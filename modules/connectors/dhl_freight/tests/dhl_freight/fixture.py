"""DHL Freight carrier tests fixtures."""

import karrio.sdk as karrio


gateway = karrio.gateway["dhl_freight"].create(
    dict(
        id="123456789",
        test_mode=True,
        carrier_id="dhl_freight",
        account_number="123456789",
        api_key="TEST_API_KEY",
    )
)