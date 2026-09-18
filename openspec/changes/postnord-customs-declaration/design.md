## Context

See proposal.md for motivation.
Today the PostNord connector books via `POST /rest/shipment/v3/edi/labels/{pdf,zpl}` with an `ediInstruction` body built in `karrio/providers/postnord/shipment/create.py:128-318`; unified `payload.customs` is silently dropped, `printoutComposition` in the response schema (`karrio/schemas/postnord/shipment_response.py:87`) is unparsed, and `parse_response` returns `Documents(label=...)` only.
The full Booking v3 spec is already vendored at `modules/connectors/postnord/vendor/booking.swagger.json` and establishes three facts that shape this design:

- The booking request itself accepts customs inline: `shipment[]` items are `shipmentCustomsv2` (SW:5942) whose properties include `customsDeclarationCN22`, `customsDeclarationCN23`, `customsInvoice`, `customsTvinn`, `customsTransit` — the same shared definitions used by the standalone declaration endpoints.
- Post-booking declaration exists as `POST /v3/customs/declaration` (digital; requires prior EDI for the item id, `ids[]` maxItems 1, one declaration branch per object) and `POST /v3/customs/declaration/pdf` (PDF-only; adds `paperSize`/`rotate`/`multiPDF`/alignment params; response includes a `labelPrintout` array).
- Documents for existing ids are retrievable via `POST /v3/labels/ids/{pdf,zpl}` with `definePrintout` values including `onlyCustomsDeclarations`, `onlyCustomsInvoice`, `onlyLabels`.

Downstream plumbing already exists: `Documents.extra_documents: List[ShippingDocument]` with `ShippingDocument(category, format, print_format, base64, url)` (`modules/sdk/karrio/core/models.py:430-450`), the provider-side construction pattern (`dhl_parcel_de shipment/create.py:63-80`), server persistence of `extra_documents` (`modules/manager/karrio/server/manager/models.py:969`, `serializers/shipment.py:304-313`), and the connector-local proxy-method precedent (`find_service_points`, postnord `proxy.py:194-204`, discovered via `Gateway.proxy_methods`).

## Goals / Non-Goals

**Goals:**

- Carry unified customs data in the booking request (declaration at booking, per the integration contract).
- Attach a standalone customs document (CN22 first) to `docs.extra_documents` for export-letter (`UX`) bookings, in the booking's label format family (PDF or ZPL).
- Expose post-booking customs declaration as connector-local proxy methods with documents returned in the unified documents structure.
- Fail fast on the documented 13-lines-per-item-id limit.

**Non-Goals:**

- No SDK or server changes (`extra_documents` plumbing and persistence already exist).
- No automatic CN23 or customs-invoice embedding at booking; those branches stay reachable through the post-booking proxy where the caller chooses the branch explicitly.
- No EORI/VAT/IOSS collection beyond what unified customs already carries; no dashboard UI.
- No lifecycle management of declarations after creation: karrio does not reconcile, regenerate, verify, or retract.
- Consolidation and dangerous-goods endpoints are out of scope.

## Decisions

### D1: Declaration rides the booking EDI, CN22 branch first

Map unified `customs` into the `customsDeclarationCN22` branch of each `shipmentCustomsv2` entry whenever customs data is present, for any service.
CN22 is the branch the first functional goal needs (export letters) and the only one whose required fields (`detailedDescription`, `totalValue`) are fully derivable from the unified model.
CN23 additionally requires `postalCharges` and per-item ids, and `customsInvoice` requires a seller block with `vatNo`/`partyIdentification`/`contacts` the unified model does not reliably hold — both are deferred to the post-booking proxy where the caller supplies branch-specific input explicitly.

Alternative considered: choose the branch per shipment (CN22 ≤ 300 SDR, CN23 above, `commercial_invoice: true` → invoice).
Rejected for v1: it invents threshold semantics the local specs do not document and multiplies mapping surface before the first goal is verified live.

Field mapping (unified → `customsDeclarationCN22`, SW:5176):

| Unified field | CN22 field |
|---|---|
| `commodities[].title or description` | `detailedDescription[].content` |
| `commodities[].quantity` | `detailedDescription[].quantity` |
| `commodities[].weight` + `weight_unit` | `detailedDescription[].grossWeight {value, unit=KGM}` |
| `commodities[].value_amount` / `value_currency` | `detailedDescription[].value {amount, currency}` |
| `commodities[].hs_code` | `detailedDescription[].hsTariffNumber` |
| `commodities[].origin_country` | `detailedDescription[].countryCode` |
| sequential index | `detailedDescription[].rowNo` |
| sum of line values, first line currency | `totalValue {amount, currency}` |
| shipment gross weight | `totalGrossWeight {value, unit=KGM}` |
| `content_type` | `categoryOfItem` |
| consignor country | `countryOfOrigin` |

Bookings without customs data keep the exact pre-change request shape (no empty structures).

### D2: Standalone customs document fetched by-id, not split from the booking printout

After a successful `UX` booking with customs, issue `POST /v3/labels/ids/{pdf|zpl}` (matching the booking's label format path) with the booking response's first assigned item id and `definePrintout=onlyCustomsDeclarations`, and attach each returned printout as `ShippingDocument(category=..., format=PDF|ZPL, base64=...)` in `docs.extra_documents`.

Alternative considered: book with `definePrintout=ALL` and route the booking response's `labelPrintout` entries between label and customs docs in one call.
Rejected: `printoutComposition` is per printout (`labelPrintout[].printoutComposition`), but a single printout may compose several document kinds at once (label plus CN22 pages in one file), and the counts carry no page ranges — so a standalone customs document cannot be guaranteed from a merged printout; the by-id endpoint with `definePrintout=onlyCustomsDeclarations` can.

Consequences:

- The booking's own printout is left unchanged (PostNord may still compose CN22 pages into it); duplication is accepted and documented, with `definePrintout=onlyLabels` on booking as a future lever if consumers report double printing.
- The document `category` comes from parsed `printoutComposition` counts (`cn22`, `cn23`, `customsInvoice`, …), satisfying the "kinds reflect composition" requirement rather than assuming CN22 from the service code.
- Retrieval failure does not fail the booking: findings surface as response messages (fail-open, same stance as the dhl-freight-sweden address-validation pre-flight).
- ZPL customs printouts go through the existing raw-UTF-8 re-encoding path (`_printout_base64`, `shipment/create.py:114-125`) — ZPL is a real option via this route, answering the open question in the proposal; the PDF-variant declaration endpoint itself is PDF-only.

### D3: Post-booking declaration as connector-local proxy methods

Add two proxy methods following the `find_service_points` precedent (plain `lib.Serializable` in, provider module builds/parses, no server surface):

- `create_customs_declaration(request)` → `POST /v3/customs/declaration`, returning the `bookingResponseCN` result (per-id `OK|FAIL` status) plus messages.
- `create_customs_declaration_pdf(request)` → `POST /v3/customs/declaration/pdf`, additionally returning the rendered `labelPrintout` documents as `ShippingDocument` entries with caller-supplied rendering params (`paperSize`, `rotate`, `multiPDF`, alignment).

The request envelope is the typed declaration object(s) (`ids[0]` with `idType`, exactly one of the CN22/CN23/customsInvoice branches, `updateIndicator` for re-declaration) so the caller — not karrio — chooses branch, ids, and updates.
The 13-line guard applies here as it does at booking.
Upstream rejections (including "EDI must have been sent earlier") surface as unified error messages via the existing error handling.

### D4: Typed schemas via the standard generation pipeline

Extend `schemas/shipment_request.json` with the customs branches (definitions lifted from `vendor/booking.swagger.json` SW:5942-6036, 5176+, 5320+, 5461+), and add `schemas/customs_declaration_request.json` / `customs_declaration_response.json` plus an ids-label request fragment; regenerate with `./bin/run-generate-on modules/connectors/postnord`.
Alternative considered: the plain-dict style of `service_points.py`.
Rejected: the declaration bodies are deeply structured and benefit from generated types; the booking embedding needs schema changes regardless.

Generation conventions forced by the pipeline (from the group-1 review):
quicktype coerces digit-only swagger string fields to `int` annotations (postalCode, basicServiceCode, partyIdType, reasonForExportation, transportModeBorder) — provider code MUST pass these through as strings and never `int()`-coerce, so leading-zero and alphanumeric values survive intact.
Booking-embedded and declaration-module branch classes are structurally identical but distinct classes; any construction shared between the two flows happens at dict level via `lib.to_dict`, never by passing one module's classes into the other's model.
`BuyerType` is the pipeline's union of seller/buyer/shipTo — variant-specific fields are caller-owned and not validated client-side.

### D5: Line-limit guard is a pre-submission field error

A module-level constant (`CUSTOMS_DECLARATION_MAX_LINES = 13`, source: PostNord's Booking Customs Information documentation) is enforced wherever a declaration is built — booking embedding and both proxy methods — producing a field error before any HTTP call.
The local swagger expresses no `maxItems` on `detailedDescription`, so the constant carries the documented value and a live verification task backs it.

## Risks / Trade-offs

- [13-line limit not machine-verifiable locally] → constant documented from PostNord prose; sandbox verification task before release; guard message names the limit and the offending item id.
- [CN22 branch used above its 300 SDR postal ceiling for non-letter services] → accepted for v1 (letters are the goal); threshold handling recorded as an open question rather than invented silently.
- [ZPL customs printout rendering unverified] → re-encoding path exists and is tested at unit level; sandbox task confirms real output before relying on it.
- [Behavior change: customs data previously dropped now reaches PostNord] → intended feature; called out in the changelog so merchants sending stale customs payloads notice.
- [Document duplication between booking printout and standalone fetch] → accepted; consumer owns printing decisions; `definePrintout=onlyLabels` documented as the future lever.
- [`ids[]` maxItems 1 means one declaration object per item id] → the declaration request is a list of declaration objects, so multi-id shipments are expressed as multiple entries rather than one merged object.

## Migration Plan

Purely additive connector change: new request fields (customs branches), new proxy methods, new response documents.
No migration; no configuration flag — absence of customs data preserves the exact current request shape, and the implicit by-id fetch only fires for `UX` bookings with customs.
Rollback is a plain revert of the connector module.

## Open Questions

- Exact handling when declared value exceeds the CN22 ceiling (field error vs CN23 escalation) — deferred until sandbox evidence exists; the only local threshold signal is the swagger note that CN23 `commercialItems` apply "for commercial items only or content exceed 200 EUR" (SW:5411).
- Whether consumers need `emailTo` or non-default `definePrintout` on the digital declaration endpoint — add as pass-through params only when asked.
- Live-render quality of ZPL customs printouts on thermal printers — settled by the sandbox verification task, no schema or API change either way.
