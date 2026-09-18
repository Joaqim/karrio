## Why

PostNord bookings made through karrio silently drop customs data today: the shipment request builder never reads `payload.customs`, so international shipments cannot produce CN22/CN23/customs-invoice documents, and consumers have no SDK path to declare customs against an existing booking via PostNord's `/rest/shipment/v3/customs/declaration` API.
The declaration belongs at booking time per our integration contract, with post-booking declaration available as an independent, consumer-owned capability.

## What Changes

- Map karrio's unified `customs` payload (commodities, content description, currencies) into the PostNord EDI booking request so the customs declaration rides the booking, matching PostNord's "EDI and Customs-information in the same request" flow.
- Implicit CN22 for export letters: booking the `postnord_export_letter` service (PostNord `UX`) with customs data attaches a standalone CN22 document to `docs.extra_documents` (the SDK's shipping-documents list), fetched from PostNord's by-id labels endpoint restricted to customs printouts; PDF and ZPL are both retrievable, following the booking's label format.
- Add connector-local proxy method(s) exposing PostNord's post-booking customs declaration endpoints (`/rest/shipment/v3/customs/declaration` and `/customs/declaration/pdf`) so consumers can independently declare customs for an existing booking and receive the resulting documents; correctness of post-booking calls is the consumer's responsibility, not karrio's.
- Surface the booking response's `printoutComposition` so the document kinds PostNord composed (cn22, cn23, customsInvoice, label, …) are visible to the unified response.
- No SDK or server changes: `Documents.extra_documents` / `ShippingDocument` and server-side persistence already exist.

## Capabilities

### New Capabilities

- `postnord/customs-declaration`: how the PostNord connector carries customs data at booking time, implicitly produces a standalone CN22 for export-letter services, exposes post-booking customs declaration as a consumer-owned proxy capability, and which document formats are produced.

### Modified Capabilities

<!-- None: no PostNord specs exist under openspec/specs/ yet. -->

## Impact

- `modules/connectors/postnord/karrio/providers/postnord/shipment/create.py` — customs mapping into the EDI booking request.
- `modules/connectors/postnord/karrio/mappers/postnord/proxy.py` — new post-booking customs-declaration proxy methods (pattern: existing `find_service_points` duck-typed methods).
- New provider module(s) under `modules/connectors/postnord/karrio/providers/postnord/` for customs declaration request/response mapping (e.g. `customs.py`), plus booking-response parsing of `printoutComposition`.
- `modules/connectors/postnord/schemas/` — extend booking schema fragments for the customs declaration models; regenerate via `./bin/run-generate-on modules/connectors/postnord` (source spec already local at `modules/connectors/postnord/vendor/booking.swagger.json`).
- `modules/connectors/postnord/tests/postnord/` — extend shipment-create fixtures with a customs block; new customs-declaration test module following the existing `patch("karrio.mappers.postnord.proxy.lib.request")` pattern.
- Consumers of the unified shipment response: bookings with customs now carry `docs.extra_documents` entries; no breaking change to existing fields.
