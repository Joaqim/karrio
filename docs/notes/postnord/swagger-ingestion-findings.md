# PostNord connector — swagger ingestion findings

Synthesis of a four-agent ingestion pass over the PostNord API specifications, mapped against the connector's known integration gaps.
Sources ingested: `postnord-track-and-trace-api-v7-findbyreference.swagger.json`, `postnord-servicepoints-v5.swagger.json`, `postnord-delivery-options.swagger.json`, `postnord-transit-time-calculation-v1-and-v2.swagger.json`, `postnord-assign-items-to-loadcarriers.swagger.json` (all currently at repo root), plus a definitive re-scan of the vendored `modules/connectors/postnord/vendor/booking.swagger.json`.
All specs authenticate with a single `apikey` query parameter, consistent with the connector's existing model.

## Classification at a glance

| Gap / opportunity | Spec | Verdict | Effort |
|---|---|---|---|
| D8 Cancel | booking.swagger.json | Blocked — no endpoint exists | — |
| Pickup update/cancel | booking.swagger.json | Blocked — no endpoint exists | — |
| D7 Tracking events | track-and-trace v7 findByReference | Blocked on correct surface (wrong identifier) | M–L |
| Rating transit/ETA | transit-time v1/v2 | Actionable (needs D9 sign-off) | M |
| D6 Service Points | servicepoints v5 | Actionable (product-deferred) | S–M |
| Service-code enrichment | delivery-options | Actionable low-effort win | S |
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

Service-code enrichment from delivery-options is a low-effort win independent of any endpoint integration.
The `BookingInstructions` schema documents the service-code vocabulary, which already aligns with the connector's `ShippingService` enum (17 home, 18 parcel-b2b, 19 parcel-locker/service-point, 52 pallet) and adds codes not yet enumerated: 11 (mailbox), 30 (home-small), 86 (express-mailbox), 83 (groupage), additional-service 65.
These can enrich `units.py` enums after cross-checking against the booking spec (the delivery-options descriptions may lag PostNord's authoritative terms).
The endpoint itself (`POST /v1/deliveryoptions/bywarehouse`) is a checkout/dashboard-time API returning selectable options with localized text and time windows; full integration needs a checkout/frontend surface that does not exist today, so the immediate value is the code vocabulary, not the call.

Service Points (D6) remains the LSP-plugin shape, confirmed.
`servicepoints v5` offers three lookups — `GET /v5/servicepoints/{nearest/bycoordinates, bypostalcode, nearest/byaddress}` — returning a service-point model (id, name, visiting/delivery address, opening hours, easting/northing coordinates + SRID, `routeDistance`, drop-off/pickup/buy capabilities).
The convention-consistent path is a `find_service_points` proxy method plus an `is_service_point_provider()` detector mirroring `googlegeocoding`'s `is_address_validator()`, kept self-contained in the connector with no new core/Django/GraphQL contract — consistent with D6's deferral of a unified contract.
Note: the root `postnord-servicepoints-v5.swagger.json` differs from the vendored `vendor/servicepoints-v5.swagger.json` (same byte size, divergence at byte 38890); authoritative version needs confirmation before either is treated as canonical.

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

## Open file-handling question

The five root-level `*.swagger.json` files are untracked and pollute the repo root.
Four are new reference specs (track-and-trace v7, delivery-options, transit-time, assign-items-to-loadcarriers); the fifth (servicepoints v5) differs from the vendored copy.
Decision pending: vendor the applicable new specs into `modules/connectors/postnord/vendor/` (canonical home), reconcile the two servicepoints versions, and delete any genuine surplus.
