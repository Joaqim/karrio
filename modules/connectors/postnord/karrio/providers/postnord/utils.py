import karrio.lib as lib
import karrio.core as core


class IssuerCode(lib.Enum):
    """PostNord issuer/market codes identifying the entity holding the agreement."""

    Z11 = "Denmark"
    Z12 = "Sweden"
    Z13 = "Norway"
    Z14 = "Finland"
    ZDL = "Direct Link"


class Settings(core.Settings):
    """PostNord connection settings.

    The Booking (EDI), Pickup, Tracking, and Service Points APIs are
    ``SECURED: False`` and take ``apikey`` as a query parameter on every
    request, so a single ``apikey`` credential authorizes all operations.
    """

    apikey: str
    issuer_code: str = "Z12"
    customer_number: str = None

    @property
    def carrier_name(self):
        return "postnord"

    @property
    def server_url(self):
        return (
            "https://atapi2.postnord.com"
            if self.test_mode
            else "https://api2.postnord.com"
        )

    @property
    def tracking_url(self):
        return "https://tracking.postnord.com/{}/?id={}".format(
            (self.account_country_code or "se").lower(), "{}"
        )

    @property
    def connection_config(self) -> lib.units.Options:
        from karrio.providers.postnord.units import ConnectionConfig

        return lib.to_connection_config(
            self.config or {},
            option_type=ConnectionConfig,
        )
