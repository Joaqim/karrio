"""Karrio PostNord shipment cancellation API implementation.

PostNord exposes no DELETE route; cancellation POSTs a ``deleteEdiRequest``
(``{"ids": [{"id": ...}]}``, ``minItems`` 1) referencing the booked shipment id
to ``/rest/shipment/v3/edi``. Success is the absence of faults in the response.
"""

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.postnord.error as error
import karrio.providers.postnord.utils as provider_utils


def parse_shipment_cancel_response(
    _response: lib.Deserializable[dict],
    settings: provider_utils.Settings,
) -> typing.Tuple[models.ConfirmationDetails, typing.List[models.Message]]:
    response = _response.deserialize()
    messages = error.parse_error_response(response, settings)
    success = not any(messages)

    confirmation = (
        models.ConfirmationDetails(
            carrier_id=settings.carrier_id,
            carrier_name=settings.carrier_name,
            operation="Cancel Shipment",
            success=success,
        )
        if success
        else None
    )

    return confirmation, messages


def shipment_cancel_request(
    payload: models.ShipmentCancelRequest,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    # PostNord cancellation is a deleteEdiRequest: an ids array (minItems 1) of
    # {"id": ...} objects naming the EDI/shipment ids to delete.
    request = dict(ids=[dict(id=payload.shipment_identifier)])

    return lib.Serializable(request, lib.to_dict)
