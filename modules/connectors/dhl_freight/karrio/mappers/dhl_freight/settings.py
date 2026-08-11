"""Karrio DHL Freight client settings."""

import attr
import karrio.providers.dhl_freight.utils as provider_utils


@attr.s(auto_attribs=True)
class Settings(provider_utils.Settings):
    """DHL Freight (Sweden API Farm) connection settings."""

    # API Farm authenticates with a single API key sent as the `client-key` header.
    client_key: str
    account_number: str = None

    # generic properties
    id: str = None
    test_mode: bool = False
    carrier_id: str = "dhl_freight"
    account_country_code: str = None
    metadata: dict = {}
    config: dict = {}
