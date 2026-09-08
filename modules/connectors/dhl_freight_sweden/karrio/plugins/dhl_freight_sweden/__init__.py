from karrio.core.metadata import PluginMetadata

from karrio.mappers.dhl_freight_sweden.mapper import Mapper
from karrio.mappers.dhl_freight_sweden.proxy import Proxy
from karrio.mappers.dhl_freight_sweden.settings import Settings
import karrio.providers.dhl_freight_sweden.units as units
import karrio.providers.dhl_freight_sweden.utils as utils

# This METADATA object is used by Karrio to discover and register this plugin
# when loaded through Python entrypoints or local plugin directories.
# The entrypoint is defined in pyproject.toml under [project.entry-points."karrio.plugins"]
#
# Phase 0 scope: shipping only (book -> print). The API Farm exposes tracking
# via a public URL rather than a Karrio tracking feature, so no tracking
# capability is advertised. Capabilities are derived from the Proxy's public
# methods (create_shipment only).
METADATA = PluginMetadata(
    status="in-development",
    id="dhl_freight_sweden",
    label="DHL Freight Sweden",
    description="DHL Freight (Sweden API Farm) shipping integration for Karrio",
    # Integrations
    Mapper=Mapper,
    Proxy=Proxy,
    Settings=Settings,
    # Data Units
    is_hub=False,
    options=units.ShippingOption,
    services=units.ShippingService,
    connection_configs=units.ConnectionConfig,
    service_levels=units.DEFAULT_SERVICES,
    # Extra info
    website="https://www.dhl.com/se-en/home/our-divisions/freight.html",
    documentation="https://developer.dhl.com/api-reference/dhl-freight",
)
