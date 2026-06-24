"""PostNord carrier tests fixtures."""

import karrio.sdk as karrio


gateway = karrio.gateway["postnord"].create(
    dict(
        id="123456789",
        test_mode=True,
        carrier_id="postnord",
        apikey="TEST_API_KEY",
        issuer_code="Z12",
        customer_number="00000000",
        account_country_code="SE",
        config=dict(
            rate_table={
                "18": {"amount": 89.0, "currency": "SEK"},
                "17": {"amount": 99.0, "currency": "SEK"},
            },
        ),
    )
)
