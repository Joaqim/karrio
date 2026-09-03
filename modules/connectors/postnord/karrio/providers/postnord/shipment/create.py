"""Karrio PostNord shipment (Booking EDI) API implementation.

Booking and label retrieval happen in one call against
``/rest/shipment/v3/edi/labels/pdf`` or ``/labels/zpl`` (selected by the
resolved label type). The request body is an ``ediInstruction``
(``ShipmentRequestType``) with ``updateIndicator`` ``"Original"``; the
response is an ``ediLabelResponse`` carrying a ``bookingResponse`` (ids,
tracking urls, per-item errors) and one or more ``labelPrintout`` entries.
PDF printouts carry base64 data; ZPL printouts carry raw UTF-8 ZPL text
with ``printout.encoding`` set to ``"none"`` (observed on the live
endpoint; the swagger documents base64 only).
"""

import base64
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
        (
            p.printout.labelFormat
            for p in printouts
            if p.printout and p.printout.labelFormat
        ),
        # ZPL responses have been observed without labelFormat; fall back to
        # the requested type rather than assuming PDF.
        ctx.get("label_type", "PDF"),
    )
    label_data = [
        _printout_base64(p.printout)
        for p in printouts
        if p.printout and p.printout.data
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


def _printout_base64(printout: postnord_res.PrintoutType) -> str:
    """Return the printout data as base64 regardless of transport encoding.

    PDF printouts are base64 already. ZPL printouts carry raw UTF-8 ZPL
    text with ``encoding`` ``"none"`` (undocumented in the swagger), so
    any non-base64 encoding is treated as raw text and encoded here; the
    downstream bundling helpers expect base64 inputs.
    """
    if (printout.encoding or "").lower() == "base64":
        return printout.data

    return base64.b64encode(printout.data.encode("utf-8")).decode("utf-8")


def shipment_request(
    payload: models.ShipmentRequest,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    shipper = lib.to_address(payload.shipper)
    recipient = lib.to_address(payload.recipient)
    packages = lib.to_packages(payload.parcels)
    service = provider_units.ShippingService.map(payload.service).value_or_key

    # File format is selected by endpoint path in the proxy; resolve
    # payload.label_type -> connection default -> PDF and thread it via ctx.
    label_type = lib.identity(
        provider_units.LabelType.map(
            payload.label_type or settings.connection_config.label_type.state
        ).value
        or provider_units.LabelType.PDF.value
    )
    options = lib.to_shipping_options(
        payload.options,
        package_options=packages.options,
        initializer=provider_units.shipping_options_initializer,
    )

    additional_service_codes = [option.code for _, option in options.items()]

    # Booking locale: request options.language > connection config language >
    # "en". Sent lowercase as the query `locale` (SMS/Email language) and
    # uppercased as the body `language` element (label/document text).
    locale = (
        (payload.options or {}).get("language")
        or settings.connection_config.language.state
        or "en"
    )

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
        # Uppercase ISO 639-1 language code for label/document text elements;
        # the query `locale` (SMS/Email language) is the lowercase variant.
        language=(locale.upper() if locale else None),
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

    return lib.Serializable(
        request, lib.to_dict, dict(shipment_id=shipment_id, label_type=label_type, locale=locale)
    )
