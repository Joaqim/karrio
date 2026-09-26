# PRD: DHL Freight Sweden integration

| Field | Value |
|-------|-------|
| Project | DHL Freight Sweden carrier connector (`dhl_freight_sweden`) |
| Version | 2.0 |
| Date | 2026-09-24 |
| Status | Implemented |
| Owner | Joaqim Planstedt |
| Type | Integration |
| Reference | [AGENTS.md](../AGENTS.md), [CARRIER_INTEGRATION_GUIDE.md](../CARRIER_INTEGRATION_GUIDE.md) |

## Table of contents

1. [Executive summary](#executive-summary)
2. [Decisions](#decisions)
3. [Alternatives considered](#alternatives-considered)
4. [Technical design](#technical-design)
5. [Edge cases and failure modes](#edge-cases-and-failure-modes)
6. [Testing strategy](#testing-strategy)
7. [Risks and residuals](#risks-and-residuals)
8. [Appendix: API reference](#appendix-api-reference)

---

## Executive summary

The `dhl_freight_sweden` connector targets the DHL Freight Sweden API Farm (`freight-logistics.dhl.com`, OpenAPI 2.10.0).
It books a transport instruction and returns its label in one `shipment/create` call, surfaces a URL-only tracking link, rates from a static rate sheet, exposes connector-local product-match and service-point lookups for pickup-and-drop-off (PUDO) booking, and validates Swedish postal codes through the PostalCodes API.

DHL offers two front doors to the same freight API.
The DHL Group Developer Portal (`api.dhl.com`) uses OAuth2 and offers Unified Shipment Tracking; the API Farm uses a single `client-key` header with no token exchange.
The connector targets the API Farm only.

### Scope

| In scope | Out of scope |
|----------|--------------|
| Booking (`sendtransportinstruction`) and label print by id | Price quotes (pricequote API) |
| `client-key` authentication, per-connection host override | Tracking events (API Farm has no tracking endpoint) |
| URL-only tracking link in shipment `meta` | Cancellation and returns (no API Farm endpoint) |
| Static rate-sheet rating (universal rating mixin) | Pickup, manifest |
| Customs declaration mapping | Dangerous goods, temperature control, ADR |
| Service-point (AccessPoint) booking options | REST/GraphQL routes or dashboard UI for the lookups |
| Connector-local `find_product_matches`, `find_service_points` | `getservicepointdetails`, home-delivery locator |
| `validate_address` plus a config-gated booking pre-flight | Other PostalCodes endpoints (`validate`, `info`, `updated`) |

---

## Decisions

| # | Decision | Rationale and evidence |
|---|----------|------------------------|
| D1 | Target the API Farm; authenticate with a `client-key` header on every request | The vendored specs declare an `apiKey` scheme named `client-key` on every service; no token cache is needed |
| D2 | `shipment/create` books, then prints by id (`POST /print/printdocumentsbyid` with `{shipmentIds: [id]}`) | Keeps Karrio's one-step "create returns a label" contract without re-sending the shipment; live-verified 2026-09-10, `reports[].content` is base64 PDF |
| D3 | Tracking is URL-only: `meta.carrier_tracking_link` from `https://www.dhl.com/se-en/home/tracking/tracking-freight.html?submit=1&tracking-id={id}` | The API Farm has no tracking endpoint; DHL Freight Sweden's tracking FAQ links to this page, and the `?submit=1&tracking-id=` convention matches the sibling DHL connectors; `activetracing.dhl.com` was rejected (no deep-link parameter, login-gated) |
| D4 | Rating comes from a static rate sheet through `RatingMixinProxy`, with `rate=0.0` placeholders overridden by merchant prices | The server's shipment flow resolves connections on the `rating` capability, so the connector must expose it; the pricequote API stays out of scope |
| D5 | Rate-sheet zones follow the Product API destination footprint: 109 → 24 Europe countries, 112 → the same minus FR, 232 → 26 countries (adds CH/GB/GR, drops HR), 107 → Sweden, international freight → unrestricted | A Nordic-only zone hid the parcel family on SE→PL (live 2026-09-10); zones match the recipient, so the return lane 107 (EU→SE) is gated on SE and keeps `domicile=True` because the mixin classifies delivery in the account country as domicile |
| D6 | No geographic gate in the connector | DHL validation is authoritative; international products to and from SE are allowed |
| D7 | Label layout is selectable (`pageOptions.pageType`, default `Label`); raster format is not | The Print API has no format parameter and the account emits PDF A4 regardless of config (live 2026-09-10); the label type is derived from the decoded document's magic prefix, then the report `contentType`, then the `label_type` setting |
| D8 | Booking-required fields: `payerCode` (option, then `customs.incoterm`, then `1`), consignor party id = `account_number`, reference qualifier `CU`, commodity `procedureCode` default `1042`, one customs document always emitted | Live 400 validation dumps for products 601 and 102 plus the SE product manual v5.23; both corrected bookings returned 200 (2026-09-08); the separate FreightPayer party was dropped because its id is a customer number, not the payer code |
| D9 | A customs declaration has a single currency: `duty.currency`, else the commodities' common currency; per-line gaps are filled, conflicts raise a field error | Mixed per-line currencies corrupt `customsValueCurrency`/`invoiceCurrency` consistency |
| D10 | Service-point bookings require the full AccessPoint party (id, name, street, city, postal code, country code) via options; `subType` is `ParcelShop` (default) or `ParcelStation`; missing details raise a field error before any carrier call | DHL rejects an id-only party (22001 "Address/Name is mandatory for party AccessPoint", 22006 linehaul failure); full parties booked 103 SE and 109 DK (2026-09-10); the Consignee party stays alongside |
| D11 | The consignee phone is always sent; no client-side suppression by destination | DHL's label renderer applies the per-country print rules server-side (SE→DE and DK PUDO labels printed only the sender phone, 2026-09-10) |
| D12 | Universal `shipper_instructions`/`recipient_instructions` map to `pickupInstruction`/`deliveryInstruction` (max 140 each) with carrier-prefixed aliases; lengths pass through | Follows the SDK `INSTRUCTIONS` option convention; DHL validation is authoritative, as for `commodityDescription` |
| D13 | Product matches and service points are connector-local proxy methods (`find_product_matches`, `find_service_points`) that register no capability | Karrio has no unified lookup contract; this mirrors the postnord connector's local `find_service_points` and needs no server work; the methods also bypass the SDK origin gate, so EU-origin return lanes can be looked up |
| D14 | Lookup providers use hand-written builders and dict parsers, no generated schemas | The vendored specs type string enums as `integer` (NSwag quirk), so codegen would infer the wrong types |
| D15 | Product matches enforce the Consignor+Consignee requirement client-side | The rule exists only in the 200-response prose of the spec |
| D16 | Normalized service points expose both `id` and `service_point_id`; callers should prefer `service_point_id` | In PL `id` is a constant point-type code (`101` parcelshop, `501` parcelstation) while `servicePointId` is unique (`8005-PL-4516440`) |
| D17 | Service-point `locationType` `locker` maps to `ParcelStation`, every other type to `ParcelShop` | Transport-instruction spec text |
| D18 | Address validation implements the unified `validate_address` protocol over `GET /postalcodes/{cc}/{pc}/route` | Gives the fluent SDK wrapper, standalone gateway use, and the server `Address.validate` route without server or dashboard changes (dhl_express/mydhl precedent) |
| D19 | Validation semantics: unscoped → `success = bookable`; `options.service` scoped to 118 → `success = homeDeliveryParcel`; `complete_address` carries the route city | Product manual §10.14.8 ties `homeDeliveryParcel` to product 118 (Hemleverans Paket B2C), the only product with a documented per-product flag |
| D20 | `address_validation` connection config (`off` \| `warn` \| `enforce`, default `off`) gates a booking pre-flight for product 118 to Swedish consignees with a postal code | Roll out per connection without a redeploy; `off` makes no route call |
| D21 | Under `enforce` a definitive negative (flag false or a 4xx `ErrorResult`) blocks the booking; a lookup without a verdict (network error, timeout, 5xx) warns and proceeds in both modes | A PostalCodes outage must not take down bookings; the warning keeps persistent breakage visible |
| D22 | Mode values resolve case-insensitively; unrecognized values resolve to `off` | A bad stored value never silently enables the check |
| D23 | The mode enum is named `ServabilityMode` | `karrio.references.parse_type` classifies any enum whose name contains "Address" as the Address model, which the dashboard config renderer drops; a references regression test pins the string-enum classification |

---

## Alternatives considered

| Area | Alternative | Outcome |
|------|-------------|---------|
| Label | Book only, print in a separate document call | Rejected: consumers get no label at create time |
| Label | Print via full-payload `/print/printdocuments` | Replaced by print by id (D2); remains a fallback |
| Rating | No rating capability | Rejected: the shipment flow cannot resolve the connection (D4) |
| Lookups | REST routes for the lookups | Deferred: new serializer and permission surface with no consumer yet; can be added on top of the local methods |
| Lookups | Product matches as a live rating filter | Rejected: a carrier call per rate fetch; revisit if static zones drift from the catalog |
| Lookups | Product matches as booking pre-validation | Rejected: adds latency and a failure mode to a working booking path |
| Validation | Duck-typed `find_postal_code_route` only | Rejected: forfeits the unified protocol and still needs separate booking wiring |
| Validation | Unified `validate_address` without booking enforcement | Rejected: leaves the connection config nothing to gate |

---

## Technical design

### Architecture

```
                 ┌──────────────────── dhl_freight_sweden ────────────────────┐
 ShipmentRequest │ mapper ─▶ shipment/create.py ─▶ proxy.create_shipment      │
                 │                                   │ [pre-flight: D20-D22] │
                 │                                   ├─▶ GET  postalcodeapi   │
                 │                                   ├─▶ POST transportinstr. │
                 │                                   └─▶ POST printapi by id  │
 RateRequest     │ mapper ─▶ universal rating ◀─ DEFAULT_SERVICES (no call)   │
 AddressValid.   │ mapper ─▶ address.py ─▶ proxy.validate_address ─▶ GET route│
 lookup dicts    │ product_matches.py / service_points.py                     │
                 │   ─▶ proxy.find_product_matches / find_service_points      │
                 └───────────────┬────────────────────────────────────────────┘
                                 │ client-key: <api key>   (every request)
                                 ▼
          API Farm host (test_mode default, connection server_url override)
```

### Booking sequence

```
create_shipment(request)
  ├─ address_validation != off, product 118, consignee SE?
  │    └─▶ GET /postalcodeapi/v1/postalcodes/SE/{pc}/route
  │         enforce + negative → raise PostalCodeNotServableError (no booking)
  │         warn / no verdict → warning message, continue
  ├─▶ POST /transportinstructionapi/v1/transportinstruction/sendtransportinstruction
  │    ◀─ { transportInstruction: { id } }
  ├─▶ POST /printapi/v1/print/printdocumentsbyid { shipmentIds: [id], options }
  │    ◀─ { reports: [ { content (base64), contentType } ] }
  └─ ShipmentDetails(tracking_number=id, docs.label, label_type,
                     meta.carrier_tracking_link, meta.product_code) + messages
```

### Field reference

| Karrio field | Carrier field | Notes |
|--------------|---------------|-------|
| `shipper` | `parties[Consignor]` | `id` = `settings.account_number` (D8) |
| `recipient` | `parties[Consignee]` | postal code serialized as a string |
| `service` | `productCode` | string on the wire (`SPI` is non-numeric) |
| `parcels[]` | `pieces[]` | kg / cm, `numberOfPieces=1` per parcel; per-product minimum dimensions apply at DHL |
| `reference` | `references[]{qualifier: "CU"}` | consignor reference, 3-character qualifier |
| `options.dhl_freight_sweden_payer_code` | `payerCode.code` | domestic `1`/`3`/`4`, international Incoterms or Combiterm |
| `options.dhl_freight_sweden_label_page_type` | `pageOptions.pageType` | also a `label_page_type` connection config |
| `options.shipper_instructions` / `recipient_instructions` | `pickupInstruction` / `deliveryInstruction` | D12 |
| `options.dhl_freight_sweden_service_point[_type,_name,_street,_city,_postal_code,_country_code]` | `parties[AccessPoint]` | D10 |
| `options.dhl_freight_sweden_notification`, `pre_advice`, `tail_lift_unloading`, `insurance`, `doorstep_access_code` | `additionalServices` | |
| `customs.commodities[]` | `customsInformation.customsCommodities[]` | description (max 35), `hsItemId`, value and currency (D9), weight, quantity, origin, `procedureCode` (D8) |
| `customs` invoice data | `customsInformation.customsDocuments[0]` | `CommercialInvoice` when invoice data exists, else `ProformaInvoice`; `transportMovement=Export` for foreign destinations |

### Products

| Direction | Codes |
|-----------|-------|
| Domestic (SE) | 118 Hemleverans Paket B2C, 401 Home Delivery B2C, 402/502 Home Delivery C2B, 210 Pall, 102 Paket, 212 Parti, 103 Service Point B2C, 104 Service Point C2B, 209 Special, 211 Stycke |
| International | 202 Road Freight Standard, 232 Euroconnect Plus, 205 Road Freight Direct, 233 Road Freight Priority, 601 Home Delivery International B2C, 109 Parcel Connect B2C, 107 Parcel Return Connect C2B, 112 Parcel Connect Plus, SPI Standard Pallet International |

PUDO products are 103, 104 and 109; per the product catalog 109 DE allows `ParcelShop` only while DK allows both subtypes.
The connector imposes no product or country gating of its own.

### Lookup shapes

`find_product_matches` takes `shipper`/`recipient` (`postal_code`, `country_code`, both required), optional `parcels[]` and shipment totals, and returns dicts with `code`, `name`, `short_name`, flags, `from_countries`, `to_countries`, `to_country_postal_excludes`, `payer_codes`, `transportation_mode`, `sub_categories`, and `rules_for_country_delivery_types`.

`find_service_points` takes an `address` (`street`, `city`, `postal_code`, `country_code`) with optional `location_types`, `max_items`, `distance {value, unit}` and `piece` capacity filters, and returns dicts with `id`, `service_point_id`, `name`, `shop_name`, `type`, `address`, `coordinates`, `distance`, `distance_unit` and `service_types`.
The address fields map one-to-one onto the service-point booking options.

### Error shapes

`error.py` normalizes three shapes into messages: the transport-instruction `{status, validationErrors[], errorMessage}`, the Product API `BadRequestError {error, errors[]}`, and the PostalCodes `ErrorResult {status, errorCode, userMessage}`, which the live API returns in PascalCase although the spec declares camelCase.

---

## Edge cases and failure modes

| Case | Handling |
|------|----------|
| Booking succeeds, print fails | Print error surfaces as messages; details are still returned from the booking id |
| Multiple print reports | The first report is the label |
| Service-point option without full details | Field error naming the missing options, no carrier call (D10) |
| Invented service-point id or name | DHL does not registry-validate them at booking, so the shipment misroutes rather than fails; source them from `find_service_points` |
| Mixed commodity currencies | Field error (D9) |
| Product matches without both parties | Field error (D15) |
| Locator in-band `status`/`errorMessage` on a 200 | Parsed into messages; an empty point list is not an error |
| `postalCodeExcludes` per destination | Passed through to callers; `ServiceZone` supports inclusion lists only |
| Opening hours | Not available in Servicepoint API 2.10.0 |
| Pre-flight for a non-118 product, a non-SE consignee, or no postal code | Skipped with no route call |
| Route lookup network error, timeout, or 5xx | Warning, booking proceeds (D21) |
| Route 4xx `ErrorResult` (e.g. 16010 post code not found) | Definitive negative: `warn` annotates, `enforce` blocks |
| Shipper country differs from `account_country_code` (SE) | The unified SDK rejects rating and booking with `SHIPPING_SDK_ORIGIN_NOT_SERVICED_ERROR` before the connector runs; the connector-local lookups are not gated |

---

## Testing strategy

All tests are hermetic `unittest` suites with mocked `lib.request`; live sandbox probes supplied fixtures and decision evidence only.

| File | Coverage |
|------|----------|
| `test_shipment.py` | request build for the fixture products (102, 401, 103, 202, 232, 109 shop and station), customs, payer and currency guard, service-point guard, driver instructions, book-then-print proxy calls, response parse, label type resolution, error parse, and the pre-flight matrix |
| `test_rate.py` | rating capability, zone coverage per lane (SE→SE, DE, PL, DK, CH, and the PL→SE return lane) |
| `test_services.py` | service-level/enum alignment, carrier-id prefixes, zone invariants, capability stability (shipping + rating) |
| `test_product_matches.py`, `test_service_points.py` | request build, party guard, proxy call, parse, error parse |
| `test_address.py` | request build, route GET, scoped and unscoped parse, `ErrorResult` parse |
| `test_references.py` | `address_validation` is a string enum in the references payload |

```bash
python -m unittest discover -v -f modules/connectors/dhl_freight_sweden/tests
```

---

## Risks and residuals

| Item | Status |
|------|--------|
| Which service-point identifier DHL consumes downstream | Both are accepted at booking; routing derives from the party address; probe deliberately if a production misroute implicates the id |
| Tracking link auto-submit | The widget's auto-submit was not directly observed; confirm with one production id |
| PostalCodes production base path | The spec lists only the test host; production follows the sibling-API convention and is unverified |
| Static zones drift from the catalog | `find_product_matches` gives callers the authoritative answer |
| Reference payload freshness | The server caches reference models at boot, so a new connector version needs an API restart before the `address_validation` option appears in the dashboard |

---

## Appendix: API reference

The OpenAPI 2.10.0 specs (`transport-instruction`, `print-api`, `product-api`, `servicepoint-api`, `postalcode-api`, and the unused `pricequote-api` and `home-delivery-locator-api`) are vendored under `modules/connectors/dhl_freight_sweden/vendor/se-api-farm/`.

| Environment | Host |
|-------------|------|
| Test | `https://test-api.freight-logistics.dhl.com` |
| Production | `https://api.freight-logistics.dhl.com` |

| Endpoint (host + base path + operation) | Method | Use |
|-----------------------------------------|--------|-----|
| `/transportinstructionapi/v1/transportinstruction/sendtransportinstruction` | POST | booking |
| `/printapi/v1/print/printdocumentsbyid` | POST | label |
| `/productapi/v1/productmatches` | POST | product matches |
| `/servicepointlocatorapi/v1/servicepoint/findnearestservicepoints` | POST | service points |
| `/postalcodeapi/v1/postalcodes/{countryCode}/{postalCode}/route` | GET | address validation and pre-flight |
