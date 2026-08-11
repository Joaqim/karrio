import karrio.lib as lib
import karrio.core as core


class Settings(core.Settings):
    """DHL Freight (Sweden API Farm) connection settings."""

    client_key: str
    account_number: str = None

    @property
    def carrier_name(self):
        return "dhl_freight_sweden"

    @property
    def server_url(self):
        """Base host for the SE API Farm.

        A per-connection ``server_url`` config value overrides the
        sandbox/production default, allowing a connection to pin a host.
        """
        return self.connection_config.server_url.state or (
            "https://test-api.freight-logistics.dhl.com"
            if self.test_mode
            else "https://api.freight-logistics.dhl.com"
        )

    @property
    def transport_instruction_url(self):
        return f"{self.server_url}/transportinstructionapi/v1"

    @property
    def print_url(self):
        return f"{self.server_url}/printapi/v1"

    @property
    def tracking_url(self):
        # The API Farm exposes no native shipment-tracking URL, so this uses the
        # public DHL Freight Sweden tracking widget keyed by shipment id.
        return "https://www.dhl.com/se-en/home/tracking/tracking-freight.html?submit=1&tracking-id={}"

    @property
    def connection_config(self) -> lib.units.Options:
        from karrio.providers.dhl_freight_sweden.units import ConnectionConfig

        return lib.to_connection_config(
            self.config or {},
            option_type=ConnectionConfig,
        )
