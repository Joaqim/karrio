"""DHL Freight (SE API Farm) carrier test fixtures."""

import karrio.sdk as karrio

gateway = karrio.gateway["dhl_freight_sweden"].create(
    dict(
        id="123456789",
        test_mode=True,
        carrier_id="dhl_freight_sweden",
        client_key="TEST_CLIENT_KEY",
        account_number="1234567",
    )
)

# Connection-configured label type variant: the config value is metadata
# (the Print API has no format parameter), used as the last-resort tag.
zpl_gateway = karrio.gateway["dhl_freight_sweden"].create(
    dict(
        id="123456789",
        test_mode=True,
        carrier_id="dhl_freight_sweden",
        client_key="TEST_CLIENT_KEY",
        account_number="1234567",
        config={"label_type": "ZPL"},
    )
)
