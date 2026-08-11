# karrio.dhl_freight_sweden

This package is a DHL Freight Sweden extension of the [karrio](https://pypi.org/project/karrio) multi carrier shipping SDK.

It targets the DHL Freight Sweden API Farm and authenticates with a single `client-key` header (no token exchange).
Phase 0 covers shipment booking with a printed label and a URL-only tracking link surfaced through the shipment `meta`.

## Requirements

`Python 3.11+`

## Installation

```bash
pip install karrio.dhl_freight_sweden
```

## Usage

```python
import karrio.sdk as karrio
from karrio.mappers.dhl_freight_sweden.settings import Settings


# Initialize a carrier gateway
dhl_freight_sweden = karrio.gateway["dhl_freight_sweden"].create(
    Settings(
        client_key="...",       # DHL Freight Sweden API Farm client key (sent as the client-key header)
        account_number="...",    # freight-payer party id
        test_mode=True,          # sandbox (test-api.freight-logistics.dhl.com) vs production
    )
)
```

Check the [Karrio Mutli-carrier SDK docs](https://docs.karrio.io) for Shipping API requests
