import typing
import karrio.lib as lib
import karrio.core.units as units
import karrio.core.models as models


class LabelType(lib.StrEnum):
    """PostNord label file formats.

    PostNord selects the file format by *endpoint path* (``/labels/pdf`` vs
    ``/labels/zpl``), not by a body/query field, so this enum resolves the
    unified ``payload.label_type`` to the value threaded through
    ``Serializable.ctx`` to the proxy.
    """

    PDF = "PDF"
    ZPL = "ZPL"

    """ Unified label type mapping """
    PDF_4x6 = PDF
    ZPL_4x6 = ZPL


class LabelSize(lib.StrEnum):
    """PostNord physical label-size tokens (the ``labelType`` query parameter).

    ``standard`` (190×105mm) and ``small`` (75×105mm) apply to both endpoints;
    ``ste`` (190×105mm, special alignment) is PDF-only and ignored/defaulted on
    the ZPL endpoint. An unset size sends no ``labelType`` and PostNord defaults
    to ``standard``.
    """

    standard = "standard"
    small = "small"
    ste = "ste"


class ConnectionConfig(lib.Enum):
    """PostNord connection configuration options."""

    # Per-connection default label file format (PDF/ZPL); overridden per request
    # by payload.label_type. Selected by endpoint path in the proxy.
    label_type = lib.OptionEnum("label_type", LabelType, "PDF")
    # PostNord physical label size, sent as the labelType query parameter.
    # Unset -> no labelType param -> PostNord defaults to standard.
    label_size = lib.OptionEnum("label_size", LabelSize)
    # Booking/notification language (lowercase ISO 639-1); sent as the query
    # `locale` and uppercased as the body `language` element.
    language = lib.OptionEnum("language", str, "en")

    shipping_options = lib.OptionEnum("shipping_options", list)
    shipping_services = lib.OptionEnum("shipping_services", list)

    # When enabled, rate() calls PostNord's Transit Time API to enrich rates
    # with accurate transit days, estimated delivery, and per-service
    # bookability. Requires the apikey be subscribed to PostNord's Transit Time
    # product; otherwise the call returns 403 "Invalid API Key". Default off.
    enable_transit_times = lib.OptionEnum("enable_transit_times", bool, False)

    # Opt-in toggles for gated letter services (see SERVICE_AVAILABILITY). Off by
    # default so the rate catalog is unchanged until a merchant enables them.
    offer_tracked_letter = lib.OptionEnum("offer_tracked_letter", bool, False)
    offer_export_letter = lib.OptionEnum("offer_export_letter", bool, False)

    # When enabled, a shipment with no explicit options.language and no
    # config.language resolves its locale from the recipient's country code
    # (see CountryLocale); other countries fall back to "en". Default off.
    locale_by_recipient = lib.OptionEnum("locale_by_recipient", bool, False)


class CountryLocale:
    """Map recipient country codes to PostNord's Nordic locales.

    Keys are ISO 3166-1 alpha-2 country codes, not language codes
    (Denmark is DK; DA is the Danish language). Countries outside the
    mapping fall back to "en" via `lookup`.
    """

    MAPPING = dict(SE="sv", DK="da", NO="no", FI="fi")

    @classmethod
    def lookup(cls, country_code: typing.Optional[str]) -> typing.Optional[str]:
        return cls.MAPPING.get((country_code or "").upper())


class PackagingType(lib.StrEnum):
    """PostNord packageTypeCode values."""

    postnord_parcel = "PC"
    postnord_eur_pallet = "PE"
    postnord_half_pallet = "AF"
    postnord_quarter_pallet = "OA"
    postnord_special_pallet = "OF"
    postnord_cage_roll = "CW"
    postnord_box = "BX"
    postnord_envelope = "EN"

    """ Unified Packaging type mapping """
    envelope = postnord_envelope
    pak = postnord_parcel
    tube = postnord_parcel
    pallet = postnord_eur_pallet
    small_box = postnord_box
    medium_box = postnord_box
    large_box = postnord_box
    your_packaging = postnord_parcel


class ShippingService(lib.StrEnum):
    """PostNord basicServiceCode values.

    Reconciled against the authoritative merchant service catalog
    (issuerCode/service pairs). basicServiceCode is a free-form string in
    PostNord's Booking API (no closed enum), so these are the products the
    merchant's PostNord agreement exposes.
    """

    # Parcel — domestic & Nordic
    postnord_mypack_home = "17"
    postnord_mypack_home_no = "32"          # Norway variant of MyPack Home
    postnord_parcel = "18"
    postnord_parcel_special = "57"
    postnord_mypack_collect = "19"
    postnord_home_small = "11"              # delivery-options labels 11 "mailbox (SE)"
    postnord_mypack_home_small = "30"
    postnord_retail_delivery = "59"
    postnord_foretagspaket_comeback = "51"

    # Returns
    postnord_return_pickup = "20"
    postnord_return = "24"

    # Express / InNight
    postnord_innight = "48"
    postnord_innight_reverse = "49"

    # Pallet & freight
    postnord_pallet = "52"
    postnord_pallett_special = "53"
    postnord_tompallsdistribution = "37"    # delivery-options also uses "37" as an additionalServiceCode
    postnord_groupage = "83"
    postnord_road_freight_europe = "84"     # Denmark markets this code as "Groupage Small"
    postnord_part_loads = "85"

    # International parcel
    postnord_postpaket_utrikes = "91"       # "International Parcel"; Denmark markets as "EMS"

    # Letters & registered mail (bookable on the create path; not on the rate path)
    postnord_tracked = "04"                 # Denmark "PostNord Tracked" / "Tracked Letters"
    postnord_tracked_letter = "34"
    postnord_export_letter = "UX"           # "Export Letter Sweden"
    postnord_varubrev_first_class = "86"    # delivery-options labels 86 "express-mailbox (SE)"
    postnord_expressbrev = "LX"
    postnord_rek = "RR"                     # registered mail
    postnord_rek_retur = "RK"
    postnord_rek_extra = "RL"
    postnord_rekommanderet_brev = "RE"      # Denmark
    postnord_rekommanderet_quickbrev = "RQ" # Denmark
    postnord_varde = "VV"                   # insured value
    postnord_afleveringsattest = "AF"       # Denmark; PackagingType.postnord_half_pallet also uses "AF" (different API field)


class ShippingOption(lib.Enum):
    """PostNord additionalServiceCode values."""

    postnord_cod = lib.OptionEnum("A1", float, meta=dict(category="COD"))
    postnord_insurance = lib.OptionEnum("A5", float, meta=dict(category="INSURANCE"))
    postnord_optional_service_point = lib.OptionEnum("A7", bool)
    postnord_flexchange = lib.OptionEnum("C7", bool)
    postnord_collect_in_store = lib.OptionEnum("E4", bool)
    postnord_early_collect = lib.OptionEnum("F6", bool)

    # Code 65 is documented in the delivery-options DeliveryType narrative as the
    # additional service code carried by pallet (52) and groupage (83) options.
    postnord_pallet_groupage = lib.OptionEnum("65", bool, meta=dict(category="HANDLING"))

    # Consignee notification channels (general-descriptions.pdf; codes current
    # per Read This First v22.7). Each code uses the matching contact slot on
    # the consignee party; notification language follows the booking `locale`
    # query parameter. Notifications are opt-in: booking no code means no
    # notification, and channels combine freely (additive model).
    postnord_notify_by_letter = lib.OptionEnum("A2", bool)
    postnord_notify_by_sms = lib.OptionEnum("A3", bool)
    postnord_notify_by_email = lib.OptionEnum("A4", bool)
    postnord_notify_by_phone = lib.OptionEnum("A9", bool)
    postnord_driver_notification = lib.OptionEnum("B8", bool)

    """ Unified Option type mapping """
    cash_on_delivery = postnord_cod
    insurance = postnord_insurance
    sms_notification = postnord_notify_by_sms
    email_notification = postnord_notify_by_email


class CustomsOption(lib.Enum):
    """Unified ``customs.options`` registration identifiers.

    PostNord rejects a CN22 declaration carrying none of EORI/VOEC/IOSS
    (SACUS-BR-24062502), so these per-request values must reach the booking.
    ``voec_number`` and ``ioss_number`` are not members of the core
    ``karrio.core.units.CustomsOption`` enum, and the options helper drops
    keys unknown to both enums, so the booking converts customs options with
    this enum as the ``option_type`` (the seko pattern) to keep them visible.
    """

    eori_number = lib.OptionEnum("eori_number")
    voec_number = lib.OptionEnum("voec_number")
    ioss_number = lib.OptionEnum("ioss_number")


class CN22CategoryType:
    """Resolve unified ``customs.content_type`` to a CN22 ``categoryType``.

    PostNord documents six ``categoryOfItem.categoryType`` values
    (booking.swagger.json): GIFT, DOCUMENT, RETURNED GOODS, COMMERCIAL
    SAMPLE, OTHER, and SALE OF GOODS — the same six categories as karrio's
    ``CustomsContentType`` under different names. Both vocabularies are
    accepted, so ``merchandise`` and ``sale of goods`` both resolve to
    ``SALE OF GOODS``; resolution ignores case and whitespace. The swagger
    types categoryType as a free string validated server-side, so a value
    outside both vocabularies is returned verbatim rather than rejected or
    coerced.
    """

    VOCABULARY = (
        ("DOCUMENTS", "DOCUMENT"),
        ("GIFT", "GIFT"),
        ("SAMPLE", "COMMERCIAL SAMPLE"),
        ("MERCHANDISE", "SALE OF GOODS"),
        ("RETURN_MERCHANDISE", "RETURNED GOODS"),
        ("OTHER", "OTHER"),
    )

    MAPPING = {
        key: postnord_value
        for karrio_value, postnord_value in VOCABULARY
        for key in {karrio_value.casefold(), postnord_value.casefold()}
    }

    @classmethod
    def lookup(cls, content_type: typing.Optional[str]) -> typing.Optional[str]:
        return cls.MAPPING.get(
            " ".join((content_type or "").casefold().split()), content_type
        )


# Booking freeText usage code carrying the recipient's door/access code;
# PostNord prints it as "Ref 2" on the label (general-descriptions.pdf:
# "ZDC ... Door code", "Used in RFF for Consignee"). No PostNord source
# enumerates which services accept it, so the value is passed through
# unverified.
ENTRY_CODE_USAGE_CODE = "ZDC"

# 50 chars is generous for door codes and stays within address-line and
# full-name limits; longer values reject the booking before it is sent.
ENTRY_CODE_MAX_LENGTH = 50

# PostNord customs declarations accept at most 13 detailedDescription
# lines per item id (Booking Customs Information documentation). The
# swagger expresses no maxItems, so the documented limit is carried here
# and enforced before submission.
CUSTOMS_DECLARATION_MAX_LINES = 13

# PostNord takes a customs invoice instead of CN22/CN23 for parcel products,
# while letters and International Parcel carry CN22/CN23. The letter set is
# the closed group; every other service, including ones added later, is a
# parcel product. VV (insured value) and AF (Danish delivery receipt) are
# letter-mail variants.
LETTER_SERVICES = frozenset(
    {
        ShippingService.postnord_tracked,
        ShippingService.postnord_tracked_letter,
        ShippingService.postnord_export_letter,
        ShippingService.postnord_varubrev_first_class,
        ShippingService.postnord_expressbrev,
        ShippingService.postnord_rek,
        ShippingService.postnord_rek_retur,
        ShippingService.postnord_rek_extra,
        ShippingService.postnord_rekommanderet_brev,
        ShippingService.postnord_rekommanderet_quickbrev,
        ShippingService.postnord_varde,
        ShippingService.postnord_afleveringsattest,
    }
)
INTERNATIONAL_PARCEL_SERVICE = ShippingService.postnord_postpaket_utrikes


# Same EU VAT area definition as the DHL Freight Sweden connector. The SDK
# EUCountry enum lists Greece under its VAT prefix EL, so the ISO code GR is
# added, and Monaco, which Tullverket treats as EU, is likewise appended.
# Special fiscal territories outside the EU VAT area (Tullverket, EU
# customs and fiscal territories) either carry their own country code (AX,
# IC, GP, GF, MQ, RE, YT), which is absent from EUCountry, or are identified
# by postal-code range within a member state. Northern Ireland is inside
# the EU VAT area for goods and outside it for services; every caller here
# decides customs handling for goods, so its BT postcode area is admitted
# by prefix.
EU_VAT_AREA_COUNTRIES: typing.FrozenSet[str] = frozenset(
    [*(country.name for country in units.EUCountry), "GR", "MC"]
)
NON_EU_VAT_POSTAL_RANGES: typing.Tuple[typing.Tuple[str, int, int], ...] = (
    ("FI", 22000, 22999),  # Åland
    ("ES", 35000, 35999),  # Canary Islands (Las Palmas)
    ("ES", 38000, 38999),  # Canary Islands (Santa Cruz de Tenerife)
    ("ES", 51000, 51999),  # Ceuta
    ("ES", 52000, 52999),  # Melilla
    ("DE", 78266, 78266),  # Büsingen
    ("DE", 27498, 27498),  # Heligoland
    ("GR", 63086, 63086),  # Mount Athos
    ("IT", 23041, 23041),  # Livigno
    ("IT", 22061, 22061),  # Campione d'Italia
)
EU_VAT_POSTAL_PREFIXES: typing.Tuple[typing.Tuple[str, str], ...] = (
    ("GB", "BT"),  # Northern Ireland
)

# Warning code shared with the DHL Freight Sweden connector.
CUSTOMS_OMITTED_INTRA_EU = "customs_omitted_intra_eu"


def in_eu_vat_area(
    country_code: typing.Optional[str],
    postal_code: typing.Optional[str],
) -> bool:
    """Whether an address lies inside the EU VAT area for goods."""
    country = (country_code or "").upper()
    postal = str(postal_code or "").replace(" ", "")
    postal_number = int(postal) if postal.isdigit() else None

    inside_member_state = country in EU_VAT_AREA_COUNTRIES and not any(
        country == range_country
        and postal_number is not None
        and low <= postal_number <= high
        for range_country, low, high in NON_EU_VAT_POSTAL_RANGES
    )
    return inside_member_state or any(
        country == prefix_country and postal.upper().startswith(prefix)
        for prefix_country, prefix in EU_VAT_POSTAL_PREFIXES
    )


class CustomsStructure(lib.StrEnum):
    """Booking customs branch, named by its ``shipmentCustomsv2`` element."""

    cn22 = "customsDeclarationCN22"
    customs_invoice = "customsInvoice"


class CustomsInvoiceType(lib.StrEnum):
    """``customsInvoice.type``; selected literally by ``commercial_invoice``."""

    commercial = "COMMERCIAL"
    proforma = "PROFORMA"


class CustomsDeclarationType(lib.StrEnum):
    """``customsInvoice.declarationType`` values used by the connector."""

    invoice_export_declaration = "invoiceExportDeclaration"


class ExportReason(lib.StrEnum):
    """``invoice.reasonForExportation`` procedure codes (booking.swagger.json)."""

    permanent_export = "1000"


def customs_structure(basic_service_code: str) -> CustomsStructure:
    """Select the booking customs branch for a basicServiceCode."""
    if (
        basic_service_code in LETTER_SERVICES
        or basic_service_code == INTERNATIONAL_PARCEL_SERVICE
    ):
        return CustomsStructure.cn22

    return CustomsStructure.customs_invoice


def enforce_customs_declaration_lines(
    lines: int, field: str, item_id: typing.Optional[str] = None
) -> None:
    """Raise a FieldError when a declaration exceeds the customs line limit.

    One guard shared by the booking embedding and the post-booking
    declaration proxy so the two enforcement points cannot drift. The
    booking path names the customs field (no PostNord item id exists
    before allocation); the proxy path additionally names the
    caller-supplied item id.
    """
    if lines <= CUSTOMS_DECLARATION_MAX_LINES:
        return

    explanation = (
        f"{field} exceeds the {CUSTOMS_DECLARATION_MAX_LINES}-line "
        "customs declaration limit"
    )
    if item_id is not None:
        explanation = f"{explanation} for item {item_id}"

    raise lib.exceptions.FieldError({field: explanation})


def enforce_cn22_registration_numbers(options: units.CustomsOptions) -> None:
    """Raise a FieldError when a CN22 carries none of EORI, VOEC, or IOSS.

    PostNord rejects such a declaration with SACUS-BR-24062502 ("Customs
    CN22/CN23 should have either EORI, VOEC, IOSS"), observed live. The
    sandbox did not apply the rule to customs invoices, so this guard is
    scoped to the CN22 branch.
    """
    if any(options[key].state for key in CustomsOption.__members__):
        return

    raise lib.exceptions.FieldError(
        {
            "customs.options": (
                "a CN22 declaration requires at least one of "
                "eori_number, voec_number, or ioss_number"
            )
        }
    )


def enforce_customs_option_placement(options: dict) -> None:
    """Raise a FieldError when customs option keys sit in shipment options.

    Shipment-level option keys unknown to the booking options enum are
    dropped silently by the typed-options helper, so a registration number
    sent under ``options`` instead of ``customs.options`` never reaches the
    CN22 branch and PostNord rejects the booking (SACUS-BR-24062502 wants
    EORI, VOEC, or IOSS). Only truthy values reject: an empty value sends
    nothing under either placement.
    """
    misplaced = [
        key for key in CustomsOption.__members__ if (options or {}).get(key)
    ]
    if misplaced:
        raise lib.exceptions.FieldError(
            {
                f"options.{key}": (
                    "customs registration number; send it under customs.options"
                )
                for key in misplaced
            }
        )


def shipping_options_initializer(
    options: dict,
    package_options: units.ShippingOptions = None,
) -> units.ShippingOptions:
    """Apply default values to the given options."""

    if package_options is not None:
        options.update(package_options.content)

    def items_filter(key: str) -> bool:
        return key in ShippingOption  # type: ignore

    return units.ShippingOptions(options, ShippingOption, items_filter=items_filter)


class ServicePointType(lib.StrEnum):
    """PostNord Service Points v5 ``typeId`` values.

    Values are the documented service-point typeIds from the
    ``servicepoints-v5`` spec (``/v5/servicepoints/nearest/byaddress``
    ``typeId`` parameter). Used as a comma-separated filter on the lookup.
    """

    parcel_box = "2"
    cancelled_dk = "4"
    pakkeshop_med_salg_dk = "6"
    letter_office_se = "22"
    business_centre_se = "24"
    servicepoint_se = "25"
    servicepoint_no = "37"
    servicepoint_fi = "38"
    pakkeshop_dk = "44"
    collect_in_store = "51"
    delivery_office_se = "54"
    servicepoint_europe = "61"
    terminal_pickup_se = "73"
    letter_terminal_drop_off_se = "74"


class ServicePointContext(lib.StrEnum):
    """PostNord Service Points v5 ``context`` values.

    A context defines which kinds of service points the lookup returns
    (``context`` parameter on the nearest-servicepoints operations).
    """

    optional_service_point = "optionalservicepoint"
    early_collect = "earlycollect"
    labelless = "labelless"
    saturday_delivery = "saturdaydelivery"
    mypack_small = "mypacksmall"
    all = "all"


class TrackingStatus(lib.Enum):
    """Maps PostNord Track & Trace v7 ``ItemStatus`` values to Karrio statuses.

    The v7 ``findByIdentifier`` response carries an ``ItemStatus`` enum on each
    item (``status``/``eventStatus``). These 13 values are normalized to
    ``karrio.core.units.TrackerStatus`` names; unmapped/``OTHER`` values fall
    back to ``in_transit`` at the call site.
    """

    delivered = ["DELIVERED"]
    in_transit = ["EN_ROUTE", "INFORMED", "CREATED", "OTHER"]
    ready_for_pickup = ["AVAILABLE_FOR_DELIVERY", "AVAILABLE_FOR_DELIVERY_PAR_LOC"]
    delivery_delayed = ["DELAYED", "EXPECTED_DELAY"]
    delivery_failed = ["DELIVERY_IMPOSSIBLE", "DELIVERY_REFUSED"]
    return_to_sender = ["RETURNED"]
    on_hold = ["STOPPED"]


# PostNord publishes no live money-rate API; prices are per-merchant contract
# rates supplied server-side via Karrio's RateSheet. These defaults seed the
# rate-sheet catalog with the carrier's service levels and zones; the rate=0.0
# placeholders are overridden by the merchant's negotiated prices at runtime.
DEFAULT_SERVICES: typing.List[models.ServiceLevel] = [
    models.ServiceLevel(
        service_name="PostNord MyPack Home",
        service_code="postnord_mypack_home",
        carrier_service_code="17",
        currency="SEK",
        transit_days=2,
        domicile=True,
        international=False,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
    ),
    models.ServiceLevel(
        service_name="PostNord Parcel",
        service_code="postnord_parcel",
        carrier_service_code="18",
        currency="SEK",
        transit_days=2,
        domicile=True,
        international=False,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
    ),
    models.ServiceLevel(
        service_name="PostNord MyPack Collect",
        service_code="postnord_mypack_collect",
        carrier_service_code="19",
        currency="SEK",
        transit_days=3,
        domicile=True,
        international=True,
        zones=[models.ServiceZone(label="Nordic", rate=0.0, country_codes=["SE", "NO", "DK", "FI"])],
    ),
    models.ServiceLevel(
        service_name="PostNord Return Pickup",
        service_code="postnord_return_pickup",
        carrier_service_code="20",
        currency="SEK",
        transit_days=3,
        domicile=True,
        international=False,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
    ),
    models.ServiceLevel(
        service_name="PostNord Pallet",
        service_code="postnord_pallet",
        carrier_service_code="52",
        currency="SEK",
        transit_days=3,
        domicile=True,
        international=True,
        zones=[
            models.ServiceZone(
                label="Nordic",
                rate=0.0,
                country_codes=["SE", "NO", "DK", "FI"],
            )
        ],
    ),
    models.ServiceLevel(
        service_name="PostNord Postpaket Utrikes",
        service_code="postnord_postpaket_utrikes",
        carrier_service_code="91",
        currency="SEK",
        transit_days=5,
        domicile=False,
        international=True,
        zones=[models.ServiceZone(label="International", rate=0.0)],
    ),
    # Parcel & freight services; other letters and registered mail are
    # enum-only, not rated.
    models.ServiceLevel(
        service_name="PostNord Home Small",
        service_code="postnord_home_small",
        carrier_service_code="11",
        currency="SEK",
        transit_days=2,
        domicile=True,
        international=True,
        zones=[models.ServiceZone(label="Sweden/Norway", rate=0.0, country_codes=["SE", "NO"])],
    ),
    models.ServiceLevel(
        service_name="PostNord Return",
        service_code="postnord_return",
        carrier_service_code="24",
        currency="SEK",
        transit_days=3,
        domicile=True,
        international=True,
        zones=[models.ServiceZone(label="Nordic", rate=0.0, country_codes=["SE", "NO", "DK", "FI"])],
    ),
    models.ServiceLevel(
        service_name="PostNord MyPack Home Small",
        service_code="postnord_mypack_home_small",
        carrier_service_code="30",
        currency="SEK",
        transit_days=2,
        domicile=True,
        international=True,
        zones=[models.ServiceZone(label="Nordic", rate=0.0, country_codes=["SE", "NO", "DK"])],
    ),
    models.ServiceLevel(
        service_name="PostNord MyPack Home",
        service_code="postnord_mypack_home_no",
        carrier_service_code="32",
        currency="SEK",
        transit_days=2,
        domicile=True,
        international=True,
        zones=[models.ServiceZone(label="Norway", rate=0.0, country_codes=["NO"])],
    ),
    models.ServiceLevel(
        service_name="PostNord Tompallsdistribution",
        service_code="postnord_tompallsdistribution",
        carrier_service_code="37",
        currency="SEK",
        transit_days=3,
        domicile=True,
        international=False,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
    ),
    models.ServiceLevel(
        service_name="PostNord InNight",
        service_code="postnord_innight",
        carrier_service_code="48",
        currency="SEK",
        transit_days=1,
        domicile=True,
        international=True,
        zones=[models.ServiceZone(label="Nordic", rate=0.0, country_codes=["SE", "NO", "DK", "FI"])],
    ),
    models.ServiceLevel(
        service_name="PostNord InNight Reverse",
        service_code="postnord_innight_reverse",
        carrier_service_code="49",
        currency="SEK",
        transit_days=1,
        domicile=True,
        international=True,
        zones=[models.ServiceZone(label="Nordic", rate=0.0, country_codes=["SE", "NO", "FI"])],
    ),
    models.ServiceLevel(
        service_name="Företagspaket Comeback",
        service_code="postnord_foretagspaket_comeback",
        carrier_service_code="51",
        currency="SEK",
        transit_days=3,
        domicile=True,
        international=False,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
    ),
    models.ServiceLevel(
        service_name="PALL.ETT Special",
        service_code="postnord_pallett_special",
        carrier_service_code="53",
        currency="SEK",
        transit_days=3,
        domicile=True,
        international=False,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
    ),
    models.ServiceLevel(
        service_name="PostNord Parcel Special",
        service_code="postnord_parcel_special",
        carrier_service_code="57",
        currency="SEK",
        transit_days=2,
        domicile=True,
        international=True,
        zones=[models.ServiceZone(label="Nordic", rate=0.0, country_codes=["SE", "DK", "FI", "NO"])],
    ),
    models.ServiceLevel(
        service_name="Retail Delivery",
        service_code="postnord_retail_delivery",
        carrier_service_code="59",
        currency="SEK",
        transit_days=2,
        domicile=True,
        international=True,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE", "FI", "NO"])],
    ),
    models.ServiceLevel(
        service_name="PostNord Groupage",
        service_code="postnord_groupage",
        carrier_service_code="83",
        currency="SEK",
        transit_days=3,
        domicile=True,
        international=True,
        zones=[models.ServiceZone(label="Nordic", rate=0.0, country_codes=["SE", "NO", "DK", "FI"])],
    ),
    models.ServiceLevel(
        service_name="Road Freight Europe",
        service_code="postnord_road_freight_europe",
        carrier_service_code="84",
        currency="SEK",
        transit_days=4,
        domicile=False,
        international=True,
        zones=[models.ServiceZone(label="Europe", rate=0.0)],
    ),
    models.ServiceLevel(
        service_name="PostNord Part Loads",
        service_code="postnord_part_loads",
        carrier_service_code="85",
        currency="SEK",
        transit_days=4,
        domicile=False,
        international=True,
        zones=[models.ServiceZone(label="Nordic/Europe", rate=0.0, country_codes=["SE", "NO", "DK", "FI", "DE"])],
    ),
    # Letter products — rateable but gated (see SERVICE_AVAILABILITY): hidden
    # until the merchant opts in, and export letter is scoped to the Sweden
    # issuer. International, unrestricted zone; rate=0.0 overridden by rate sheet.
    models.ServiceLevel(
        service_name="PostNord Tracked Letter",
        service_code="postnord_tracked_letter",
        carrier_service_code="34",
        currency="SEK",
        transit_days=3,
        domicile=False,
        international=True,
        zones=[models.ServiceZone(label="International", rate=0.0)],
    ),
    models.ServiceLevel(
        service_name="PostNord Export Letter",
        service_code="postnord_export_letter",
        carrier_service_code="UX",
        currency="SEK",
        transit_days=4,
        domicile=False,
        international=True,
        zones=[models.ServiceZone(label="International", rate=0.0)],
    ),
]


class ServiceAvailabilityRule(typing.NamedTuple):
    """Gating rule applied to a rate-catalog ``service_code``.

    ``allowed_issuer_codes`` restricts the service to connections whose
    ``issuer_code`` is one of the given Z-codes (``None`` = any issuer).
    ``required_config`` names a ``ConnectionConfig`` bool option that must be
    enabled for the service to be offered (``None`` = always offered).
    """

    allowed_issuer_codes: typing.Optional[typing.FrozenSet[str]] = None
    required_config: typing.Optional[str] = None


# Services absent from this registry are unconditionally offered, preserving the
# default catalog. Gated entries surface only when their issuer/toggle rule passes.
SERVICE_AVAILABILITY: typing.Dict[str, ServiceAvailabilityRule] = {
    "postnord_tracked_letter": ServiceAvailabilityRule(
        required_config="offer_tracked_letter",
    ),
    "postnord_export_letter": ServiceAvailabilityRule(
        allowed_issuer_codes=frozenset({"Z12"}),
        required_config="offer_export_letter",
    ),
}


def is_service_available(
    service_code: str,
    issuer_code: str,
    connection_config: lib.units.Options,
) -> bool:
    """Return whether a catalog service is offered for this connection.

    A service not listed in ``SERVICE_AVAILABILITY`` is always available. A gated
    service is offered only when the connection's ``issuer_code`` is permitted
    and its required opt-in ``ConnectionConfig`` flag is enabled; a missing flag
    is treated as disabled (fail closed).
    """
    rule = SERVICE_AVAILABILITY.get(service_code)
    if rule is None:
        return True

    if (
        rule.allowed_issuer_codes is not None
        and issuer_code not in rule.allowed_issuer_codes
    ):
        return False

    if rule.required_config is not None:
        option = getattr(connection_config, rule.required_config, None)
        if option is None or not option.state:
            return False

    return True
