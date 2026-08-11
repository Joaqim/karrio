from karrio.core.metadata import PluginMetadata

from karrio.mappers.dhl_freight.mapper import Mapper
from karrio.mappers.dhl_freight.proxy import Proxy
from karrio.mappers.dhl_freight.settings import Settings
import karrio.providers.dhl_freight.units as units
import karrio.providers.dhl_freight.utils as utils


# This METADATA object is used by Karrio to discover and register this plugin
# when loaded through Python entrypoints or local plugin directories.
# The entrypoint is defined in pyproject.toml under [project.entry-points."karrio.plugins"]
METADATA = PluginMetadata(
    id="dhl_freight",
    label="DHL Freight",
    description="DHL Freight shipping integration for Karrio",
    # Integrations
    Mapper=Mapper,
    Proxy=Proxy,
    Settings=Settings,
    # Data Units
    is_hub=False,
    # options=units.ShippingOption,
    # services=units.ShippingService,
    connection_configs=units.ConnectionConfig,
    # Extra info
    website="",
    documentation="",
)
