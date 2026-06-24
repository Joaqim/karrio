"""Karrio PostNord shipment cancellation API implementation.

PostNord exposes no DELETE route; cancellation re-POSTs the booking
``ediInstruction`` (``ShipmentRequestType``) with ``updateIndicator``
``"Deletion"`` to ``/rest/shipment/v3/edi``. PostNord matches the original
shipment by ``shipmentIdentification.shipmentId`` (the client id assigned at
booking), so the Deletion references that id on both the shipment and its
item. Success is the absence of faults in the response.
"""

import datetime
import karrio.schemas.postnord.shipment_request as postnord_req

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
    shipment_id = payload.shipment_identifier

    request = postnord_req.ShipmentRequestType(
        messageDate=datetime.datetime.now().isoformat(timespec="seconds"),
        updateIndicator="Deletion",
        testIndicator=settings.test_mode,
        application=postnord_req.ApplicationType(
            name="Karrio",
            applicationId=lib.to_int(settings.application_id),
        ),
        shipment=[
            postnord_req.ShipmentType(
                shipmentIdentification=postnord_req.ShipmentIdentificationType(
                    shipmentId=shipment_id,
                ),
                parties=postnord_req.PartiesType(
                    consignor=postnord_req.ConsignType(
                        issuerCode=settings.issuer_code,
                        partyIdentification=lib.identity(
                            postnord_req.PartyIdentificationType(
                                partyId=settings.customer_number,
                                partyIdType="160",
                            )
                            if settings.customer_number
                            else None
                        ),
                    ),
                ),
                goodsItem=[
                    postnord_req.GoodsItemType(
                        items=[
                            postnord_req.ItemType(
                                itemIdentification=postnord_req.ItemIdentificationType(
                                    itemId=shipment_id,
                                ),
                            )
                        ],
                    )
                ],
            )
        ],
    )

    return lib.Serializable(request, lib.to_dict)
