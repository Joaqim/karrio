"""DHL Freight (SE API Farm) carrier test fixtures."""

import karrio.sdk as karrio


def _gateway(config: dict):
    return karrio.gateway["dhl_freight_sweden"].create(
        dict(
            id="123456789",
            test_mode=True,
            carrier_id="dhl_freight_sweden",
            client_key="TEST_CLIENT_KEY",
            account_number="1234567",
            config=config,
        )
    )


gateway = _gateway({})

# Connection-configured label type variant: the config value is metadata
# (the Print API has no format parameter), used as the last-resort tag.
zpl_gateway = _gateway({"label_type": "ZPL"})

# Booking pre-flight mode variants: the address_validation config gates the
# create_shipment route check only, never the unified validate_address.
# Mode values resolve case-insensitively; values naming no mode resolve to off.
warn_gateway = _gateway({"address_validation": "warn"})
enforce_gateway = _gateway({"address_validation": "enforce"})
warn_case_gateway = _gateway({"address_validation": "Warn"})
unrecognized_gateway = _gateway({"address_validation": "strict"})
