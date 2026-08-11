"""Karrio DHL Freight shipment cancellation.

The DHL Freight Sweden API Farm 2.10.0 exposes no void/cancel endpoint;
cancellation must be arranged through DHL Freight customer service. This is a
documented stub that never reports a fake success. The connector Proxy
deliberately omits a ``cancel_shipment`` method, so the cancel capability is
not advertised and Karrio's gateway raises a not-supported error before this
code path is reached. Should it ever be wired, it fails loudly with a message
rather than silently no-oping.
"""

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.dhl_freight_sweden.utils as provider_utils


def parse_shipment_cancel_response(
    _response: lib.Deserializable[dict],
    settings: provider_utils.Settings,
) -> typing.Tuple[
    typing.Optional[models.ConfirmationDetails], typing.List[models.Message]
]:
    return None, [
        models.Message(
            carrier_id=settings.carrier_id,
            carrier_name=settings.carrier_name,
            code="not_supported",
            message="DHL Freight (SE API Farm) does not support shipment cancellation.",
        )
    ]


def shipment_cancel_request(
    payload: models.ShipmentCancelRequest,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    return lib.Serializable(payload.shipment_identifier)
