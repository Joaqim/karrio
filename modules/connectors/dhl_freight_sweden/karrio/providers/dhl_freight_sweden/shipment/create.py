"""Karrio DHL Freight shipment API implementation."""

import karrio.schemas.dhl_freight_sweden.transport_instruction_request as dhl_freight_sweden_req
import karrio.schemas.dhl_freight_sweden.transport_instruction_response as dhl_freight_sweden_res
import karrio.schemas.dhl_freight_sweden.print_request as dhl_freight_sweden_print
import karrio.schemas.dhl_freight_sweden.print_response as dhl_freight_sweden_report

import base64
import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.core.units as units
import karrio.core.errors as errors
import karrio.providers.dhl_freight_sweden.error as error
import karrio.providers.dhl_freight_sweden.utils as provider_utils
import karrio.providers.dhl_freight_sweden.units as provider_units


class DeclarationCurrencyError(errors.ShippingSDKDetailedError):
    """Raised when commodity value currencies conflict with the declaration."""

    code = "SHIPPING_SDK_FIELD_ERROR"


class CustomsServiceIdentifierError(errors.ShippingSDKDetailedError):
    """Raised when a selected customs service lacks its required identifier."""

    code = "SHIPPING_SDK_FIELD_ERROR"


class ServicePointDetailsError(errors.ShippingSDKDetailedError):
    """Raised when an access point party is missing service point details."""

    code = "SHIPPING_SDK_FIELD_ERROR"


def parse_shipment_response(
    _response: lib.Deserializable[typing.List[dict]],
    settings: provider_utils.Settings,
) -> typing.Tuple[models.ShipmentDetails, typing.List[models.Message]]:
    # The proxy appends address-validation warning messages as optional
    # trailing elements after the booking and print bodies.
    booking, printed, *warnings = _response.deserialize()
    messages = [
        *error.parse_error_response([booking, printed], settings),
        *(lib.to_object(models.Message, warning) for warning in warnings),
    ]

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
        dhl_freight_sweden_res.TransportInstructionType,
        booking.get("transportInstruction") or {},
    )
    result = lib.to_object(dhl_freight_sweden_report.PrintResponseType, printed)
    report = next(iter(result.reports or []), None)

    tracking_number = instruction.id

    return models.ShipmentDetails(
        carrier_id=settings.carrier_id,
        carrier_name=settings.carrier_name,
        tracking_number=tracking_number,
        shipment_identifier=tracking_number,
        label_type=_label_type(report, settings),
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


# The Print API has no raster-format parameter, so the emitted document
# format is governed by the DHL account and is identified from the decoded
# report bytes' magic prefix (live-verified PDF A4, 2026-09-10).
LABEL_MAGICS: typing.Tuple[typing.Tuple[bytes, str], ...] = (
    (b"%PDF-", "PDF"),
    (b"^XA", "ZPL"),
)
CONTENT_TYPE_LABELS: typing.Tuple[typing.Tuple[str, str], ...] = (
    ("pdf", "PDF"),
    ("zpl", "ZPL"),
    ("png", "PNG"),
)


def _label_type(report, settings: provider_utils.Settings) -> str:
    prefix = (
        lib.failsafe(
            lambda: base64.b64decode(getattr(report, "content", None) or "")[:16].strip()
        )
        or b""
    )
    content_type = (getattr(report, "contentType", None) or "").lower()

    return (
        next((label for magic, label in LABEL_MAGICS if prefix.startswith(magic)), None)
        or next(
            (label for keyword, label in CONTENT_TYPE_LABELS if keyword in content_type),
            None,
        )
        or settings.connection_config.label_type.state
        or "PDF"
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

    # PayerCode carries the product's terms-of-delivery code (see the product
    # documentation): domestic products use the freight-payer codes 1/3/4,
    # international products use Incoterms or Combiterm codes.
    payer_code = lib.identity(
        options.dhl_freight_sweden_payer_code.state
        or (payload.customs.incoterm if payload.customs else None)
        or "1"
    )
    procedure_code = (
        options.dhl_freight_sweden_customs_procedure_code.state or "1042"
    )
    service_point_party = _service_point_party(options)
    customs_options = lib.to_customs_info(
        payload.customs, option_type=provider_units.CustomsOption
    ).options
    _check_customs_service_identifiers(options, customs_options)
    page_type = provider_units.PageType.map(
        options.dhl_freight_sweden_label_page_type.state
        or settings.connection_config.label_page_type.state
        or provider_units.PageType.Label.value
    ).value_or_key
    customs = lib.identity(
        _customs_information(
            payload.customs,
            customs_options,
            shipper.country_code,
            recipient.country_code,
            procedure_code,
        )
        if payload.customs
        and any(
            [
                payload.customs.commodities,
                payload.customs.invoice,
                payload.customs.invoice_date,
            ]
        )
        else None
    )

    parties = [
        # The consignor id is the customer/agreement number and is mandatory
        # according to the payer code; the consignor-pays default always needs it.
        _party(
            provider_units.PartyType.Consignor, shipper, id=settings.account_number
        ),
        _party(provider_units.PartyType.Consignee, recipient),
        *lib.identity([service_point_party] if service_point_party else []),
    ]

    request = dhl_freight_sweden_req.TransportInstructionRequestType(
        # productCode is generated as Optional[int]; the SPI product and codes
        # such as 402/502 must serialize as strings on the wire.
        productCode=str(service),
        shippingDate=lib.fdate(payload.options.get("shipment_date")),
        pickupInstruction=options.dhl_freight_sweden_pickup_instruction.state,
        deliveryInstruction=options.dhl_freight_sweden_delivery_instruction.state,
        totalNumberOfPieces=len(packages),
        totalWeight=packages.weight.KG,
        references=lib.identity(
            [
                dhl_freight_sweden_req.ReferenceType(
                    # DHL Freight (Sweden) shipment-level reference qualifiers
                    # (product manual appendix E); the qualifier is limited to
                    # 3 characters and karrio's reference is the consignor's.
                    qualifier="CU",
                    value=payload.reference,
                )
            ]
            if payload.reference
            else []
        ),
        payerCode=lib.identity(
            dhl_freight_sweden_req.PayerCodeType(code=payer_code) if payer_code else None
        ),
        parties=parties,
        pieces=[
            dhl_freight_sweden_req.PieceType(
                # packageType/goodsType are product-documentation dependent and
                # not enumerated in the API Farm spec, so they are omitted.
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
        additionalServices=dhl_freight_sweden_req.AdditionalServicesType(
            notification=options.dhl_freight_sweden_notification.state,
            preAdvice=options.dhl_freight_sweden_pre_advice.state,
            tailLiftUnloading=options.dhl_freight_sweden_tail_lift_unloading.state,
            doorstepDelivery=lib.identity(
                dhl_freight_sweden_req.DoorstepDeliveryType(
                    accessCode=options.dhl_freight_sweden_doorstep_access_code.state
                )
                if options.dhl_freight_sweden_doorstep_access_code.state is not None
                else None
            ),
            insurance=lib.identity(
                dhl_freight_sweden_req.InsuranceType(
                    value=options.dhl_freight_sweden_insurance.state,
                    currency=options.currency.state,
                )
                if options.dhl_freight_sweden_insurance.state is not None
                else None
            ),
            customsHandlingStandard=lib.identity(
                True
                if options.dhl_freight_sweden_customs_handling_standard.state
                else None
            ),
            customsHandlingFullService=lib.identity(
                True
                if options.dhl_freight_sweden_customs_handling_full_service.state
                else None
            ),
            customsCustomersOwnDeclaration=lib.identity(
                dhl_freight_sweden_req.CustomsCustomersOwnDeclarationType(
                    customsId=options.dhl_freight_sweden_customs_own_declaration.state
                )
                if options.dhl_freight_sweden_customs_own_declaration.state
                is not None
                else None
            ),
            customsJointDeclaration=lib.identity(
                dhl_freight_sweden_req.CustomsJointDeclarationType(
                    sfid=options.dhl_freight_sweden_customs_joint_declaration.state
                )
                if options.dhl_freight_sweden_customs_joint_declaration.state
                is not None
                else None
            ),
            voecSupplyVAT=lib.identity(
                dhl_freight_sweden_req.VoecSupplyVATType(
                    vatId=customs_options.voec_number.state
                )
                if customs_options.voec_number.state
                else None
            ),
        ),
        customsInformation=customs,
    )

    print_options = dhl_freight_sweden_print.OptionsType(
        label=True,
        pageOptions=dhl_freight_sweden_print.PageOptionsType(pageType=page_type),
    )

    return lib.Serializable(
        request,
        lib.to_dict,
        dict(print_options=lib.to_dict(print_options)),
    )


def _customs_information(
    customs: models.Customs,
    customs_options: units.CustomsOptions,
    origin_country: str,
    destination_country: str,
    procedure_code: str,
) -> dhl_freight_sweden_req.CustomsInformationType:
    duty = customs.duty
    commodities = customs.commodities or []
    # A customs declaration carries a single currency: the duty currency when
    # present, otherwise the commodities' common currency. Commodity lines
    # without a currency are gap-filled from it, and a line carrying a
    # different currency would corrupt the declaration, so it is rejected.
    declaration_currency = lib.identity(
        (duty.currency if duty else None)
        or next(
            (c.value_currency for c in commodities if c.value_currency), None
        )
    )
    conflicting = {
        commodity.value_currency
        for commodity in commodities
        if commodity.value_currency
        and declaration_currency
        and commodity.value_currency != declaration_currency
    }
    if any(conflicting):
        raise DeclarationCurrencyError(
            "Commodity value currencies must match the customs declaration "
            f"currency {declaration_currency}; "
            f"found {', '.join(sorted(conflicting))}",
            details={
                "customs.commodities.value_currency": dict(
                    code="invalid",
                    message="mixed commodity currencies",
                )
            },
        )

    # The API requires at least one customs document whenever the customs
    # information section is present, so the document is always emitted.
    document = dhl_freight_sweden_req.CustomsDocumentType(
        id=customs.invoice,
        type=lib.identity(
            provider_units.CustomsDocumentType.CommercialInvoice.value
            if customs.commercial_invoice
            else provider_units.CustomsDocumentType.ProformaInvoice.value
        ),
        transportMovement=lib.identity(
            provider_units.TransportMovement.Export.value
            if destination_country and destination_country != origin_country
            else None
        ),
        invoiceDate=lib.fdate(customs.invoice_date),
        invoiceCurrency=declaration_currency,
        invoiceAmount=duty.declared_value if duty else None,
        eori=customs_options.eori_number.state or None,
    )

    return dhl_freight_sweden_req.CustomsInformationType(
        customsDocuments=[document],
        customsCommodities=[
            dhl_freight_sweden_req.CustomsCommodityType(
                countryCodeOfOrigin=commodity.origin_country,
                customsValueCurrency=commodity.value_currency
                or declaration_currency,
                customsValue=commodity.value_amount,
                # hsItemId and procedureCode are strings on the wire even
                # though the generated type annotates them as int.
                hsItemId=commodity.hs_code,
                commodityDescription=commodity.description or commodity.title,
                procedureCode=procedure_code,
                netWeight=commodity.weight,
                numberOfUnits=commodity.quantity,
            )
            for commodity in commodities
        ],
    )


def _check_customs_service_identifiers(
    options: units.ShippingOptions,
    customs_options: units.CustomsOptions,
) -> None:
    def is_blank(value: typing.Optional[str]) -> bool:
        return not (value or "").strip()

    own_declaration = options.dhl_freight_sweden_customs_own_declaration.state
    joint_declaration = options.dhl_freight_sweden_customs_joint_declaration.state
    missing = {
        field: label
        for field, label, is_missing in [
            (
                "customs.options.eori_number",
                "the EORI number for standard customs handling",
                bool(options.dhl_freight_sweden_customs_handling_standard.state)
                and is_blank(customs_options.eori_number.state),
            ),
            (
                "dhl_freight_sweden_customs_own_declaration",
                "the customs identifier (MRN) for customer's own declaration",
                own_declaration is not None and is_blank(own_declaration),
            ),
            (
                "dhl_freight_sweden_customs_joint_declaration",
                "the joint-declaration identifier (SFID) for joint declaration",
                joint_declaration is not None and is_blank(joint_declaration),
            ),
        ]
        if is_missing
    }

    if any(missing):
        raise CustomsServiceIdentifierError(
            "The selected customs services require "
            f"{'; '.join(missing.values())}",
            details={
                field: dict(code="required", message=label)
                for field, label in missing.items()
            },
        )


def _service_point_party(
    options,
) -> typing.Optional[dhl_freight_sweden_req.PartyType]:
    service_point = options.dhl_freight_sweden_service_point.state

    if not service_point:
        return None

    # Keys double as the ``dhl_freight_sweden_service_point_{key}`` option names.
    details = dict(
        name=options.dhl_freight_sweden_service_point_name.state,
        street=options.dhl_freight_sweden_service_point_street.state,
        city=options.dhl_freight_sweden_service_point_city.state,
        postal_code=options.dhl_freight_sweden_service_point_postal_code.state,
        country_code=options.dhl_freight_sweden_service_point_country_code.state,
    )
    missing = [key for key, value in details.items() if not value]

    # DHL rejects an AccessPoint party without name and address (validation
    # errors 22001 and 22006, live sandbox 2026-09-10), so incomplete details
    # fail here with the missing option names instead of as a carrier 400.
    if any(missing):
        raise ServicePointDetailsError(
            "The service point option requires the full service point details; "
            f"missing {', '.join(missing)}",
            details={
                f"dhl_freight_sweden_service_point_{key}": dict(
                    code="required", message="service point detail is required"
                )
                for key in missing
            },
        )

    return dhl_freight_sweden_req.PartyType(
        id=service_point,
        type=provider_units.PartyType.AccessPoint.value,
        subType=provider_units.PartySubType.map(
            options.dhl_freight_sweden_service_point_type.state
            or provider_units.PartySubType.ParcelShop.value
        ).value_or_key,
        name=details["name"],
        address=dhl_freight_sweden_req.AddressType(
            street=details["street"],
            cityName=details["city"],
            # postalCode is generated as Optional[int]; keep it a string so
            # alphanumeric/space-bearing postal codes survive serialization.
            postalCode=str(details["postal_code"]) if details["postal_code"] else None,
            countryCode=details["country_code"],
        ),
    )


def _party(
    role: str, address, id: str = None
) -> dhl_freight_sweden_req.PartyType:
    return dhl_freight_sweden_req.PartyType(
        type=role,
        id=id,
        name=address.company_name or address.person_name,
        contactName=address.contact,
        vatEoriSocialSecurityNumber=address.tax_id,
        phone=address.phone_number,
        email=address.email,
        address=dhl_freight_sweden_req.AddressType(
            street=address.address_line1,
            additionalAddressInfo=address.address_line2,
            cityName=address.city,
            # postalCode is generated as Optional[int]; keep it a string so
            # alphanumeric/space-bearing postal codes survive serialization.
            postalCode=str(address.postal_code) if address.postal_code else None,
            countryCode=address.country_code,
        ),
    )
