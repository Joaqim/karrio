"""Karrio DHL Freight client settings."""

import attr
import karrio.providers.dhl_freight_sweden.utils as provider_utils


@attr.s(auto_attribs=True)
class Settings(provider_utils.Settings):
    """DHL Freight (Sweden API Farm) connection settings."""

    # API Farm authenticates with a single API key sent as the `client-key` header.
    client_key: str
    account_number: str = None

    # generic properties
    id: str = None
    test_mode: bool = False
    carrier_id: str = "dhl_freight_sweden"
    account_country_code: str = "SE"
    metadata: dict = {}
    config: dict = {}
