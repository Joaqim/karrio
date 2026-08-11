"""Karrio DHL Freight client settings."""

import attr
import karrio.providers.dhl_freight.utils as provider_utils


@attr.s(auto_attribs=True)
class Settings(provider_utils.Settings):
    """DHL Freight connection settings."""

    # Add carrier specific API connection properties here
    api_key: str
    account_number: str = None

    # generic properties
    id: str = None
    test_mode: bool = False
    carrier_id: str = "dhl_freight"
    account_country_code: str = None
    metadata: dict = {}
    config: dict = {}
