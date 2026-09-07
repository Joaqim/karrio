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
| `label_type` | `PDF` | Per-connection default label file format (`PDF` or `ZPL`), overridden per request by the shipment `label_type`. PostNord selects the format by endpoint path (`/labels/pdf` vs `/labels/zpl`). |
| `label_size` | — (unset) | PostNord physical label size, sent as the `labelType` query parameter: `standard` (190×105mm), `small` (75×105mm), or `ste` (PDF-only). Unset omits the parameter and PostNord defaults to `standard`. |
| `enable_transit_times` | `false` | Opt-in: call the Transit Time API to enrich `transit_days`/estimated delivery and filter by serviceability. Requires the key to be subscribed to the Transit Time product. |

## Shipment options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `entry_code` | string | — | PostNord entry code (door code) for the recipient's building, e.g. an apartment entrance code. Sent as a shipment `freeText` with usage code `ZDC`; PostNord prints it as "Ref 2" on the label and maps it to the consignee reference. Max 50 characters: a longer value rejects the booking with an `ENTRY_CODE_LENGTH` message before any call to PostNord. PostNord does not document which services accept it — the value is passed through unverified and is ignored by services without door-code support. |
| `language` | string | `en` | Booking/notification locale (lowercase ISO 639-1), sent as the query `locale` (SMS/Email language) and uppercased as the body `language` element (label/document text). Resolved per request, then from connection config, then (with `locale_by_recipient` enabled) from the recipient's country code. |
| `sms_notification` | bool | — | Opt in to PostNord notifying the consignee by SMS (`additionalServiceCode` `A3`, consignee `smsNo`). Least intrusive channel; notification language follows the booking locale. |
| `email_notification` | bool | — | Opt in to e-mail notification (`A4`, consignee `emailAddress`). |
| `postnord_notify_by_letter` | bool | — | Opt in to letter notification (`A2`, consignee address). |
| `postnord_notify_by_phone` | bool | — | Opt in to voice-call notification (`A9`, consignee `phoneNo`). |
| `postnord_driver_notification` | bool | — | Opt in to driver notification (`B8`, consignee `phoneNo`). |

PostNord has no notification-suppress flag: the consignee is notified only when a notification additional service is booked, and channels combine freely — setting only `sms_notification` books SMS and nothing else. `false` or omitted books nothing. Per-service rules apply (documented, not enforced here): PostNord documents Parcel (18) as requiring one of A2/A3/A4 and MyPack Home (17) as requiring consignee SMS-or-email contact data; PostNord validates these at booking.

## Supported operations

| Operation | Notes |
|-----------|-------|
| Rating | Static rates from the connection's service levels / server-side RateSheet (no carrier call by default). Optionally enriched with live transit times when `enable_transit_times` is on. |
| Shipment | Booking + label retrieval in one call (`/rest/shipment/v3/edi/labels/pdf`, or `/labels/zpl` when the resolved label type is ZPL). |
| Pickup | Courier collection booking (`Pickup.schedule`). |
| Tracking | Event-based via Track & Trace v7 (`findByIdentifier`); degrades to link-only (tracking URL + generic status) when the key isn't authorized for the T&T product. |
| Returns | Booked via the shipment create flow with a return service code. |
| Service points | Connector-local lookup (`gateway.proxy.find_service_points`). |

## Limitations

Tracking uses PostNord Track & Trace v7 (`findByIdentifier`) for full event history and normalized statuses. Per-product authorization applies (as with Transit Time): if the key is not subscribed to the Track & Trace product, tracking degrades gracefully to link-only — a tracking URL plus a single generic status, no events.

Cancellation is not available over the REST API: PostNord's REST `/v3/edi` ignores `updateIndicator: "Deletion"` and re-books a duplicate, and the id-based delete endpoint is absent from the published spec. The connector therefore never cancels and never reports a false success — cancel returns an explicit failure message pending PostNord's v3 REST reference manual.

Manifest is not supported: PostNord has no scan-form/end-of-day manifest endpoint. Use `Pickup.schedule` for courier collection.

Transit-time enrichment is opt-in (`enable_transit_times`, default off) because it requires a key subscribed to the Transit Time product. When enabled but unavailable, rating degrades gracefully to static transit days with a warning rather than failing.
