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
        ...
    )
)
```

Check the [Karrio Mutli-carrier SDK docs](https://docs.karrio.io) for Shipping API requests
