# PostNord connector — swagger ingestion findings

Synthesis of a four-agent ingestion pass over the PostNord API specifications, mapped against the connector's known integration gaps.
Sources ingested, now vendored under `modules/connectors/postnord/vendor/`: `track-and-trace-v7-findbyreference.swagger.json`, `delivery-options.swagger.json`, `transit-time-v1-v2.swagger.json`, `assign-items-to-loadcarriers.swagger.json`, plus a definitive re-scan of `booking.swagger.json` and the existing `servicepoints-v5.swagger.json`.
All specs authenticate with a single `apikey` query parameter, consistent with the connector's existing model.

## Classification at a glance

| Gap / opportunity | Spec | Verdict | Effort |
|---|---|---|---|
| D8 Cancel | booking.swagger.json | Blocked — no endpoint exists | — |
| Pickup update/cancel | booking.swagger.json | Blocked — no endpoint exists | — |
| D7 Tracking events | track-and-trace v7 findByReference | Blocked on correct surface (wrong identifier) | M–L |
| Rating transit/ETA | transit-time v1/v2 | Actionable (needs D9 sign-off) | M |
| D6 Service Points | servicepoints v5 | Actionable (product-deferred) | S–M |
| Service-code enrichment | delivery-options + service_codes.csv | Done — reconciled to units.py (7c24443f) | — |
| Manifest | assign-items-to-loadcarriers | Not applicable — confirms D10 | — |

## Confirmed dead ends (ground truth)

Cancel (D8) is definitively blocked. The vendored booking spec has 17 operations (16 POST, 1 GET) and zero DELETE/PUT/PATCH verbs.
The `deleteEdiRequest` schema (`{ids:[{id}]}`) is defined at `.definitions.deleteEdiRequest` but has zero `$ref` referrers — an orphan schema with no endpoint.
The only deletion affordance is `updateIndicator: "Deletion"` on the `ediInstruction` body, which routes to the same `POST /v3/edi` that was verified live to book a duplicate rather than delete.
The connector is already shaped correctly: `shipment/cancel.py` emits the exact `{ids:[{id}]}` body and `proxy.py` posts it as an inert placeholder; once PostNord supplies the real delete route, only the URL in `proxy.py::cancel_shipment` needs repointing — no serializer change.
This remains blocked pending PostNord's v3 REST reference manual.

Pickup update/cancel is definitively blocked. The pickup surface is three POSTs (`/v3/pickups`, `/v3/pickups/ids`, `/v4/sac/pickup/stopdate`) with no update or delete.
`pickupBooking.updateIndicator` is documented as "only Original is supported", so the `not_supported` placeholders are correct.

Assign-items-to-loadcarriers is not applicable and does not reverse D2/D10.
It is an internal warehouse `PUT /v3/edi` "split shipment" operation recording which physical item ids were loaded onto which load-carrier master id — ids the connector never holds, requiring separate EDI onboarding, producing an EDI `bookingId` rather than a manifest artifact.

## Actionable opportunities

Rating transit-time enrichment is the most concrete actionable item.
`GET /v2/transittime/addresstoaddress` (prefer v2 — it returns every requested service with per-service `errorMessage`, `isSupported`, and `isBookable` serviceability flags, unlike v1 which silently drops uncomputable services) takes origin/destination postal code + country, a `startTime` hand-over time, and `serviceCodes`, returning `estimatedTimeOfArrival` (exact `timeOfArrival` date-time or a `dayRangeOfArrival` min/max).
This maps to `RateDetails.transit_days` (compute from departure→arrival, or `dayRangeOfArrival.daysMaximum`) and an estimated-delivery date in `meta`.
The decision hinge is D9's load-bearing "rating performs no carrier call" property: a per-rate call breaks it (adds api-key dependency, latency, a failure mode), so the recommendation is an opt-in enrichment that preserves the static no-call default.
Open items before implementation: a source for `startTime` (default to now / next business day, or a new option), confirming the Nordic `basicServiceCode` values align with `DEFAULT_SERVICES`, and D9 sign-off.

### Service-code catalog — resolved via direct PostNord export

Service-code enrichment is resolved, superseding the tentative delivery-options vocabulary with a catalog exported directly from PostNord.
The `service_codes.csv` export (a 3,484-line file deduplicating to 32 distinct basic service codes) is the authoritative product catalog for the merchant's PostNord agreement.
For each code it carries a name, the issuer zones (Denmark, Finland, Norway, Sweden), an `adnlServiceCode` additional-service compatibility matrix, `allowedConsignorCountry`/`allowedConsigneeCountry` deliverability, and a `mandatory` flag.
No vendored swagger defines a closed enum for `basicServiceCode` — `booking.swagger.json` types it as a free-form string (minLength 1, maxLength 10, example "19") — so this export, not the swagger, is the authority for the service vocabulary.

The export corrects two labels the delivery-options spec supplied tentatively, confirming the earlier caveat that its descriptions may lag PostNord's authoritative terms: code 11 is "PostNord Home Small" (not "mailbox"), and code 86 is "Varubrev 1:a Klass" (not "express-mailbox"); code 30 is "MyPack Home Small".
Every code, including the letter and registered-mail products, carries real additional-service rows, indicating they are bookable services rather than documentation artifacts.
Two cross-field code reuses are recorded in `units.py`: the catalog lists 37 as a basic service ("Tompallsdistribution") while delivery-options uses "37" as an `additionalServiceCode` example, and the catalog's letter code "AF" (Afleveringsattest, Denmark) collides by string with `PackagingType.postnord_half_pallet = "AF"`, a `packageTypeCode` on a different API field.

The catalog was reconciled into `units.py`: `ShippingService` expanded from 10 to 32 codes (fixing the guessed 11/86 names and renaming 30 to `postnord_mypack_home_small`), and `DEFAULT_SERVICES` from 6 to 20 parcel/freight service levels with catalog-derived country zones, while letter and registered products remain enum-only (bookable but not rated).
The connection form's `issuer_code` was reconciled to a Z11–Z14 dropdown sourced from the export's `issuerCode` values.
Reconciled in commits `7c24443f` (service codes) and `17c20d66` (issuer dropdown).

The delivery-options endpoint itself (`POST /v1/deliveryoptions/bywarehouse`) remains a checkout/dashboard-time API returning selectable options with localized text and time windows; full integration still needs a checkout/frontend surface that does not exist today, so its value was the code vocabulary, now superseded by the direct export.

Service Points (D6) remains the LSP-plugin shape, confirmed.
`servicepoints v5` offers three lookups — `GET /v5/servicepoints/{nearest/bycoordinates, bypostalcode, nearest/byaddress}` — returning a service-point model (id, name, visiting/delivery address, opening hours, easting/northing coordinates + SRID, `routeDistance`, drop-off/pickup/buy capabilities).
The convention-consistent path is a `find_service_points` proxy method plus an `is_service_point_provider()` detector mirroring `googlegeocoding`'s `is_address_validator()`, kept self-contained in the connector with no new core/Django/GraphQL contract — consistent with D6's deferral of a unified contract.
The previously-flagged byte difference between the root and vendored `servicepoints-v5` copies was pure formatting — both are v5.0.14 and semantically identical (normalized `jq -S` diff is empty), so the redundant root copy was removed.

## Tracking events (D7) — blocked on the correct surface

The supplied Track & Trace v7 spec exposes one operation: `GET /v7/trackandtrace/customernumber/{customerNumber}/reference/{reference}/public`.
It keys on a `(customerNumber, reference)` pair, but the connector tracks by the PostNord-allocated `itemId` (the value returned as Karrio `tracking_number`); `get_tracking` receives bare item ids and has no natural `(customerNumber, reference)` pair at tracking time, and the spec's `reference` example is a slash-composite that may not equal `payload.reference` verbatim.
The natural surface for itemId-based tracking is a findByIdentifier/findByItemId v7 endpoint, which is not in this file.
The event model itself is rich and reusable regardless of surface: `shipments[].items[].events[]` with `eventTime`, `eventCode`, `eventDescription`, `location` (name/city/postcode/countryCode), plus item-level `status`/`eventStatus` over a 13-value enum (`DELIVERED`, `EN_ROUTE`, `AVAILABLE_FOR_DELIVERY`, `DELAYED`, `DELIVERY_IMPOSSIBLE`, `RETURNED`, …) and `acceptor`/`signature` for `signed_by`.
Implementation would rewrite `tracking.py` (`_extract_details` + `tracking_request`), replace the placeholder `TrackingStatus` in `units.py` with the full normalized mapping, repoint `proxy.py::get_tracking` to the v7 path, and regenerate a `tracking_response` schema.
Action before committing: obtain the T&T v7 findByIdentifier (by itemId/shipmentId) spec, or confirm with PostNord how to recover the indexed `reference` for an itemId.

## Newly discovered capabilities (beyond the tracked gaps)

The booking spec scan surfaced operations not currently used by the connector:

- Label reprint / document retrieval: `POST /v3/labels/ids/{pdf,zpl}` re-fetch existing labels by id without rebooking; `/v3/labels/printoptions/ids` returns print options. Could back a reprint feature.
- Dedicated returns surface: `POST /v3/returns/edi` (+ zpl/pdf label variants). The connector's `return_shipment` currently delegates to the booking `create` flow; this dedicated endpoint may be the more correct target for returns.
- Pickup cutoff lookup: `POST /v4/sac/pickup/stopdate` returns the next valid pickup/booking cutoff datetime — useful to validate a pickup-ready date before `createPickups`.
- Customs and dangerous goods: `POST /v3/customs/declaration{,/pdf}`, `/v3/customs/consolidation`, `/v3/dangerousgoods` for international/DG declarations.

## Spec file handling (resolved)

The four new reference specs (track-and-trace v7, delivery-options, transit-time, assign-items-to-loadcarriers) were vendored into `modules/connectors/postnord/vendor/` alongside the existing booking/servicepoints/tracking-url specs, clearing the repo root.
The redundant root `servicepoints-v5` copy (identical to the vendored one modulo formatting) was removed.
