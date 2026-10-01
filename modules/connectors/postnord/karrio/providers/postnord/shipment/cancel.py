"""Karrio PostNord shipment cancellation API implementation.

PostNord's REST ``/rest/shipment/v3/edi`` does NOT support cancellation via an
``ediInstruction`` with ``updateIndicator`` ``"Deletion"``: re-POSTing a complete
booking instruction with that indicator is ignored and books a NEW shipment
(verified live -- the response is HTTP 201 with a fresh ``bookingId`` and new
tracking ids). Sending a Deletion-shaped booking would therefore silently create
duplicate shipments, so this connector never does so.

Real id-based cancellation uses the swagger ``deleteEdiRequest`` shape
(``{"ids": [{"id": <string>}], "minItems": 1}``), but its endpoint is absent from
the available ``vendor/booking.swagger.json``. Pending the delete endpoint URL
from PostNord's v3 REST reference manual, ``shipment_cancel_request`` emits the
correct ``{"ids": [{"id": ...}]}`` body and the proxy POSTs it to ``/v3/edi`` as a
placeholder: ``/v3/edi`` cannot mis-read this body as a booking and safely rejects
it ("edi.shipment is not iterable"). Success is the absence of faults in the
response.
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

    # PostNord has no usable REST cancellation endpoint (see module docstring),
    # so cancellation can never actually succeed. Never let an empty or
    # unrecognized response body be read as a successful cancellation: surface an
    # explicit "unsupported" message when the carrier returned no fault of its own.
    messages = messages or [
        models.Message(
            carrier_id=settings.carrier_id,
            carrier_name=settings.carrier_name,
            code="cancellation_unsupported",
            message=(
                "PostNord REST cancellation is unavailable: the id-based delete "
                "endpoint is pending. The shipment was not cancelled."
            ),
        )
    ]

    return None, messages


def shipment_cancel_request(
    payload: models.ShipmentCancelRequest,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    request = dict(ids=[dict(id=payload.shipment_identifier)])

    return lib.Serializable(request, lib.to_dict)
