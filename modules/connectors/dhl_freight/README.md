# karrio.dhl_freight

This package is a DHL Freight extension of the [karrio](https://pypi.org/project/karrio) multi carrier shipping SDK.

## Requirements

`Python 3.11+`

## Installation

```bash
pip install karrio.dhl_freight
```

## Usage

```python
import karrio.sdk as karrio
from karrio.mappers.dhl_freight.settings import Settings


# Initialize a carrier gateway
dhl_freight = karrio.gateway["dhl_freight"].create(
    Settings(
        ...
    )
)
```

Check the [Karrio Mutli-carrier SDK docs](https://docs.karrio.io) for Shipping API requests
