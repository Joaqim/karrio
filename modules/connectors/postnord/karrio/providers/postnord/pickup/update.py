"""Karrio PostNord pickup update implementation.

PostNord's Booking API has no pickup modify endpoint: ``/v3/pickups`` only
supports ``Original`` (the spec states "For messageFunction PickupBooking — Only
Original is supported"), with no PUT/PATCH and no identifier-addressed update
route. Updating a pickup is therefore unsupported; the request is a no-op and
the parse surfaces an explicit Message rather than fabricating a route.
"""

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.postnord.error as error
import karrio.providers.postnord.utils as provider_utils


def parse_pickup_update_response(
    _response: lib.Deserializable[dict],
    settings: provider_utils.Settings,
) -> typing.Tuple[models.PickupDetails, typing.List[models.Message]]:
    response = _response.deserialize()
    messages = [
        *error.parse_error_response(response, settings),
        models.Message(
            carrier_id=settings.carrier_id,
            carrier_name=settings.carrier_name,
            message=(
                "PostNord has no pickup update endpoint; cancel is also "
                "unavailable. Schedule a new pickup instead."
            ),
            code="not_supported",
        ),
    ]

    return None, messages


def pickup_update_request(
    payload: models.PickupUpdateRequest,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    return lib.Serializable({"confirmationNumber": payload.confirmation_number}, lib.to_dict)
