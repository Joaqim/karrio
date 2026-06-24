import typing
import karrio.lib as lib
import karrio.core.units as units
import karrio.core.models as models


class ConnectionConfig(lib.Enum):
    """PostNord connection configuration options."""

    label_type = lib.OptionEnum("label_type", str, "PDF")
    label_format = lib.OptionEnum("label_format", str, "A4")

    shipping_options = lib.OptionEnum("shipping_options", list)
    shipping_services = lib.OptionEnum("shipping_services", list)


class LabelType(lib.StrEnum):
    """PostNord supported label/printout formats."""

    PDF = "PDF"
    ZPL = "ZPL"

    """ Unified label type mapping """
    PDF_4x6 = PDF
    ZPL_4x6 = ZPL


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
    """PostNord basicServiceCode values."""

    postnord_mypack_home = "17"
    postnord_parcel = "18"
    postnord_mypack_collect = "19"
    postnord_return_pickup = "20"
    postnord_pallet = "52"
    postnord_postpaket_utrikes = "91"

    # Codes 11 and 86 appear as serviceCode values in worked bookingInstructions
    # example payloads in delivery-options.swagger.json (mailbox, express-mailbox),
    # the same instructions the Booking API consumes.
    postnord_mailbox = "11"
    postnord_express_mailbox = "86"

    # Codes 30 and 83 are documented in the delivery-options DeliveryType narrative
    # (home-small, groupage) and are not contradicted by the booking spec, which
    # accepts any basicServiceCode string.
    postnord_home_small = "30"
    postnord_groupage = "83"


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

    """ Unified Option type mapping """
    cash_on_delivery = postnord_cod
    insurance = postnord_insurance


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
    """Maps carrier tracking status codes to normalized Karrio statuses.

    The supplied tracking API is link-only (D7) and returns no events, so
    tracking yields a single neutral status. These mappings are retained for
    a future Track & Trace v5/v7 events upgrade.
    """

    in_transit = ["IN_TRANSIT"]


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
        international=False,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
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
        international=False,
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
]
