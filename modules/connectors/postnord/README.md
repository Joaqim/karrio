# karrio.postnord

This package is a PostNord extension of the [karrio](https://pypi.org/project/karrio) multi carrier shipping SDK.

## Requirements

`Python 3.11+`

## Installation

```bash
pip install karrio.postnord
```

## Usage

```python
import karrio.sdk as karrio
from karrio.mappers.postnord.settings import Settings


# Initialize a carrier gateway
postnord = karrio.gateway["postnord"].create(
    Settings(
        apikey="...",            # PostNord API key (single credential, sent as a query param)
        customer_number="...",   # PostNord customer number
        application_id="...",    # PostNord application id
        issuer_code="Z12",       # consignor issuer code (default "Z12")
        account_country_code="SE",
        test_mode=True,          # True -> sandbox (atapi2.postnord.com); False -> production (api2.postnord.com)
    )
)
```

Check the [Karrio Mutli-carrier SDK docs](https://docs.karrio.io) for Shipping API requests.
