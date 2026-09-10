import typing

import karrio.lib as lib
import karrio.core.models as models
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


class LocationType(lib.StrEnum):
    """DHL Freight Servicepoint API location types (LocationTypeEnum)."""

    servicepoint = "servicepoint"
    locker = "locker"
    postoffice = "postoffice"
    postbank = "postbank"


# AccessPoint subType derivation from the transport-instruction spec:
# a locationType of "locker" books as a ParcelStation, every other
# location type books as a ParcelShop.
SUB_TYPE_BY_LOCATION_TYPE: typing.Dict[LocationType, PartySubType] = {
    LocationType.servicepoint: PartySubType.ParcelShop,
    LocationType.locker: PartySubType.ParcelStation,
    LocationType.postoffice: PartySubType.ParcelShop,
    LocationType.postbank: PartySubType.ParcelShop,
}


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
    dhl_freight_sweden_hemleverans_paket_b2c = "118"
    dhl_freight_sweden_home_delivery_b2c = "401"
    dhl_freight_sweden_home_delivery_c2b = "402"
    dhl_freight_sweden_home_delivery_c2b_502 = "502"
    dhl_freight_sweden_pall = "210"
    dhl_freight_sweden_paket = "102"
    dhl_freight_sweden_parti = "212"
    dhl_freight_sweden_service_point_b2c = "103"
    dhl_freight_sweden_service_point_c2b = "104"
    dhl_freight_sweden_special = "209"
    dhl_freight_sweden_stycke = "211"

    # International
    dhl_freight_sweden_road_freight_standard = "202"
    dhl_freight_sweden_euroconnect_plus = "232"
    dhl_freight_sweden_road_freight_direct = "205"
    dhl_freight_sweden_road_freight_priority = "233"
    dhl_freight_sweden_home_delivery_international_b2c = "601"
    dhl_freight_sweden_parcel_connect_b2c = "109"
    dhl_freight_sweden_parcel_return_connect_c2b = "107"
    dhl_freight_sweden_parcel_connect_plus = "112"
    dhl_freight_sweden_standard_pallet_international = "SPI"


class ShippingOption(lib.Enum):
    """DHL Freight shipping options."""

    # Additional services
    dhl_freight_sweden_notification = lib.OptionEnum(
        "notification", bool, meta=dict(category="NOTIFICATION")
    )
    dhl_freight_sweden_pre_advice = lib.OptionEnum("preAdvice", bool)
    dhl_freight_sweden_tail_lift_unloading = lib.OptionEnum("tailLiftUnloading", bool)
    dhl_freight_sweden_insurance = lib.OptionEnum(
        "insurance", float, meta=dict(category="INSURANCE")
    )
    # Access code (int) for home-delivery doorstep delivery.
    dhl_freight_sweden_doorstep_access_code = lib.OptionEnum("doorstepDelivery", int)

    # Access point / service point (products 103/109): the location id, the
    # access-point sub type (ParcelShop | ParcelStation), and the party
    # details DHL requires on the AccessPoint party (name + address).
    dhl_freight_sweden_service_point = lib.OptionEnum("servicepoint", str)
    dhl_freight_sweden_service_point_type = lib.OptionEnum("servicepointType", str)
    dhl_freight_sweden_service_point_name = lib.OptionEnum(
        "servicepointName", str, meta=dict(category="PUDO")
    )
    dhl_freight_sweden_service_point_street = lib.OptionEnum(
        "servicepointStreet", str, meta=dict(category="PUDO")
    )
    dhl_freight_sweden_service_point_city = lib.OptionEnum(
        "servicepointCity", str, meta=dict(category="PUDO")
    )
    dhl_freight_sweden_service_point_postal_code = lib.OptionEnum(
        "servicepointPostalCode", str, meta=dict(category="PUDO")
    )
    dhl_freight_sweden_service_point_country_code = lib.OptionEnum(
        "servicepointCountryCode", str, meta=dict(category="PUDO")
    )

    # Print page layout override (PageTypeEnum).
    dhl_freight_sweden_label_page_type = lib.OptionEnum("labelPageType", str)

    # Terms-of-delivery code: domestic products use the freight-payer codes
    # (1 consignor, 3 consignee, 4 third party); international products use
    # Incoterms/Combiterm codes (DAP, DDP, 022, 023, ...). Falls back to
    # customs.incoterm, then to the consignor-pays code "1".
    dhl_freight_sweden_payer_code = lib.OptionEnum("payerCode", str)

    # Customs procedure code per commodity (maxLength 4). "1042" is the
    # standard definitive-export procedure in the Swedish export declaration.
    dhl_freight_sweden_customs_procedure_code = lib.OptionEnum("procedureCode", str)

    """ Unified Option type mapping """
    email_notification = dhl_freight_sweden_notification
    insurance = dhl_freight_sweden_insurance


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


# The API Farm publishes no money-rate API for these products (the pricequote
# API is a later phase); these defaults seed the rate-sheet catalog with the
# carrier's service levels and zones so universal rating can present the
# product set. The rate=0.0 placeholders are overridden by the merchant's
# negotiated prices at runtime.
#
# Zone model (recipient-gated, account_country_code="SE"):
# - Domestic products: domicile-only, Sweden zone.
# - Outbound parcel family (109/112/232): both flags set so all lanes are
#   granted, Europe zone list from the product catalog gates the recipient.
# - Parcel Return Connect (107): the reverse lane to Sweden; the zone matches
#   the recipient, so Sweden.
# - International freight: international-only with an unrestricted zone
#   (no country list), so any non-SE destination rates without maintaining
#   a country list.
#
# Outbound destination footprints from the DHL Product API catalog
# (test host, fetched 2026-09-10: GET /productapi/v1/products/{code}
# toCountries, all from SE; every product below is isDomestic=false).
PARCEL_CONNECT_B2C_COUNTRIES = [
    "AT",
    "BE",
    "BG",
    "CZ",
    "DE",
    "DK",
    "EE",
    "ES",
    "FI",
    "FR",
    "HR",
    "HU",
    "IE",
    "IT",
    "LT",
    "LU",
    "LV",
    "NL",
    "NO",
    "PL",
    "PT",
    "RO",
    "SI",
    "SK",
]
PARCEL_CONNECT_PLUS_COUNTRIES = [
    "AT",
    "BE",
    "BG",
    "CZ",
    "DE",
    "DK",
    "EE",
    "ES",
    "FI",
    "HR",
    "HU",
    "IE",
    "IT",
    "LT",
    "LU",
    "LV",
    "NL",
    "NO",
    "PL",
    "PT",
    "RO",
    "SI",
    "SK",
]
EUROCONNECT_PLUS_COUNTRIES = [
    "AT",
    "BE",
    "BG",
    "CH",
    "CZ",
    "DE",
    "DK",
    "EE",
    "ES",
    "FI",
    "FR",
    "GB",
    "GR",
    "HU",
    "IE",
    "IT",
    "LT",
    "LU",
    "LV",
    "NL",
    "NO",
    "PL",
    "PT",
    "RO",
    "SI",
    "SK",
]

DEFAULT_SERVICES: typing.List[models.ServiceLevel] = [
    models.ServiceLevel(
        service_name="Hemleverans Paket B2C",
        service_code="dhl_freight_sweden_hemleverans_paket_b2c",
        carrier_service_code="118",
        currency="SEK",
        domicile=True,
        international=False,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
    ),
    models.ServiceLevel(
        service_name="Home Delivery B2C",
        service_code="dhl_freight_sweden_home_delivery_b2c",
        carrier_service_code="401",
        currency="SEK",
        domicile=True,
        international=False,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
    ),
    models.ServiceLevel(
        service_name="Home Delivery C2B",
        service_code="dhl_freight_sweden_home_delivery_c2b",
        carrier_service_code="402",
        currency="SEK",
        domicile=True,
        international=False,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
    ),
    models.ServiceLevel(
        service_name="Home Delivery C2B (502)",
        service_code="dhl_freight_sweden_home_delivery_c2b_502",
        carrier_service_code="502",
        currency="SEK",
        domicile=True,
        international=False,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
    ),
    models.ServiceLevel(
        service_name="Pall",
        service_code="dhl_freight_sweden_pall",
        carrier_service_code="210",
        currency="SEK",
        domicile=True,
        international=False,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
    ),
    models.ServiceLevel(
        service_name="Paket",
        service_code="dhl_freight_sweden_paket",
        carrier_service_code="102",
        currency="SEK",
        domicile=True,
        international=False,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
    ),
    models.ServiceLevel(
        service_name="Parti",
        service_code="dhl_freight_sweden_parti",
        carrier_service_code="212",
        currency="SEK",
        domicile=True,
        international=False,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
    ),
    models.ServiceLevel(
        service_name="Service Point B2C",
        service_code="dhl_freight_sweden_service_point_b2c",
        carrier_service_code="103",
        currency="SEK",
        domicile=True,
        international=False,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
    ),
    models.ServiceLevel(
        service_name="Service Point C2B",
        service_code="dhl_freight_sweden_service_point_c2b",
        carrier_service_code="104",
        currency="SEK",
        domicile=True,
        international=False,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
    ),
    models.ServiceLevel(
        service_name="Special",
        service_code="dhl_freight_sweden_special",
        carrier_service_code="209",
        currency="SEK",
        domicile=True,
        international=False,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
    ),
    models.ServiceLevel(
        service_name="Stycke",
        service_code="dhl_freight_sweden_stycke",
        carrier_service_code="211",
        currency="SEK",
        domicile=True,
        international=False,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
    ),
    models.ServiceLevel(
        service_name="Road Freight Standard",
        service_code="dhl_freight_sweden_road_freight_standard",
        carrier_service_code="202",
        currency="SEK",
        domicile=False,
        international=True,
        zones=[models.ServiceZone(label="International", rate=0.0)],
    ),
    models.ServiceLevel(
        service_name="Euroconnect Plus",
        service_code="dhl_freight_sweden_euroconnect_plus",
        carrier_service_code="232",
        currency="SEK",
        domicile=True,
        international=True,
        zones=[
            models.ServiceZone(
                label="Europe",
                rate=0.0,
                country_codes=EUROCONNECT_PLUS_COUNTRIES,
            )
        ],
    ),
    models.ServiceLevel(
        service_name="Road Freight Direct",
        service_code="dhl_freight_sweden_road_freight_direct",
        carrier_service_code="205",
        currency="SEK",
        domicile=False,
        international=True,
        zones=[models.ServiceZone(label="International", rate=0.0)],
    ),
    models.ServiceLevel(
        service_name="Road Freight Priority",
        service_code="dhl_freight_sweden_road_freight_priority",
        carrier_service_code="233",
        currency="SEK",
        domicile=False,
        international=True,
        zones=[models.ServiceZone(label="International", rate=0.0)],
    ),
    models.ServiceLevel(
        service_name="Home Delivery International B2C",
        service_code="dhl_freight_sweden_home_delivery_international_b2c",
        carrier_service_code="601",
        currency="SEK",
        domicile=False,
        international=True,
        zones=[models.ServiceZone(label="International", rate=0.0)],
    ),
    models.ServiceLevel(
        service_name="Parcel Connect B2C",
        service_code="dhl_freight_sweden_parcel_connect_b2c",
        carrier_service_code="109",
        currency="SEK",
        domicile=True,
        international=True,
        zones=[
            models.ServiceZone(
                label="Europe",
                rate=0.0,
                country_codes=PARCEL_CONNECT_B2C_COUNTRIES,
            )
        ],
    ),
    models.ServiceLevel(
        service_name="Parcel Return Connect C2B",
        service_code="dhl_freight_sweden_parcel_return_connect_c2b",
        carrier_service_code="107",
        currency="SEK",
        domicile=True,
        international=True,
        zones=[models.ServiceZone(label="Sweden", rate=0.0, country_codes=["SE"])],
    ),
    models.ServiceLevel(
        service_name="Parcel Connect Plus",
        service_code="dhl_freight_sweden_parcel_connect_plus",
        carrier_service_code="112",
        currency="SEK",
        domicile=True,
        international=True,
        zones=[
            models.ServiceZone(
                label="Europe",
                rate=0.0,
                country_codes=PARCEL_CONNECT_PLUS_COUNTRIES,
            )
        ],
    ),
    models.ServiceLevel(
        service_name="Standard Pallet International",
        service_code="dhl_freight_sweden_standard_pallet_international",
        carrier_service_code="SPI",
        currency="SEK",
        domicile=False,
        international=True,
        zones=[models.ServiceZone(label="International", rate=0.0)],
    ),
]
