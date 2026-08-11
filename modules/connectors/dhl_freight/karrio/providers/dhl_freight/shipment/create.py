"""Karrio DHL Freight shipment API implementation."""

import karrio.schemas.dhl_freight.transport_instruction_request as dhl_freight_req
import karrio.schemas.dhl_freight.transport_instruction_response as dhl_freight_res
import karrio.schemas.dhl_freight.print_request as dhl_freight_print
import karrio.schemas.dhl_freight.print_response as dhl_freight_report

import typing
import karrio.lib as lib
import karrio.core.units as units
import karrio.core.models as models
import karrio.providers.dhl_freight.error as error
import karrio.providers.dhl_freight.utils as provider_utils
import karrio.providers.dhl_freight.units as provider_units


def parse_shipment_response(
    _response: lib.Deserializable[typing.List[dict]],
    settings: provider_utils.Settings,
) -> typing.Tuple[models.ShipmentDetails, typing.List[models.Message]]:
    booking, printed = _response.deserialize()
    messages = error.parse_error_response([booking, printed], settings)

    instruction = (booking or {}).get("transportInstruction") or {}
    details = lib.identity(
        _extract_details(booking, printed, settings) if instruction.get("id") else None
    )

    return details, messages


def _extract_details(
    booking: dict,
    printed: dict,
    settings: provider_utils.Settings,
) -> models.ShipmentDetails:
    instruction = lib.to_object(
        dhl_freight_res.TransportInstructionType,
        booking.get("transportInstruction") or {},
    )
    result = lib.to_object(dhl_freight_report.PrintResponseType, printed)
    report = next(iter(result.reports or []), None)

    tracking_number = instruction.id
    content_type = getattr(report, "contentType", None) or ""
    label_type = lib.identity(
        "PDF"
        if "pdf" in content_type.lower()
        else (
            "ZPL"
            if "zpl" in content_type.lower()
            else (
                "PNG"
                if "png" in content_type.lower()
                else settings.connection_config.label_type.state or "PDF"
            )
        )
    )

    return models.ShipmentDetails(
        carrier_id=settings.carrier_id,
        carrier_name=settings.carrier_name,
        tracking_number=tracking_number,
        shipment_identifier=tracking_number,
        label_type=label_type,
        docs=models.Documents(label=getattr(report, "content", None) or ""),
        meta=dict(
            carrier_tracking_link=settings.tracking_url.format(tracking_number),
            product_code=(
                str(instruction.productCode)
                if instruction.productCode is not None
                else None
            ),
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

    payer_code = options.dhl_freight_payer_code.state or settings.account_number
    service_point = options.dhl_freight_service_point.state
    page_type = provider_units.PageType.map(
        options.dhl_freight_label_page_type.state
        or settings.connection_config.label_page_type.state
        or provider_units.PageType.Label.value
    ).value_or_key

    parties = [
        _party(provider_units.PartyType.Consignor, shipper),
        _party(provider_units.PartyType.Consignee, recipient),
        *lib.identity([_payer_party(payer_code)] if payer_code else []),
        *lib.identity(
            [
                dhl_freight_req.PartyType(
                    id=service_point,
                    type=provider_units.PartyType.AccessPoint.value,
                    subType=provider_units.PartySubType.map(
                        options.dhl_freight_service_point_type.state
                        or provider_units.PartySubType.ParcelShop.value
                    ).value_or_key,
                )
            ]
            if service_point
            else []
        ),
    ]

    request = dhl_freight_req.TransportInstructionRequestType(
        # productCode is generated as Optional[int]; the SPI product and codes
        # such as 402/502 must serialize as strings on the wire.
        productCode=str(service),
        shippingDate=lib.fdate(payload.options.get("shipment_date")),
        totalNumberOfPieces=len(packages),
        totalWeight=packages.weight.KG,
        references=lib.identity(
            [
                dhl_freight_req.ReferenceType(
                    qualifier="CustomerReference", value=payload.reference
                )
            ]
            if payload.reference
            else []
        ),
        payerCode=lib.identity(
            dhl_freight_req.PayerCodeType(code=payer_code) if payer_code else None
        ),
        parties=parties,
        pieces=[
            dhl_freight_req.PieceType(
                # packageType/goodsType are product-documentation dependent and
                # not enumerated in the API Farm spec; omitted in Phase 0.
                marksAndNumbers=package.reference_number,
                numberOfPieces=1,
                weight=package.weight.KG,
                volume=lib.failsafe(lambda: package.volume.m3),
                width=lib.identity(package.width.CM if package.width.value else None),
                height=lib.identity(
                    package.height.CM if package.height.value else None
                ),
                length=lib.identity(
                    package.length.CM if package.length.value else None
                ),
            )
            for package in packages
        ],
        additionalServices=dhl_freight_req.AdditionalServicesType(
            notification=options.dhl_freight_notification.state,
            preAdvice=options.dhl_freight_pre_advice.state,
            tailLiftUnloading=options.dhl_freight_tail_lift_unloading.state,
            doorstepDelivery=lib.identity(
                dhl_freight_req.DoorstepDeliveryType(
                    accessCode=options.dhl_freight_doorstep_access_code.state
                )
                if options.dhl_freight_doorstep_access_code.state is not None
                else None
            ),
            insurance=lib.identity(
                dhl_freight_req.InsuranceType(
                    value=options.dhl_freight_insurance.state,
                    currency=options.currency.state,
                )
                if options.dhl_freight_insurance.state is not None
                else None
            ),
        ),
    )

    print_options = dhl_freight_print.OptionsType(
        label=True,
        pageOptions=dhl_freight_print.PageOptionsType(pageType=page_type),
    )

    return lib.Serializable(
        request,
        lib.to_dict,
        dict(
            print_options=lib.to_dict(print_options),
            label_type=settings.connection_config.label_type.state or "PDF",
        ),
    )


def _party(role: str, address) -> dhl_freight_req.PartyType:
    return dhl_freight_req.PartyType(
        type=role,
        name=address.company_name or address.person_name,
        contactName=address.contact,
        vatEoriSocialSecurityNumber=address.tax_id,
        phone=address.phone_number,
        email=address.email,
        address=dhl_freight_req.AddressType(
            street=address.address_line1,
            additionalAddressInfo=address.address_line2,
            cityName=address.city,
            # postalCode is generated as Optional[int]; keep it a string so
            # alphanumeric/space-bearing postal codes survive serialization.
            postalCode=str(address.postal_code) if address.postal_code else None,
            countryCode=address.country_code,
        ),
    )


def _payer_party(payer_code: str) -> dhl_freight_req.PartyType:
    return dhl_freight_req.PartyType(
        type=provider_units.PartyType.FreightPayer.value,
        id=payer_code,
    )
