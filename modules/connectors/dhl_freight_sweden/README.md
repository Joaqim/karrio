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

## Connection settings

Connection settings are passed through the gateway's `config` dict (e.g. `config={"label_type": "ZPL"}`).

| Setting | Default | Notes |
|---------|---------|-------|
| `label_type` | `PDF` | Tags the returned document format when the carrier response does not identify it. The Print API exposes no format parameter, so the emitted format is governed by the DHL account (live-verified PDF A4, 2026-09-10); the connector derives the tag from the decoded document's magic prefix (`%PDF-`, `^XA`) first, then the report `contentType`, and uses this setting as the last resort. |

## Capabilities

| Capability | Notes |
|------------|-------|
| Shipping | Book then print by id in one `shipment/create` call. |
| Rating | Static rate sheet (universal rating mixin); no carrier call. |
| Product matches | Connector-local lookup (`gateway.proxy.find_product_matches`). |
| Service points | Connector-local lookup (`gateway.proxy.find_service_points`). |

## PUDO workflow lookups

The two lookups are connector-local: karrio has no unified service-points or
product-match interface, so the methods are called directly on the proxy and
register no connection capability.

```python
from karrio.providers.dhl_freight_sweden import (
    product_matches,
    service_points,
)

# 1. Eligible products for an address pair (optional piece criteria).
request = product_matches.product_matches_request(
    {
        "shipper": {"postal_code": "11120", "country_code": "SE"},
        "recipient": {"postal_code": "00-251", "country_code": "PL"},
        "parcels": [{"weight": 2.5, "length": 40, "width": 30, "height": 15}],
    },
    gateway.settings,
)
products, messages = product_matches.parse_product_matches_response(
    gateway.proxy.find_product_matches(request), gateway.settings
)

# 2. Nearest service points (address required; filters optional). Both
#    identifiers are returned: prefer `service_point_id` — in some countries
#    `id` is a constant point-type code rather than a unique identifier.
request = service_points.service_points_request(
    {
        "address": {
            "street": "Nowogrodzka 31",
            "city": "Warszawa",
            "postal_code": "00-251",
            "country_code": "PL",
        },
        "max_items": 5,
    },
    gateway.settings,
)
points, messages = service_points.parse_service_points_response(
    gateway.proxy.find_service_points(request), gateway.settings
)

# 3. Book with the chosen point: feed `service_point_id` (or `id`), `name`
#    and the address into the five service-point options — the shipment
#    create flow emits the complete AccessPoint party. A `locker` point
#    books with `service_point_type` "ParcelStation"; every other location
#    type books as "ParcelShop" (the default).
```

Service-point ids, names, and addresses must come from the locator: DHL does
not registry-validate them at booking, so invented values misroute rather
than fail. The locator exposes no opening hours (Servicepoint API 2.10.0).
