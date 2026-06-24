"""Karrio PostNord tracking API implementation.

The supplied Track Shipment URL API returns only a tracking URL, not events
(D7). ``get_tracking`` therefore populates ``TrackingDetails`` with the
tracking number plus the tracking URL and an empty event list, under a single
neutral status. ``LinksResponse.faults`` are surfaced as error Messages.
"""

import karrio.schemas.postnord.tracking_response as postnord_res

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.postnord.error as error
import karrio.providers.postnord.utils as provider_utils


def parse_tracking_response(
    _response: lib.Deserializable[typing.List[typing.Tuple[str, dict]]],
    settings: provider_utils.Settings,
) -> typing.Tuple[typing.List[models.TrackingDetails], typing.List[models.Message]]:
    responses = _response.deserialize()

    messages: typing.List[models.Message] = sum(
        [
            error.parse_error_response(response, settings, tracking_number=tracking_number)
            for tracking_number, response in responses
        ],
        start=[],
    )

    tracking_details = [
        _extract_details(response, settings, tracking_number)
        for tracking_number, response in responses
        if not response.get("faults")
    ]

    return tracking_details, messages


def _extract_details(
    data: dict,
    settings: provider_utils.Settings,
    tracking_number: str,
) -> models.TrackingDetails:
    details = lib.to_object(postnord_res.TrackingResponseType, data)
    tracking_url = details.url

    return models.TrackingDetails(
        carrier_id=settings.carrier_id,
        carrier_name=settings.carrier_name,
        tracking_number=tracking_number,
        events=[],
        delivered=False,
        status="in_transit",
        info=models.TrackingInfo(
            carrier_tracking_link=tracking_url,
        ),
        meta=dict(tracking_url=tracking_url),
    )


def tracking_request(
    payload: models.TrackingRequest,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    # PostNord's Track Shipment URL path is GET /v1/tracking/{country}/{id}.
    # country must be one of SE/NO/FI/DK; derive it from the account country.
    country = (settings.account_country_code or "SE").lower()
    language = (payload.options or {}).get("language") or "en"

    request = [
        dict(country=country, id=tracking_number, language=language)
        for tracking_number in payload.tracking_numbers
    ]

    return lib.Serializable(request, lib.to_dict)
