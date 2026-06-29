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

## Authentication

PostNord uses a single `apikey`, sent as a query parameter on every call (the Booking, Pickup, Service Points, and Tracking APIs are unsecured beyond the key).
Authorization is granted per API product: a key may be authorized for Booking but not for the Transit Time product, in which case that product returns `403 "Invalid API Key"`.
`test_mode` selects the host — `atapi2.postnord.com` (sandbox) when on, `api2.postnord.com` (production) when off — so a production key supplied to a test-mode connection is rejected by the sandbox rather than creating real shipments.

## Connection settings

| Setting | Required | Default | Description |
|---------|----------|---------|-------------|
| `apikey` | yes | — | PostNord API key (query-param credential) |
| `customer_number` | yes | — | PostNord customer number |
| `application_id` | yes | — | PostNord application id |
| `issuer_code` | no | `Z12` | Consignor issuer code |
| `account_country_code` | no | `SE` | Account country |
| `test_mode` | no | `false` | Route to sandbox vs production |

Connection config options (under the connection's config):

| Option | Default | Description |
|--------|---------|-------------|
| `label_type` | `PDF` | Label document type |
| `label_format` | `A4` | Label page format |
| `enable_transit_times` | `false` | Opt-in: call the Transit Time API to enrich `transit_days`/estimated delivery and filter by serviceability. Requires the key to be subscribed to the Transit Time product. |

## Supported operations

| Operation | Notes |
|-----------|-------|
| Rating | Static rates from the connection's service levels / server-side RateSheet (no carrier call by default). Optionally enriched with live transit times when `enable_transit_times` is on. |
| Shipment | Booking + PDF label retrieval in one call (`/rest/shipment/v3/edi/labels/pdf`). |
| Pickup | Courier collection booking (`Pickup.schedule`). |
| Tracking | Link-only: returns a tracking URL plus a generic status (see limitations). |
| Returns | Booked via the shipment create flow with a return service code. |
| Service points | Connector-local lookup (`gateway.proxy.find_service_points`). |

## Limitations

Tracking is link-only: the supplied Track & Trace URL API returns only a tracking URL, so `get_tracking` populates `tracking_url` plus a single generic status and emits no events. An events-based upgrade (Track & Trace v5/v7) is a planned follow-up.

Cancellation is not available over the REST API: PostNord's REST `/v3/edi` ignores `updateIndicator: "Deletion"` and re-books a duplicate, and the id-based delete endpoint is absent from the published spec. The connector therefore never cancels and never reports a false success — cancel returns an explicit failure message pending PostNord's v3 REST reference manual.

Manifest is not supported: PostNord has no scan-form/end-of-day manifest endpoint. Use `Pickup.schedule` for courier collection.

Transit-time enrichment is opt-in (`enable_transit_times`, default off) because it requires a key subscribed to the Transit Time product. When enabled but unavailable, rating degrades gracefully to static transit days with a warning rather than failing.
