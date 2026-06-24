"""Karrio PostNord client proxy."""

import karrio.lib as lib
import karrio.api.proxy as proxy
import karrio.mappers.postnord.settings as provider_settings
from karrio.universal.mappers.rating_proxy import RatingMixinProxy


class Proxy(proxy.Proxy):
    settings: provider_settings.Settings

    # PostNord has no live rate API; rating resolves the server-side RateSheet
    # via the universal rating mixin rather than an HTTP call.
    get_rates = RatingMixinProxy.get_rates

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
        # Manifest is mapped to a physical pickup booking (D2): /v3/pickups.
        response = lib.request(
            url=self._url("/rest/shipment/v3/pickups"),
            data=lib.to_json(request.serialize()),
            trace=self.trace_as("json"),
            method="POST",
            headers={"Content-Type": "application/json"},
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
