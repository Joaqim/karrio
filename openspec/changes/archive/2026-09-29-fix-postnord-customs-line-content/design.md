## Context

On `fix-postnord-eu-vat-territories`, `shipment/create.py` builds CN22 lines in `_customs_line` (~390, `content=commodity.title or commodity.description` at ~405) and customs invoice lines in `_customs_invoice_line` (~556, same expression at ~567).
`_customs_declaration` (~430) already calls `provider_units.enforce_customs_declaration_lines` and `enforce_cn22_registration_numbers` (~448-451), which raise `lib.exceptions.FieldError` before any request is built; `enforce_customs_option_placement` runs in `shipment_request` (~754).
Customs is built only when commodities exist and the lane is outside the EU VAT area (~740-751).
`error.py` builds one message per fault with `code = faultCode or _sub_type(fault)` and `message = explanationText or body["message"]` (~66-85), and copies `paramValues` and `faultReferences` into `details`.
`schemas/shipment_response.json` has no `faultReferences` on its fault objects, so `lib.to_object(ShipmentResponseType, ...)` (~164) logs "unknown arguments" whenever a fault carries references.

## Goals / Non-Goals

**Goals:**

- A missing goods description is reported locally, naming the commodity index and unified field.
- PostNord faults whose subtype we understand tell the user what to fix.

**Non-Goals:**

- Using `sku`, HS code text or any other field as a substitute goods description.
- Requiring commodity titles in the dashboard or order import.
- Hints for subtypes not evidenced in the vendored specs or captured fixtures.

## Decisions

### A check in `units.py`, called by both line builders' callers

Add `enforce_customs_line_content(commodities)` beside the existing `enforce_*` functions in `units.py`.
It collects every commodity index with neither title nor description and raises one `FieldError` with a key per offending index, `customs.commodities[<index>].title`, each explaining that PostNord requires a title or description for each customs line.
It is called where the CN22 declaration and the customs invoice are assembled, before lines are built, so it runs only when customs is actually sent and never for lanes inside the EU VAT area.
If the connector builds declaration lines anywhere else (for example a standalone customs declaration request), that path calls it too.

Alternative considered: a check inside each line builder; rejected because one error listing every offending index is more useful than failing on the first.

### Hints keyed by fault subtype in `error.py`

A module-level mapping from subtype to hint text is applied where the message is built: `message = f"{explanationText} ({hint})"` when the subtype has a hint, otherwise unchanged.
The initial table holds `CONTENT` (customs commodity title or description) and each further subtype that the vendored PostNord specs or the connector's captured fixtures show with a clear unified counterpart, such as `WEIGHT_LIMIT` (parcel weight); the implementer lists the evidence for each entry.
`code` and `details.references` are unchanged, so consumers matching on codes are unaffected.

Alternative considered: a separate `details.hint`; rejected because the dashboard shows `message`, which is where the user needs the hint.

### Envelope message kept as `details.summary`

When a fault has its own `explanationText` and the body has a top-level `message`, that message is added as `details["summary"]`.
When `explanationText` is missing, the top-level message remains the message, as today, and is not duplicated into details.

### Schema update is generated, not hand-edited

`faultReferences` (array of `{key, value}` strings) is added to each fault object in `schemas/shipment_response.json`, and `./bin/run-generate-on modules/connectors/postnord` regenerates `karrio/schemas/postnord/shipment_response.py`; the generated file is not edited by hand.

## Risks / Trade-offs

- [Bookings that PostNord would have accepted are now rejected] → PostNord's swagger defines `content` with `minLength` 1 as required on every customs line object, so such bookings already fail remotely.
- [Hint text drifts from PostNord's meaning] → only subtypes with evidence get hints, and PostNord's own text stays first in the message.
- [Consumers parsing `message` text exactly] → the text now has a suffix for hinted subtypes; `code` and references are the stable fields and are unchanged.

## Migration Plan

Create the branch from `fix-postnord-eu-vat-territories`, add it to `BRANCHES` directly after that branch, run `rebuild-develop.sh`, and leave the develop push to the user.
