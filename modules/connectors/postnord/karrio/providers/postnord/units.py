import karrio.lib as lib
import karrio.core.units as units


class ConnectionConfig(lib.Enum):
    """PostNord connection configuration options."""

    # Static rate table backing config-driven rating (D1, Q3 per-connection).
    # Maps a basicServiceCode to its price, e.g.
    #   {"18": {"amount": 89.0, "currency": "SEK"}, "17": {...}}
    rate_table = lib.OptionEnum("rate_table", dict)

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


class ShippingOption(lib.Enum):
    """PostNord additionalServiceCode values."""

    postnord_cod = lib.OptionEnum("A1", float, meta=dict(category="COD"))
    postnord_insurance = lib.OptionEnum("A5", float, meta=dict(category="INSURANCE"))
    postnord_optional_service_point = lib.OptionEnum("A7", bool)
    postnord_flexchange = lib.OptionEnum("C7", bool)
    postnord_collect_in_store = lib.OptionEnum("E4", bool)
    postnord_early_collect = lib.OptionEnum("F6", bool)

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


class TrackingStatus(lib.Enum):
    """Maps carrier tracking status codes to normalized Karrio statuses.

    The supplied tracking API is link-only (D7) and returns no events, so
    tracking yields a single neutral status. These mappings are retained for
    a future Track & Trace v5/v7 events upgrade.
    """

    in_transit = ["IN_TRANSIT"]
