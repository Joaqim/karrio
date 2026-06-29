"""Karrio PostNord client proxy."""

import datetime
import karrio.lib as lib
import karrio.api.proxy as proxy
import karrio.mappers.postnord.settings as provider_settings
from karrio.universal.mappers.rating_proxy import RatingMixinProxy


class Proxy(proxy.Proxy):
    settings: provider_settings.Settings

    def get_rates(self, request: lib.Serializable) -> lib.Deserializable:
        """Resolve static prices, optionally enriching with transit times.

        PostNord has no live money-rate API, so PRICE resolution delegates to
        the universal rating mixin (server-side RateSheet). Transit-time
        enrichment is opt-in via the ``enable_transit_times`` connection config
        flag (default off), because PostNord returns 403 "Invalid API Key" on
        the Transit Time API for keys not subscribed to that product. When the
        flag is disabled the universal rate result is returned unchanged with no
        carrier call.

        When enabled, one ``GET /rest/transport/v2/transittime/addresstoaddress``
        call is issued per rate request to obtain accurate transit days,
        estimated delivery dates, and per-service bookability. The transit
        results are threaded to ``parse_rate_response`` via the returned
        ``Deserializable.ctx``.

        A transit outage never breaks price rating: the call is guarded, and on
        failure an empty result set plus a ``transit_degraded`` marker is placed
        on the context so the parser can surface a warning and skip filtering.
        """
        rate_response = RatingMixinProxy.get_rates(self, request)

        if not self.settings.connection_config.enable_transit_times.state:
            return rate_response

        payload = request.serialize()
        transit_ctx = self._get_transit_times(payload)

        return lib.Deserializable(
            rate_response.deserialize(),
            ctx=transit_ctx,
        )

    def _get_transit_times(self, payload) -> dict:
        """Call the Transit Time V2 API and parse it into a service-code map.

        Returns ``{"transit_results": {basicServiceCode: {transit_days,
        estimated_delivery, is_bookable}}}`` on success, or
        ``{"transit_results": {}, "transit_degraded": True,
        "transit_degrade_reason": ...}`` when the call fails, returns a non-200
        body, or cannot be parsed. ``transit_degrade_reason`` is ``"unauthorized"``
        when PostNord rejects the key for the Transit Time product (401/403), so
        the parser can explain the cause and point to the opt-in setting.
        """
        service_codes = ",".join(
            s.carrier_service_code
            for s in (self.settings.services or [])
            if s.carrier_service_code
        )

        response = lib.failsafe(
            lambda: lib.request(
                url=self._url(
                    "/rest/transport/v2/transittime/addresstoaddress",
                    startTime=datetime.datetime.now().isoformat(timespec="seconds"),
                    originPostalCode=payload.shipper.postal_code,
                    originCountryCode=payload.shipper.country_code,
                    destinationPostalCode=payload.recipient.postal_code,
                    destinationCountryCode=payload.recipient.country_code,
                    serviceCodes=service_codes or None,
                ),
                trace=self.trace_as("json"),
                method="GET",
            )
        )

        results = _parse_transit_times(response)
        if results is None:
            return {
                "transit_results": {},
                "transit_degraded": True,
                "transit_degrade_reason": _degrade_reason(response),
            }

        return {"transit_results": results}

    def _url(self, path: str, **params) -> str:
        """Build a PostNord URL with the apikey appended as a query parameter.

        Every PostNord endpoint is apikey-authenticated via the query string
        (the Booking/Pickup/Tracking specs are ``SECURED: False``), so the
        credential always travels in the URL rather than a header.
        """
        query = lib.to_query_string(
            {"apikey": self.settings.apikey, **{k: v for k, v in params.items() if v is not None}}
        )
        return f"{self.settings.server_url}{path}?{query}"

    def create_shipment(self, request: lib.Serializable) -> lib.Deserializable[str]:
        response = lib.request(
            url=self._url("/rest/shipment/v3/edi/labels/pdf"),
            data=lib.to_json(request.serialize()),
            trace=self.trace_as("json"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        return lib.Deserializable(response, lib.to_dict, request.ctx)

    def cancel_shipment(self, request: lib.Serializable) -> lib.Deserializable[str]:
        # Placeholder endpoint: the id-based deleteEdiRequest delete route is
        # absent from the available swagger, so the {ids:[{id}]} body is POSTed to
        # /v3/edi, which safely rejects it. Pending the real delete endpoint URL
        # from PostNord's v3 reference manual (see shipment/cancel.py).
        response = lib.request(
            url=self._url("/rest/shipment/v3/edi"),
            data=lib.to_json(request.serialize()),
            trace=self.trace_as("json"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        return lib.Deserializable(response, lib.to_dict)

    def create_manifest(self, request: lib.Serializable) -> lib.Deserializable[str]:
        # PostNord has no manifest/scan-form endpoint; the operation is
        # unsupported and resolves to an explicit Message without an HTTP call.
        # Use schedule_pickup (/v3/pickups) to collect already-booked parcels.
        return lib.Deserializable("{}", lib.to_dict)

    def schedule_pickup(self, request: lib.Serializable) -> lib.Deserializable[str]:
        # Courier collection booking: POST /v3/pickups (pickupBooking).
        response = lib.request(
            url=self._url("/rest/shipment/v3/pickups"),
            data=lib.to_json(request.serialize()),
            trace=self.trace_as("json"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        return lib.Deserializable(response, lib.to_dict)

    def modify_pickup(self, request: lib.Serializable) -> lib.Deserializable[str]:
        # PostNord pickup bookings support only "Original" (no PUT/PATCH route);
        # modifying is unsupported and resolves to an explicit Message.
        return lib.Deserializable("{}", lib.to_dict)

    def cancel_pickup(self, request: lib.Serializable) -> lib.Deserializable[str]:
        # PostNord exposes no pickup cancel/DELETE route; cancelling is
        # unsupported and resolves to an explicit Message.
        return lib.Deserializable("{}", lib.to_dict)

    def find_service_points(self, request: lib.Serializable) -> lib.Deserializable[dict]:
        # Service Points v5 lookup (GET, apikey). The provider request carries the
        # chosen endpoint path (byaddress/bycoordinates) on its ctx; the v5 base
        # path is /rest/businesslocation per the spec's `servers` entry.
        response = lib.request(
            url=self._url(request.ctx["path"], **request.serialize()),
            trace=self.trace_as("json"),
            method="GET",
        )

        return lib.Deserializable(response, lib.to_dict)

    def get_tracking(self, request: lib.Serializable) -> lib.Deserializable[str]:
        # Link-only tracking (D7): GET /rest/links/v1/tracking/{country}/{id}.
        # The tracking provider serializes a list of {country, id, language}
        # dicts (country and id drive the path; language is an optional query).
        response = lib.run_asynchronously(
            lambda query: (
                query["id"],
                lib.request(
                    url=self._url(
                        f"/rest/links/v1/tracking/{query['country']}/{query['id']}",
                        language=query.get("language"),
                    ),
                    trace=self.trace_as("json"),
                    method="GET",
                ),
            ),
            request.serialize(),
        )

        return lib.Deserializable(
            response,
            lambda res: [(identifier, lib.to_dict(data)) for identifier, data in res],
        )


def _parse_transit_times(response):
    """Parse a Transit Time V2 response body into a service-code map.

    The V2 ``addresstoaddress`` operation returns a JSON array of
    ``TransitTimeV2`` objects. Each carries ``service.basicServiceCode``,
    ``estimatedTimeOfArrival`` (with ``dateOfDeparture``/``timeOfArrival`` or a
    ``dayRangeOfArrival.daysMaximum`` fallback), and an ``isBookable`` flag.

    Returns ``{basicServiceCode: {transit_days, estimated_delivery,
    is_bookable, error_message}}`` on an array body (an empty array yields an
    empty map, a successful "no transit info" result, not a degrade), or
    ``None`` to signal degrade when the body is missing, not a list (e.g. an
    error object), or unparseable.

    The response returns one entry per service *variant*: the bare service plus
    one per additional-service combination (e.g. ``18``, ``18+D6``, ``18+Q1``),
    and the variants frequently differ in bookability for a given route. The
    connector's catalog is keyed on the bare ``basicServiceCode`` only, so only
    the base entry (no ``additionalServices``) is mapped — otherwise a
    not-bookable variant would clobber a bookable base service and wrongly drop
    it from the rates.
    """
    if not response:
        return None

    entries = lib.failsafe(lambda: lib.to_dict(response))
    if not isinstance(entries, list):
        return None

    results: dict = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        service = entry.get("service") or {}
        if service.get("additionalServices"):
            continue  # variant entry; the catalog only has bare service codes
        code = service.get("basicServiceCode")
        if not code:
            continue

        eta = entry.get("estimatedTimeOfArrival") or {}
        results[code] = dict(
            transit_days=_compute_transit_days(eta),
            estimated_delivery=_estimated_delivery(eta),
            is_bookable=entry.get("isBookable"),
            error_message=entry.get("errorMessage"),
        )

    return results


def _degrade_reason(response):
    """Classify why the transit lookup degraded.

    Returns ``"unauthorized"`` when PostNord's API-gateway rejected the key for
    the Transit Time product (the nested ``{"error": {"status_code": 401|403}}``
    envelope), else ``None`` for network/unparseable/other failures.
    """
    body = lib.failsafe(lambda: lib.to_dict(response))
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict) and error.get("status_code") in (401, 403):
        return "unauthorized"
    return None


def _estimated_delivery(eta: dict):
    """Return the estimated delivery date (YYYY-MM-DD) from an ETA object."""
    arrival = eta.get("timeOfArrival")
    if not arrival:
        return None

    return lib.failsafe(
        lambda: lib.fdate(arrival, try_formats=["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"])
    )


def _compute_transit_days(eta: dict):
    """Derive transit days from an ETA, departure->arrival or day-range fallback."""
    departure = eta.get("dateOfDeparture") or eta.get("timeOfDeparture")
    arrival = eta.get("timeOfArrival")

    if departure and arrival:
        days = lib.failsafe(
            lambda: (
                lib.to_date(
                    arrival, try_formats=["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]
                ).date()
                - lib.to_date(
                    departure, try_formats=["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]
                ).date()
            ).days
        )
        if days is not None:
            return days

    day_range = eta.get("dayRangeOfArrival") or {}
    return day_range.get("daysMaximum")
