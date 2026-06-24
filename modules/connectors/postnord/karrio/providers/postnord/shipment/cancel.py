"""Karrio PostNord shipment cancellation API implementation.

PostNord exposes no DELETE route; cancellation re-POSTs an ``ediInstruction``
with ``updateIndicator`` ``"Deletion"`` referencing the booked shipment id
(``/rest/shipment/v3/edi``). Success is the absence of faults in the response.
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
    options = payload.options or {}
    service = options.get("service")

    # Deletion reuses the booking EdiInstruction schema, which still REQUIRES
    # service, parties, and a goodsItem with at least one items[] entry even
    # when only deleting. ShipmentCancelRequest carries no original shipper or
    # parcels, so parties/service are reduced to safe minimal values: the
    # consignor identifies the agreement holder, and the goodsItem references
    # the parcel/tracking id (shipment_identifier) being deleted. service is
    # only emitted when an optional payload option supplies it.
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
                    shipmentId=payload.shipment_identifier,
                ),
                service=lib.identity(
                    postnord_req.ServiceType(basicServiceCode=service)
                    if service
                    else None
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
                                    itemId=payload.shipment_identifier,
                                ),
                            )
                        ],
                    )
                ],
            )
        ],
    )

    return lib.Serializable(request, lib.to_dict)
