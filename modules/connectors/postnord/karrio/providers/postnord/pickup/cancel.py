"""Karrio PostNord pickup cancellation implementation.

PostNord's Booking API has no pickup cancel endpoint: ``/v3/pickups`` only
supports ``Original`` ("For messageFunction PickupBooking — Only Original is
supported"), and there is no DELETE route. Cancelling a pickup is therefore
unsupported; the parse surfaces an explicit Message rather than fabricating a
route, mirroring the shipment-cancel placeholder.
"""

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.postnord.error as error
import karrio.providers.postnord.utils as provider_utils


def parse_cancel_pickup_response(
    _response: lib.Deserializable[dict],
    settings: provider_utils.Settings,
) -> typing.Tuple[models.ConfirmationDetails, typing.List[models.Message]]:
    response = _response.deserialize()
    messages = [
        *error.parse_error_response(response, settings),
        models.Message(
            carrier_id=settings.carrier_id,
            carrier_name=settings.carrier_name,
            message=(
                "PostNord has no pickup cancel endpoint; pickup bookings "
                "support only 'Original'."
            ),
            code="not_supported",
        ),
    ]

    return None, messages


def cancel_pickup_request(
    payload: models.PickupCancelRequest,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    return lib.Serializable({"confirmationNumber": payload.confirmation_number}, lib.to_dict)
