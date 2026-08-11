"""DHL Freight (SE API Farm) carrier test fixtures."""

import karrio.sdk as karrio

gateway = karrio.gateway["dhl_freight"].create(
    dict(
        id="123456789",
        test_mode=True,
        carrier_id="dhl_freight",
        client_key="TEST_CLIENT_KEY",
        account_number="1234567",
    )
)
