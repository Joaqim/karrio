# karrio.dhl_freight_sweden

This package is a DHL Freight Sweden extension of the [karrio](https://pypi.org/project/karrio) multi carrier shipping SDK.

It targets the DHL Freight Sweden API Farm and authenticates with a single `client-key` header (no token exchange).
It covers shipment booking with a printed label and a URL-only tracking link surfaced through the shipment `meta`, static rate-sheet rating, service-point (PUDO) booking with connector-local lookups, and postal-code address validation.

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
        account_number="...",    # customer/agreement number, sent as the consignor party id
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
| `label_page_type` | `Label` | Print page layout (`Label`, `Label2xPortraitA4`, `Label3xLandscapeA4`, `LabelCompact`, `LabelCompact2x2PortraitA4`); the `dhl_freight_sweden_label_page_type` option overrides it per shipment. |
| `address_validation` | `off` | Booking pre-flight against the postal-code route: `off`, `warn`, or `enforce` (see [Address validation](#address-validation)). |
| `server_url` | | Overrides the API Farm host selected by `test_mode`. |

## Label printing behavior

The connector always transmits the consignee `phone_number` on the booking; DHL's label renderer decides per destination country whether it prints (live-verified 2026-09-10: suppressed for SE→DE, absent on a DK PUDO label — in both cases only the sender phone printed, as `Phn.`).
For parcelshop/parcelstation-addressed 109 shipments the mandatory "Customer information" label section is auto-composed from the Consignee party, so no connector input is needed.
`parties[].references` exists as the optional shipper-controlled free-text channel for custom label print text.
Phone format per product manual Appendix D: exactly one prefix (foreign country prefixes are fine), then digits, dash, and space only — dots, letters, and slash are forbidden.
The connector transmits `phone_number` as given, so callers should pre-format numbers to those constraints.

## Capabilities

| Capability | Notes |
|------------|-------|
| Shipping | Book then print by id in one `shipment/create` call. |
| Rating | Static rate sheet (universal rating mixin); no carrier call. |
| Address validation | `validate_address` over the PostalCodes API route lookup. |
| Product matches | Connector-local lookup (`gateway.proxy.find_product_matches`). |
| Service points | Connector-local lookup (`gateway.proxy.find_service_points`). |

The API Farm has no tracking or cancellation endpoint, so neither capability is advertised.

## PUDO one-click booking

A pickup-and-drop-off (PUDO) booking resolves an eligible service-point product, selects an acceptable service point near the recipient, and books the shipment with its label.
The two lookups are connector-local: karrio has no unified service-points or product-match interface, so the methods are called directly on the proxy and register no connection capability.
They also bypass the SDK origin check, so EU-origin return lanes can be looked up even though the unified rating and shipping entry points reject a shipper country other than the account country (`SHIPPING_SDK_ORIGIN_NOT_SERVICED_ERROR`).

```
  1. address pair (+ optional piece criteria)
     gateway.proxy.find_product_matches()   POST /productapi/v1/productmatches
     → eligible products; pick a service-point product (103/104/109)
  2. recipient address (+ radius, location types, capacity)
     gateway.proxy.find_service_points()    POST /servicepointlocatorapi/v1/servicepoint/findnearestservicepoints
     → normalized points; apply the acceptance policy; pick one
  3. unified ShipmentRequest with the service-point options
     karrio.Shipment.create(...).from_(gateway)   book + print by id
  on AccessPoint-related DHL validation errors, reject the point and retry with the next candidate
```

The service-point products are 103 (Service Point B2C, domestic), 104 (Service Point C2B, domestic), and 109 (Parcel Connect B2C, international).

### Step 1: eligible products

Product eligibility is authoritative at DHL, while the static rate sheet can drift, so query product matches for the address pair before offering a service choice.

```python
from karrio.providers.dhl_freight_sweden import product_matches

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
```

Both `shipper` and `recipient` (postal code and country) are required; the connector raises a field error before any carrier call when one is missing.
Each product carries `code`, `name`, `from_countries`, `to_countries`, `to_country_postal_excludes`, and `rules_for_country_delivery_types`; the delivery-type rules signal whether a product delivers to a service point.

### Step 2: service points

```python
from karrio.providers.dhl_freight_sweden import service_points

request = service_points.service_points_request(
    {
        "address": {
            "street": "Nowogrodzka 31",
            "city": "Warszawa",
            "postal_code": "00-251",
            "country_code": "PL",
        },
        "max_items": 5,
        "location_types": ["servicepoint", "locker"],   # optional
        "distance": {"value": 2, "unit": "km"},         # optional
        "piece": {"weight": 2.5, "length": 40, "width": 30, "height": 15},  # optional
    },
    gateway.settings,
)
points, messages = service_points.parse_service_points_response(
    gateway.proxy.find_service_points(request), gateway.settings
)
```

| Key | Content | Booking use |
|-----|---------|-------------|
| `service_point_id` | unique identifier (e.g. `8005-PL-4516440`) | `dhl_freight_sweden_service_point` (preferred) |
| `id` | a point-type code in some countries (e.g. `101`) | fallback identifier only |
| `name`, `shop_name` | point name | `dhl_freight_sweden_service_point_name` |
| `type` | `servicepoint`, `locker`, `postoffice`, or `postbank` | `locker` books as `ParcelStation`, every other type as `ParcelShop` |
| `address` | `{street, city, postal_code, country_code}` | the four address options |
| `coordinates` | `{latitude, longitude}` | display and sorting |
| `distance`, `distance_unit` | distance from the queried address | ranking |
| `service_types` | carrier service codes | informational |

Filter and rank candidates in this order so the fallback loop has a deterministic list:

1. `service_point_id` is present and the address has all four fields. DHL requires a complete AccessPoint party and does not registry-validate ids or names at booking, so incomplete or invented values misroute rather than fail.
2. Capacity: pass the parcel as the `piece` filter, and keep a local margin check for lockers.
3. Distance: apply a business threshold using `distance` and `distance_unit`.
4. Location type: product 109 to DE allows `ParcelShop` only per the product catalog, so enforce that locally for DE recipients.
5. Opening hours are not available (Servicepoint API 2.10.0), so do not promise them to recipients.

### Step 3: booking

```python
import karrio.core.models as models

point = accepted_points[0]

payload = {
    "service": "109",                      # or "103" domestic; enum keys also work
    "shipper": SHIPPER_ADDRESS,
    "recipient": RECIPIENT_ADDRESS,        # stays alongside the AccessPoint party
    "parcels": [{"weight": 2.5, "length": 40, "width": 30, "height": 15}],
    "options": {
        "dhl_freight_sweden_service_point": point["service_point_id"],
        "dhl_freight_sweden_service_point_type": (
            "ParcelStation" if point["type"] == "locker" else "ParcelShop"
        ),
        "dhl_freight_sweden_service_point_name": point["name"],
        "dhl_freight_sweden_service_point_street": point["address"]["street"],
        "dhl_freight_sweden_service_point_city": point["address"]["city"],
        "dhl_freight_sweden_service_point_postal_code": point["address"]["postal_code"],
        "dhl_freight_sweden_service_point_country_code": point["address"]["country_code"],
        # optional driver instructions (max 140 characters each):
        # "shipper_instructions" -> pickupInstruction,
        # "recipient_instructions" -> deliveryInstruction
    },
    # international lanes also need customs (commodities, incoterm); the payer
    # code resolves from dhl_freight_sweden_payer_code, else customs.incoterm,
    # else the consignor-pays default "1"
}

details, messages = (
    karrio.Shipment.create(models.ShipmentRequest(**payload))
    .from_(gateway)
    .parse()
)
```

`details.tracking_number` is the transport instruction id, `details.docs.label` the base64 label, and `details.meta["carrier_tracking_link"]` the public tracking URL.
The same options book identically through the server (`POST /api/v1/shipments`).

### Errors and the fallback loop

| Failure | Origin | Action |
|---------|--------|--------|
| "requires the full service point details; missing ..." | connector field error | fix the option mapping |
| "Address is mandatory for party AccessPoint" / "Name is mandatory ..." (22001) | DHL validation | reject the candidate, take the next |
| "Accesspoint party is required for product 103" | DHL validation | a service-point product was booked without the options; do not retry as-is |
| linehaul failure without postalCode (22006) | DHL validation | reject the candidate |
| product not offered or zone miss | rating or product matches | fall back to a non-PUDO service or re-quote |

Booking is not idempotent, so retry with the next candidate only when no booking id was returned.

### REST-only variant

A driver that cannot import the connector can split the flow: the lookups go directly to the API Farm, because karrio exposes no REST surface for them, and the booking goes through the karrio REST API.

The hosts are `https://test-api.freight-logistics.dhl.com` (test) and `https://api.freight-logistics.dhl.com` (production), and every call carries the `client-key` header.
Karrio never returns stored connection credentials over REST, so the driver needs the client key through its own secret channel.

The product matches body is the `MatchCriteria` shape that `product_matches_request` builds; both parties are required:

```json
{
  "parties": [
    {"type": "Consignor", "address": {"countryCode": "SE", "postalCode": "11120"}},
    {"type": "Consignee", "address": {"countryCode": "PL", "postalCode": "00-251"}}
  ],
  "pieces": [{"weight": 2.5, "length": 40, "width": 30, "height": 15}]
}
```

The service points body is the `NearestServicePointRequest` shape; the 200 body carries `servicePoints` plus in-band `status`/`errorMessage`:

```json
{
  "address": {
    "street": "Nowogrodzka", "cityName": "Warszawa",
    "postalCode": "00-251", "countryCode": "PL"
  },
  "maxNumberOfItems": 5,
  "locationTypes": ["servicepoint", "locker"],
  "distance": 2, "distanceUnit": "km",
  "piece": {"weight": 2.5, "length": 40, "width": 30, "height": 15}
}
```

The driver then does the normalization the connector would: prefer `servicePointId` over `id`, map `locationType` `locker` to `ParcelStation` and every other type to `ParcelShop`, and check the four address fields.

REST booking resolves the connection from the selected rate, so it is rate-first:

```bash
curl -X POST "$KARRIO/v1/proxy/rates" \
  -H "Authorization: Token $KARRIO_TOKEN" -H "Content-Type: application/json" \
  -d '{"shipper": {...}, "recipient": {...}, "parcels": [...],
       "services": ["dhl_freight_sweden_parcel_connect_b2c"]}'

curl -X POST "$KARRIO/v1/proxy/shipping" \
  -H "Authorization: Token $KARRIO_TOKEN" -H "Content-Type: application/json" \
  -d '{"shipper": {...}, "recipient": {...}, "parcels": [...],
       "selected_rate_id": "<id from the rates response>",
       "options": {"dhl_freight_sweden_service_point": "8005-PL-4516440", ...}}'
```

The `services` filter takes karrio service codes (`dhl_freight_sweden_parcel_connect_b2c`), not carrier codes.
The proxy endpoints require `person_name` and `address_line1` on both addresses.
The response carries `tracking_number`, `docs.label` (base64 PDF), and `meta.carrier_tracking_link`; `POST /api/v1/shipments` accepts the same payload when persistent shipment records are wanted.
The error table and fallback loop above apply unchanged.

## Address validation

Home-delivery shipments with product 118 (Hemleverans Paket B2C) are only servable to postal codes with home-delivery coverage, and the transport API does not fully validate postal codes at booking.
`GET /postalcodeapi/v1/postalcodes/{cc}/{pc}/route` resolves a postal code to its route, and the product manual (§10.14.8) ties the route's `homeDeliveryParcel` flag to product 118.

```python
details, messages = karrio.Address.validate(
    {
        "address": {"postal_code": "11120", "country_code": "SE"},
        "options": {"service": "dhl_freight_sweden_hemleverans_paket_b2c"},
    }
).from_(gateway).parse()
```

Scoped to product 118 through `options.service` (karrio service code or carrier product code `"118"`), `details.success` reports `homeDeliveryParcel`; unscoped, it reports the route's general `bookable` flag.
`details.complete_address` carries DHL's canonical city for the code.
A failed lookup returns the DHL `ErrorResult` as messages (the live API uses PascalCase `Status`, `ErrorCode`, `UserMessage`; 16010 is "post code not found", 16012 "not supported").

The `address_validation` connection setting adds the same check to `create_shipment` for product 118 to Swedish consignees:

| Mode | Behavior |
|------|----------|
| `off` (default) | no route lookup |
| `warn` | an unservable route or a 4xx `ErrorResult` adds a message; the shipment is booked |
| `enforce` | an unservable route or a 4xx `ErrorResult` blocks the booking with a field error |

A lookup that produces no verdict (network error, timeout, 5xx) adds a warning and books in both modes, so a PostalCodes API outage cannot block bookings.
Mode values resolve case-insensitively, and a value that names no mode resolves to `off`.
Roll out per connection by moving from `off` to `warn` to `enforce`.

The server builds its reference models at boot, so after deploying a new connector version restart the API before the dashboard's connection dialog shows the option.
`GET /v1/references` must list `connection_configs.dhl_freight_sweden.address_validation` with `type: "string"` and `enum: ["off", "warn", "enforce"]`.

## Operational notes

- The lookups are live carrier calls; cache per address pair when volume justifies it.
- The static rate-sheet prices are placeholders (rate 0.0) overridden by merchant prices; product matches give the authoritative service list.
- Sandbox bookings create real transport instructions in the DHL test system, so keep probes bounded.
