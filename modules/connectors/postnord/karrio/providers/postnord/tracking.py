"""Karrio PostNord tracking API implementation (Track & Trace v7).

``get_tracking`` calls PostNord's Track & Trace v7 ``findByIdentifier``
endpoint keyed on the karrio ``tracking_number`` (the allocated itemId) and
parses the ``ResponseDto.TrackingInformationResponse.shipments[].items[]``
event history into ``TrackingDetails`` with timestamped events, a normalized
status, a delivered flag, ``signed_by``, and estimated delivery.

PostNord authorizes per product, so the v7 call may return the gateway 403
envelope (``{"error": {"status_code": 403, ...}}``) when the key is not
subscribed to T&T. When the response yields no usable item (auth error,
``compositeFault``, or no data) the detail degrades to the prior link-only
behavior: the tracking URL plus a single neutral ``in_transit`` status and an
empty event list, so tracking still returns a usable result. Both the
``compositeFault`` and the gateway envelope are surfaced as error Messages.
"""

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.postnord.error as error
import karrio.providers.postnord.units as provider_units
import karrio.providers.postnord.utils as provider_utils

_DATETIME_FORMATS = ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]


def parse_tracking_response(
    _response: lib.Deserializable[typing.List[typing.Tuple[str, dict]]],
    settings: provider_utils.Settings,
) -> typing.Tuple[typing.List[models.TrackingDetails], typing.List[models.Message]]:
    responses = _response.deserialize()

    messages: typing.List[models.Message] = sum(
        [
            error.parse_error_response(
                # the compositeFault is nested under TrackingInformationResponse;
                # the gateway 403 envelope sits at the top level, so pass both.
                [_information(response), response],
                settings,
                tracking_number=tracking_number,
            )
            for tracking_number, response in responses
        ],
        start=[],
    )

    tracking_details = [
        _extract_details(response, settings, tracking_number)
        for tracking_number, response in responses
    ]

    return tracking_details, messages


def _information(response: dict) -> dict:
    """Return the inner ``TrackingInformationResponse`` (or an empty dict)."""
    return (response.get("TrackingInformationResponse") or {}) if isinstance(
        response, dict
    ) else {}


def _extract_details(
    data: dict,
    settings: provider_utils.Settings,
    tracking_number: str,
) -> models.TrackingDetails:
    tracking_url = settings.tracking_url.format(tracking_number)
    shipment, item = _locate_item(_information(data), tracking_number)

    if item is None:
        # No usable v7 data (auth error, compositeFault, or empty body): degrade
        # to the link-only result so tracking still returns a usable detail.
        return models.TrackingDetails(
            carrier_id=settings.carrier_id,
            carrier_name=settings.carrier_name,
            tracking_number=tracking_number,
            events=[],
            delivered=False,
            status="in_transit",
            info=models.TrackingInfo(carrier_tracking_link=tracking_url),
            meta=dict(tracking_url=tracking_url),
        )

    status = _tracking_status(item.get("status") or item.get("eventStatus"))
    estimated_delivery = lib.failsafe(
        lambda: lib.fdate(
            item.get("estimatedTimeOfArrival")
            or shipment.get("estimatedTimeOfArrival")
            or shipment.get("deliveryDate"),
            try_formats=_DATETIME_FORMATS,
        )
    )
    acceptor = item.get("acceptor") or {}

    return models.TrackingDetails(
        carrier_id=settings.carrier_id,
        carrier_name=settings.carrier_name,
        tracking_number=tracking_number,
        events=[
            models.TrackingEvent(
                date=lib.failsafe(
                    lambda event=event: lib.fdate(
                        event.get("eventTime"), try_formats=_DATETIME_FORMATS
                    )
                ),
                time=lib.failsafe(
                    lambda event=event: lib.flocaltime(
                        event.get("eventTime"), try_formats=_DATETIME_FORMATS
                    )
                ),
                code=event.get("eventCode"),
                description=event.get("eventDescription"),
                location=_location(event.get("location")),
            )
            for event in (item.get("events") or [])
        ],
        delivered=status == "delivered",
        status=status,
        estimated_delivery=estimated_delivery,
        info=models.TrackingInfo(
            carrier_tracking_link=tracking_url,
            shipment_package_count=shipment.get("assessedNumberOfItems"),
            signed_by=acceptor.get("name"),
        ),
        meta=dict(tracking_url=tracking_url),
    )


def _locate_item(
    information: dict,
    tracking_number: str,
) -> typing.Tuple[dict, typing.Optional[dict]]:
    """Find the (shipment, item) whose ``itemId`` matches the tracking number.

    Falls back to the first item of the first shipment when no exact match is
    found, and returns ``(shipment, None)`` when there is no item at all.
    """
    shipments = information.get("shipments") or []
    if not shipments:
        return {}, None

    for shipment in shipments:
        for item in shipment.get("items") or []:
            if item.get("itemId") == tracking_number:
                return shipment, item

    first = shipments[0]
    items = first.get("items") or []
    return first, (items[0] if items else None)


def _location(location: typing.Optional[dict]) -> typing.Optional[str]:
    """Compact a ``LocationDto`` into a single human-readable location string."""
    if not isinstance(location, dict):
        return None

    parts = [
        location.get("name"),
        lib.text(location.get("city"), location.get("postcode")),
        location.get("countryCode"),
    ]
    return lib.text(*parts, separator=", ") or None


def _tracking_status(status: typing.Optional[str]) -> str:
    """Normalize a v7 ``ItemStatus`` to a ``TrackerStatus`` name."""
    return next(
        (
            mapped.name
            for mapped in list(provider_units.TrackingStatus)
            if status in mapped.value
        ),
        provider_units.TrackingStatus.in_transit.name,
    )


def tracking_request(
    payload: models.TrackingRequest,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    # Track & Trace v7 keys on the itemId (= karrio tracking_number); locale is
    # an optional display-language query (default "en").
    locale = (payload.options or {}).get("language") or "en"

    request = [
        dict(id=tracking_number, locale=locale)
        for tracking_number in payload.tracking_numbers
    ]

    return lib.Serializable(request, lib.to_dict)
