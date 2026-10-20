## Why

Stamping placement today requires a measured millimetre anchor: consumers must supply coordinates or rely on a hand-measured registry seed per carrier, document type, format, and paper variant, and a carrier re-rendering a form can silently drift a shipped anchor.
The anchor is already printed in the carrier form itself — PostNord's CN22 carries a "Date and Sender's signature" field directly beside the strip a date-plus-signature stamp must fill — so placement can be derived from the document's own content per carrier, with no measurement to drift and no coordinates for the consumer to know.

## What Changes

- Placement resolution gains a keyword stage ahead of the existing compositing pipeline: a keyword locates the matching text field in a ZPL carrier stream and the stamp placement is derived from that field's position in the form.
- The keyword comes from the consumer or from the registry, keyed per carrier and document type, mirroring the existing coordinate-seed mechanism.
- Registry entries anchor the two formats each in its own currency: PDF by a measured coordinate anchor, ZPL by a carrier form keyword; a consumer invoking a seeded carrier/document supplies neither and each format resolves implicitly.
- A keyword-resolved placement flows through the existing backends unchanged: raster GRF compositing, corner-anchored rotation, operand and mediabox bounds validation, and single-call date-prefixed-before-signature compositing.
- Resolution precedence is explicit: a consumer-supplied placement wins; then a consumer-supplied keyword; then the registry (keyword for ZPL, coordinate seed for PDF); a miss at the end of the chain still fails explicitly naming what was tried.
- Non-goals: no change to date rendering (raster through the existing pipeline), no change to the interim even date/signature strip split, no change to the accepted base64 PNG image contract, and no PDF-side keyword mechanism.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `documents/stamping`: the placement-resolution requirements extend from the current placement-or-seed pair to a placement, keyword, and seed chain with defined precedence; registry requirements extend so an entry can anchor ZPL documents by carrier form keyword; the compositing requirements behind resolution are unchanged.

## Impact

- `modules/sdk/karrio/core/utils/stamping.py` — placement resolution chain, keyword fields on the request and seed models, and a ZPL field locator that finds the keyword's `^FO` origin in the carrier stream.
- `lib.stamp_document` — a new keyword parameter threaded through the SDK re-export.
- `_SEED_REGISTRY` / `StampSeed` — keyword-bearing entries, PostNord CN22 first.
- Tests — `modules/sdk/tests/core/test_document_stamping*.py` gain keyword-resolution cases against the vendored PostNord CN22 ZPL fixture, including precedence and resolution-failure paths.
- SDK-level utility only: no database, API, or dependency surface changes.
