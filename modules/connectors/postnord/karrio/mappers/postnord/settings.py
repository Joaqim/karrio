"""Karrio PostNord client settings."""

import attr
import karrio.providers.postnord.utils as provider_utils


@attr.s(auto_attribs=True)
class Settings(provider_utils.Settings):
    """PostNord connection settings."""

    # PostNord uses a single apikey credential (query param) for all operations.
    apikey: str = None
    issuer_code: str = "Z12"
    customer_number: str = None
    application_id: str = None

    # generic properties
    id: str = None
    test_mode: bool = False
    carrier_id: str = "postnord"
    account_country_code: str = "SE"
    metadata: dict = {}
    config: dict = {}
