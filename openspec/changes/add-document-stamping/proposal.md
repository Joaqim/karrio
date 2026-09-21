## Why

Third-party consumers of the karrio SDK need to composite raster images — signatures and letterheads — onto carrier duty documents (CN22 declarations, commercial invoices) that karrio returns as base64 in either PDF or ZPL.
Today every consumer reimplements format branching, two unrelated coordinate systems, and two alpha/depth models, and the silent-failure modes (naive thresholding destroys signature strokes; un-flattened alpha white-boxes over form content) look like success.
A single utility that sniffs format and composites via the matching backend removes that duplication and gives karrio one normalized placement vocabulary to document and to accrue verified defaults against.

## What Changes

- Add a format-multiplexing `lib.stamp_document` SDK entry point that accepts a `ShippingDocument`, a base64 PNG, and a consumer-supplied anchor, and returns a stamped document of the same format.
- Add a shared magic-byte format sniffer (generalizing the DHL Freight Sweden `LABEL_MAGICS` precedent) that routes to a per-format backend and rejects PNG documents explicitly.
- Add a PDF compositing backend at launch with zero new SDK dependencies: PNG becomes a single-page image PDF via Pillow and is scaled into place with a pypdf transformation merge.
- Add a neutral placement vocabulary (`StampPlacement`, millimetres from page top-left) with consumer-supplied anchors as the primary path and an optional registry of karrio-supplied seeds keyed by (carrier, document category, format, paper variant).
- Add a documented consumer workflow, per carrier, comparing the flow to the established FedEx ETD precedent.
- ZPL backend, registry seeds, printer-graphic caching, and any server/API surface are out of launch scope (P1 or deferred per the PRD).

## Capabilities

### New Capabilities
- `documents/stamping`: Carrier-agnostic compositing of a consumer-supplied image onto a returned carrier duty document, preserving the document's format and shape; covers format detection, consumer-supplied placement precedence, explicit PNG rejection, and registry-miss error semantics.

### Modified Capabilities
<!-- None. Stamping is additive; no existing spec's requirements change. -->

## Impact

- New SDK module (`modules/sdk/karrio/core/utils/stamping.py`) plus a `lib.stamp_document` re-export; the shared sniffer lands in `modules/sdk/karrio/core/utils/helpers.py`.
- Operates on the existing `ShippingDocument` model (`modules/sdk/karrio/core/models.py`), replacing `base64` in place and leaving `format` unchanged; no model, schema, or migration changes.
- No new SDK dependencies — the PDF backend uses the already-pinned Pillow and pypdf.
- No API endpoint, serializer, or document-payload changes; stamping is opt-in and consumer-invoked.
- Reference material: `PRDs/DOCUMENT_STAMPING_UTILITY.md` is the decision record (D1-D13); the FedEx ETD flow and PostNord customs printout path are untouched precedents, not modified surfaces.
