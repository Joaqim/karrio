import karrio.lib as lib
import karrio.core.units as units


class ConnectionConfig(lib.Enum):
    """DHL Freight connection configuration options."""

    server_url = lib.OptionEnum("server_url", str)
    # Informational/account-aligned label type. The API has no raster selector;
    # the actual document format is read from the Print response contentType.
    label_type = lib.OptionEnum("label_type", str, "PDF")
    # Print page layout, mapped to the Print API PageTypeEnum.
    label_page_type = lib.OptionEnum("label_page_type", str, "Label")
    shipping_options = lib.OptionEnum("shipping_options", list)
    shipping_services = lib.OptionEnum("shipping_services", list)


class PartyType(lib.StrEnum):
    """DHL Freight transport-instruction party roles."""

    Consignor = "Consignor"
    Pickup = "Pickup"
    Consignee = "Consignee"
    Delivery = "Delivery"
    AccessPoint = "AccessPoint"
    FreightPayer = "FreightPayer"


class PartySubType(lib.StrEnum):
    """DHL Freight access-point sub types (products 103/109)."""

    ParcelShop = "ParcelShop"
    ParcelStation = "ParcelStation"


class PageType(lib.StrEnum):
    """DHL Freight Print API page layouts (PageTypeEnum)."""

    Label = "Label"
    Label2xPortraitA4 = "Label2xPortraitA4"
    Label3xLandscapeA4 = "Label3xLandscapeA4"
    LabelCompact = "LabelCompact"
    LabelCompact2x2PortraitA4 = "LabelCompact2x2PortraitA4"


class ShippingService(lib.StrEnum):
    """DHL Freight product codes.

    Values are the carrier product codes as strings. They are intentionally
    not integers: the international "Standard Pallet International" product is
    non-numeric (``SPI``), and codes such as ``402``/``502`` must serialize as
    strings on the wire.
    """

    # Domestic (Sweden)
    dhl_freight_hemleverans_paket_b2c = "118"
    dhl_freight_home_delivery_b2c = "401"
    dhl_freight_home_delivery_c2b = "402"
    dhl_freight_home_delivery_c2b_502 = "502"
    dhl_freight_pall = "210"
    dhl_freight_paket = "102"
    dhl_freight_parti = "212"
    dhl_freight_service_point_b2c = "103"
    dhl_freight_service_point_c2b = "104"
    dhl_freight_special = "209"
    dhl_freight_stycke = "211"

    # International
    dhl_freight_road_freight_standard = "202"
    dhl_freight_euroconnect_plus = "232"
    dhl_freight_road_freight_direct = "205"
    dhl_freight_road_freight_priority = "233"
    dhl_freight_home_delivery_international_b2c = "601"
    dhl_freight_parcel_connect_b2c = "109"
    dhl_freight_parcel_return_connect_c2b = "107"
    dhl_freight_parcel_connect_plus = "112"
    dhl_freight_standard_pallet_international = "SPI"


class ShippingOption(lib.Enum):
    """DHL Freight shipping options."""

    # Additional services
    dhl_freight_notification = lib.OptionEnum(
        "notification", bool, meta=dict(category="NOTIFICATION")
    )
    dhl_freight_pre_advice = lib.OptionEnum("preAdvice", bool)
    dhl_freight_tail_lift_unloading = lib.OptionEnum("tailLiftUnloading", bool)
    dhl_freight_insurance = lib.OptionEnum(
        "insurance", float, meta=dict(category="INSURANCE")
    )
    # Access code (int) for home-delivery doorstep delivery.
    dhl_freight_doorstep_access_code = lib.OptionEnum("doorstepDelivery", int)

    # Access point / service point (products 103/109): the location id and the
    # access-point sub type (ParcelShop | ParcelStation).
    dhl_freight_service_point = lib.OptionEnum("servicepoint", str)
    dhl_freight_service_point_type = lib.OptionEnum("servicepointType", str)

    # Print page layout override (PageTypeEnum).
    dhl_freight_label_page_type = lib.OptionEnum("labelPageType", str)

    # Payer code (defaults to the connection account number when unset).
    dhl_freight_payer_code = lib.OptionEnum("payerCode", str)

    """ Unified Option type mapping """
    email_notification = dhl_freight_notification
    insurance = dhl_freight_insurance


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
