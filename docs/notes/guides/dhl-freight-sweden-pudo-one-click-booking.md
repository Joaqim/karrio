# DHL Freight Sweden one-click PUDO booking via proxy tooling

Instruction guide for implementing the pickup-and-drop-off (PUDO) one-click booking:
one driver action that resolves an eligible service-point product, selects an
acceptable service point near the recipient, and books the shipment with its label.

The intended implementer is external workflow tooling — a Python driver running
where the `dhl_freight_sweden` connector is importable (the repository environment
or the deployed API container).
No dashboard UI is involved; that is a deliberate decision (2026-09-11), and the
UI surface (HTTP routes plus a picker) is deferred PUDO-PRD alternative B.

Reference material: the connector README documents the lookup calling conventions
(`modules/connectors/dhl_freight_sweden/README.md`); the integration PRD records the
booking field semantics and live-verified DHL behavior
(`PRDs/PRD_DHL_FREIGHT_INTEGRATION.md`); the PUDO workflow PRD records the lookup
design (`PRDs/DHL_FREIGHT_SWEDEN_PUDO_WORKFLOW.md`).

## Workflow overview

```
  workflow driver (Python, connector-local)
        │
        │ 1. address pair (+ optional piece criteria)
        ▼
  gateway.proxy.find_product_matches()
        │   POST /productapi/v1/productmatches
        │  → eligible products; pick a service-point product (103/104/109)
        │
        │ 2. recipient address (+ filters: radius, location types, capacity)
        ▼
  gateway.proxy.find_service_points()
        │   POST /servicepointlocatorapi/v1/servicepoint/findnearestservicepoints
        │  → normalized points; apply acceptance policy; pick one
        │
        │ 3. unified ShipmentRequest with the service-point options
        ▼
  karrio.Shipment.create(...).from_(gateway)      book + print by id, one call
        │  → ShipmentDetails: tracking id, label, meta.tracking_url
        ▼
  fallback loop: on AccessPoint-related DHL validation errors,
  reject the point and retry with the next candidate
```

## Prerequisites

- Python 3.11+ with the connector importable (`source bin/activate-env` in the repo,
  or the deployment container).
- Connection settings: the API Farm `client_key`, the `account_number`
  (customer/agreement number, carried as the Consignor party id), and `test_mode`
  selecting the sandbox host.
- Known PUDO product set: 103 (Service Point B2C, domestic SE), 104 (Service Point
  C2B, domestic SE), 109 (Parcel Connect B2C, international). Treat 112 as
  unverified until probed.
- Sandbox versus production: identical code paths, different host; every probe
  recorded below used the sandbox.

```python
import karrio.sdk as karrio
from karrio.mappers.dhl_freight_sweden.settings import Settings

gateway = karrio.gateway["dhl_freight_sweden"].create(
    Settings(
        client_key=CLIENT_KEY,
        account_number=ACCOUNT_NUMBER,
        test_mode=True,
    )
)
```

## Step 1 — resolve eligible products (recommended, optional)

Product eligibility is authoritative at DHL; the static rate sheet can drift.
Call product matches for the address pair before offering a service choice,
then keep only service-point products.

```python
from karrio.providers.dhl_freight_sweden import product_matches

request = product_matches.product_matches_request(
    {
        "shipper": {"postal_code": "11120", "country_code": "SE"},
        "recipient": {"postal_code": "00-251", "country_code": "PL"},
        # optional piece criteria sharpen the match
        "parcels": [{"weight": 2.5, "length": 40, "width": 30, "height": 15}],
    },
    gateway.settings,
)
products, messages = product_matches.parse_product_matches_response(
    gateway.proxy.find_product_matches(request), gateway.settings
)
```

Both `shipper` and `recipient` (postal code + country) are required; the connector
raises a field error before any carrier call when one is missing.
Each normalized product carries `code`, `name`, `from_countries`, `to_countries`,
`to_country_postal_excludes`, and `rules_for_country_delivery_types`; the delivery
type rules are the catalog-derived signal for "this product delivers to a service
point".
Note the origin gate bypass: these connector-local lookups work for EU-origin
return lanes that the unified SDK create/rating entry points would reject
(`SHIPPING_SDK_ORIGIN_NOT_SERVICED_ERROR`, account country SE).

## Step 2 — find acceptable service points

Query the locator with the recipient's full address, then apply an acceptance
policy to the normalized results.

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

Normalized point shape (one dict per point):

| Key | Content | Booking use |
|-----|---------|-------------|
| `service_point_id` | unique identifier (e.g. `8005-PL-4516440`) | `dhl_freight_sweden_service_point` (preferred) |
| `id` | point-type code in some countries (e.g. `101`) | fallback identifier only |
| `name`, `shop_name` | point name | `dhl_freight_sweden_service_point_name` |
| `type` | `servicepoint` \| `locker` \| `postoffice` \| `postbank` | subType derivation |
| `address` | `{street, city, postal_code, country_code}` | the four address options |
| `coordinates` | `{latitude, longitude}` | caller-side sorting/display |
| `distance`, `distance_unit` | distance from the queried address | acceptance ranking |
| `service_types` | carrier service codes | informational |

### Acceptance policy

A point is acceptable when all of the following hold; filter and rank in this
order so the fallback loop has a deterministic candidate list.

1. `service_point_id` is present and the `address` has all four fields — DHL
   requires a complete AccessPoint party (name + full address) and does not
   registry-validate the id, so incomplete or invented values misroute rather
   than fail.
2. Capacity: pass the parcel dimensions as the `piece` filter and let the carrier
   pre-filter, then keep a local margin check for lockers.
3. Distance: apply a business threshold (for example ≤ 2 km urban) using
   `distance`/`distance_unit`.
4. Location type: `locker` books as `service_point_type` `ParcelStation`; every
   other type books as `ParcelShop` (the connector default). Product 109 to DE
   allows `ParcelShop` only per the product catalog — enforce that locally when
   the recipient country is DE.
5. Opening hours are not available (Servicepoint API 2.10.0 gap) — do not promise
   recipient-facing hours from this data.

## Step 3 — book with the service-point options

Build the unified `ShipmentRequest` with the chosen service and the six
service-point options, then create through the same gateway (book + label print
in one call).

```python
import karrio.core.models as models

point = accepted_points[0]

payload = {
    "service": "109",                      # or "103" domestic; enum keys also work
    "shipper": SHIPPER_ADDRESS,            # phone formatted per manual appendix D
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
        # optional driver instructions land on the transport instruction:
        # "shipper_instructions" / "recipient_instructions" →
        # pickupInstruction / deliveryInstruction (max 140 characters each)
    },
    # international lanes additionally need customs (commodities, incoterm);
    # payer code resolves from dhl_freight_sweden_payer_code, else
    # customs.incoterm, else the consignor-pays default "1"
}

details, messages = (
    karrio.Shipment.create(models.ShipmentRequest(**payload))
    .from_(gateway)
    .parse()
)
```

`details.tracking_number` is the transport instruction id, `details.docs.label`
the base64 label document (PDF from this account), and
`details.meta["carrier_tracking_link"]` the public tracking URL.

The same options dict books identically through the deployed server
(`POST /api/v1/shipments` with the connection's carrier id) when the driver
prefers REST over the SDK for the create leg.

## Error handling and the fallback loop

| Failure | Origin | Driver action |
|---------|--------|---------------|
| "requires the full service point details; missing ..." | connector guard (field error) | programming error in option mapping; fix the driver |
| "Address is mandatory for party AccessPoint" / "Name is mandatory..." (22001) | DHL validation | point data incomplete; reject candidate, take next |
| "Accesspoint party is required for product 103" | DHL validation | service-point product booked without the options; the step-2/3 data is missing — do not retry as-is |
| linehaul failure without postalCode (22006) | DHL validation | address corrupted in mapping; reject candidate |
| product not offered / zone miss | rating or productmatches | non-PUDO fallback service or re-quote |

Keep the candidate list from step 2 and retry step 3 with the next acceptable
point on AccessPoint-related validation errors; booking itself is not idempotent,
so only retry when no booking id was returned.

## Operational notes

- The locator and product matches are live carrier calls; cache per address pair
  when volume justifies it (points are stable; hours unknown).
- The static rate sheet prices are placeholders (rate 0.0) overridden by merchant
  prices; product eligibility from step 1 is the authoritative service list.
- Labels from this account are PDF regardless of connection `label_type`; the
  connector sniffs the document magic prefix and tags accordingly.
- Sandbox bookings create real transport instructions in the test system —
  keep probes bounded and recorded under `docs/notes/evidence/`.

## Verifying the driver

- Hermetic: the connector suite pins all three legs against captured fixtures
  (`tests/dhl_freight_sweden/test_product_matches.py`,
  `test_service_points.py`, `test_shipment.py`); run
  `python -m unittest discover -v -f modules/connectors/dhl_freight_sweden/tests`.
- Live smoke: point the driver at the sandbox, run one address pair end to end,
  decode the returned label, and record the transcript as evidence; do not loop
  bookings.
