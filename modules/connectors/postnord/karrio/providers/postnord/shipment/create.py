"""Karrio PostNord shipment (Booking EDI) API implementation.

Booking and label retrieval happen in one call against
``/rest/shipment/v3/edi/labels/pdf``. The request body is an
``ediInstruction`` (``ShipmentRequestType``) with ``updateIndicator``
``"Original"``; the response is an ``ediLabelResponse`` carrying a
``bookingResponse`` (ids, tracking urls, per-item errors) and one or more
``labelPrintout`` entries with base64 label data.
"""

import uuid
import datetime
import karrio.schemas.postnord.shipment_request as postnord_req
import karrio.schemas.postnord.shipment_response as postnord_res

import typing
import karrio.lib as lib
import karrio.core.units as units
import karrio.core.models as models
import karrio.providers.postnord.error as error
import karrio.providers.postnord.utils as provider_utils
import karrio.providers.postnord.units as provider_units


def parse_shipment_response(
    _response: lib.Deserializable[dict],
    settings: provider_utils.Settings,
) -> typing.Tuple[models.ShipmentDetails, typing.List[models.Message]]:
    response = _response.deserialize()
    messages = error.parse_error_response(response, settings)

    booking = response.get("bookingResponse") or {}
    # A booking succeeds per-item: any item allocated ids (item/shipment id)
    # yields a usable label and tracking number. Inline per-item faults are
    # surfaced as messages alongside the details, so the presence of messages
    # must not suppress a partially-successful booking.
    informations = booking.get("idInformation") or []
    has_shipment = any(info.get("ids") for info in informations)
    shipment = (
        _extract_details(response, settings, _response.ctx)
        if has_shipment
        else None
    )

    return shipment, messages


def _extract_details(
    data: dict,
    settings: provider_utils.Settings,
    ctx: dict = {},
) -> models.ShipmentDetails:
    response = lib.to_object(postnord_res.ShipmentResponseType, data)
    booking = response.bookingResponse
    informations = booking.idInformation or []

    ids = [_id for info in informations for _id in (info.ids or [])]
    urls = [url for info in informations for url in (info.urls or [])]

    tracking_number = next(
        (_id.value for _id in ids if _id.idType == "itemId"), None
    )
    shipment_identifier = lib.identity(
        ctx.get("shipment_id")
        or next((_id.value for _id in ids if _id.idType == "shipmentId"), None)
        or booking.bookingId
        or tracking_number
    )
    tracking_url = next(
        (url.url for url in urls if (url.type or "").upper() == "TRACKING"), None
    )

    printouts = response.labelPrintout or []
    label_format = next(
        (p.printout.labelFormat for p in printouts if p.printout), "PDF"
    )
    label_data = [
        p.printout.data for p in printouts if p.printout and p.printout.data
    ]
    label = lib.identity(
        label_data[0]
        if len(label_data) == 1
        else lib.bundle_base64(label_data, label_format) if label_data else None
    )

    return models.ShipmentDetails(
        carrier_id=settings.carrier_id,
        carrier_name=settings.carrier_name,
        tracking_number=tracking_number,
        shipment_identifier=shipment_identifier,
        label_type=label_format,
        docs=models.Documents(label=label),
        meta=dict(
            booking_id=booking.bookingId,
            tracking_url=tracking_url,
            carrier_tracking_link=tracking_url,
        ),
    )


def shipment_request(
    payload: models.ShipmentRequest,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    shipper = lib.to_address(payload.shipper)
    recipient = lib.to_address(payload.recipient)
    packages = lib.to_packages(payload.parcels)
    service = provider_units.ShippingService.map(payload.service).value_or_key
    options = lib.to_shipping_options(
        payload.options,
        package_options=packages.options,
        initializer=provider_units.shipping_options_initializer,
    )

    additional_service_codes = [option.code for _, option in options.items()]

    # Assign a client-controlled shipmentId from the merchant reference so the
    # booking carries a searchable Track & Trace id; without one PostNord
    # auto-allocates an opaque id. Prefer the caller reference; fall back to a
    # generated id (unit tests always set a reference). Cancellation is not
    # performed via this id (see shipment/cancel.py).
    shipment_id = payload.reference or uuid.uuid4().hex[:12].upper()

    def _party(address, *, with_consignor_id: bool) -> postnord_req.ConsignType:
        return postnord_req.ConsignType(
            issuerCode=settings.issuer_code,
            partyIdentification=lib.identity(
                postnord_req.PartyIdentificationType(
                    partyId=settings.customer_number,
                    partyIdType="160",
                )
                if with_consignor_id and settings.customer_number
                else None
            ),
            party=postnord_req.PartyType(
                nameIdentification=postnord_req.NameIdentificationType(
                    name=address.person_name or address.company_name,
                    companyName=address.company_name,
                ),
                address=postnord_req.AddressType(
                    streets=[_ for _ in [address.address_line1, address.address_line2] if _],
                    postalCode=address.postal_code,
                    city=address.city,
                    state=address.state_code,
                    countryCode=address.country_code,
                ),
                contact=postnord_req.ContactType(
                    contactName=address.person_name,
                    emailAddress=address.email,
                    phoneNo=address.phone_number,
                    smsNo=address.phone_number,
                ),
            ),
        )

    request = postnord_req.ShipmentRequestType(
        messageDate=datetime.datetime.now().isoformat(timespec="seconds"),
        updateIndicator="Original",
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
                service=postnord_req.ServiceType(
                    basicServiceCode=service,
                    additionalServiceCode=additional_service_codes or None,
                ),
                parties=postnord_req.PartiesType(
                    consignor=_party(shipper, with_consignor_id=True),
                    consignee=_party(recipient, with_consignor_id=False),
                ),
                goodsItem=[
                    postnord_req.GoodsItemType(
                        packageTypeCode=provider_units.PackagingType.map(
                            package.packaging_type or "your_packaging"
                        ).value,
                        numberOfPackageTypeCodeItems=postnord_req.NumberOfPackageType(
                            value=1,
                        ),
                        items=[
                            postnord_req.ItemType(
                                itemIdentification=postnord_req.ItemIdentificationType(
                                    # "0" tells PostNord to allocate the parcel id
                                    # (returned as the tracking number). An arbitrary
                                    # value triggers "unable to determine id type",
                                    # since PostNord infers the id scheme (SSCC/S10/…)
                                    # from the value.
                                    itemId="0",
                                ),
                                grossWeight=postnord_req.TotalGrossWeightType(
                                    value=package.weight.KG,
                                    unit="KGM",
                                ),
                                dimensions=lib.identity(
                                    postnord_req.DimensionsType(
                                        height=postnord_req.TotalGrossWeightType(
                                            value=package.height.CM, unit="CMT"
                                        ),
                                        width=postnord_req.TotalGrossWeightType(
                                            value=package.width.CM, unit="CMT"
                                        ),
                                        length=postnord_req.TotalGrossWeightType(
                                            value=package.length.CM, unit="CMT"
                                        ),
                                    )
                                    if any([package.height, package.width, package.length])
                                    else None
                                ),
                            )
                        ],
                    )
                    for package in packages
                ],
            )
        ],
    )

    return lib.Serializable(request, lib.to_dict, dict(shipment_id=shipment_id))
