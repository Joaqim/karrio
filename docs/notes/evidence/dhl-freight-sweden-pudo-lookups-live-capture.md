# DHL Freight Sweden PUDO lookups — live capture evidence

Bounded sandbox probes backing `PRDs/DHL_FREIGHT_SWEDEN_PUDO_WORKFLOW.md` (fixture provenance for the hermetic test suite).
All calls against `https://test-api.freight-logistics.dhl.com` with the standard `client-key` header on 2026-09-10.
No bookings were created; both endpoints are read-only lookups.

## Product matches (`POST /productapi/v1/productmatches`)

Request: Consignor `SE 11120` → Consignee `PL 00001`, one piece (2.5 kg, 40×30×15 cm).
Result: HTTP 200, six products — `109`, `202`, `112`, `601`, `233`, `232` (~154 KB).

Cross-checks recorded at capture time:

- The returned set contains exactly the three Europe-zoned parcel services the rate sheet now offers for SE→PL (109, 112, 232), alongside three unrestricted-zone services (202, 233, 601); 205 and SPI are offered statically but were not returned — the documented permissive-by-design divergence.
- Wire shapes matched the vendored spec: `transportationMode` carries only `name`; `toCountries[].postalCodeExcludes` sometimes empty-string; `payerCodes`/`subCategories` are code+name pairs; `rulesForCountryAndDeliveryTypes` carries per-country shipment/piece min-max rules.

The test fixture (`tests/dhl_freight_sweden/test_product_matches.py`) trims this capture to two representative products (109 with full rules; 601 with postal excludes and empty rule lists), values verbatim.

## Service points (`POST /servicepointlocatorapi/v1/servicepoint/findnearestservicepoints`)

Call 1 — unfiltered, Warszawa 00-251, `maxNumberOfItems: 5`: HTTP 200, `status: "OK"`, five points, all `locationType: "servicepoint"` (Żabka DHL Parcelshops), `distance` 0.06–0.39 km.
Call 2 — same address, `locationTypes: ["locker"]`, `maxNumberOfItems: 2`: HTTP 200, two DHL Parcelstation automats (`locationType: "locker"`), 0.66 and 1.08 km.

Identifier semantics discovered (PRD pending question #1): in the PL responses `id` is a constant point-type code — `101` on every parcelshop, `501` on every parcelstation — while `servicePointId` (`8005-PL-4516440` style) is the unique identifier.
Callers should prefer `service_point_id` when filling the service-point option.

The test fixture (`tests/dhl_freight_sweden/test_service_points.py`) merges one parcelshop from call 1 and one parcelstation from call 2 (both subType-mapping branches covered by real data), trimmed to normalizer-consumed fields, values verbatim.
The error fixture is constructed to the spec's in-band `status`/`errorMessage` shape; the endpoint declares no 4xx responses and no live error body was captured.
