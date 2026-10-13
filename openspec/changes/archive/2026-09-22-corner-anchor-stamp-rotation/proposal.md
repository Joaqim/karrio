## Why

A live request against `POST /v1/documents/stamp` with placement `(0, 0, 70, 20, rotation=90, dpi=203)` on a PostNord CN22 ZPL form emitted `^FO200,-200`, placing the signature 25 mm right of the anchor and half-clipped above the label.
Both backends rotate about the placement rectangle's centre and re-anchor to preserve that centre, so the intuitive reading — the anchor is where the rotated image's top-left lands — is inexpressible: for a 70x20 mm placement rotated 90 degrees, the rotated extent's left edge sits at least 25 mm right of the requested corner for any non-negative x.
The backend also emits the negative `^FO` operand silently, which is out-of-spec ZPL (valid range 0-32000) that preview renderers clip forgivingly and physical printers interpret inconsistently.

## What Changes

- Rotated placements anchor corner-first in both backends: the image is rotated clockwise, then the rotated extent's top-left corner lands at the placement's `(x, y)`.
- The ZPL backend's `^FO` becomes the placement anchor directly, and any origin or extent operand resolving outside 0-32000 dots is rejected with an explicit error.
- The PDF backend rotates about the image corner and translates the rotated bounding box's top-left onto the anchor; a rotated extent crossing the mediabox is rejected with an error naming the edge.
- Negative anchors are rejected before any backend work, naming the field.
- Unrotated placements are byte-identical to the shipped output and keep their permissive behavior.
- The PostNord CN22 seed re-expresses its unchanged physical strip under the new semantics as `StampSeed` revision 2: anchor `(53.3, 91.4)` becomes `(32.55, 112.15)`.
- The rotation direction question (design Q10) closes as confirmed-clockwise using the vendored CN22 ZPL form, whose `^FWR` field stream reads with glyph-up = page +x.

## Capabilities

### Modified Capabilities
- `documents/stamping`: the placement rotation requirement now specifies corner-anchored rotated extents, and a new requirement covers bounds rejection for negative anchors and out-of-printable-area rotated extents.

## Impact

- SDK module `modules/sdk/karrio/core/utils/stamping.py`: rotation branches of `stamp_zpl` and `stamp_pdf`/`_merge_overlay`, new `_validate_anchor` and `_validate_pdf_extent` helpers, seed revision 2.
- Breaking for rotated placements only: a rotated anchor must be re-expressed as the rotated extent's top-left (for 90 degrees, `x_new = x_old + (w-h)/2`, `y_new = y_old - (w-h)/2`).
- No server, serializer, model, or dependency changes: the server already maps backend `ValueError` to a 400 response.
- Tests: oracles updated in `modules/sdk/tests/core/test_document_stamping.py`; the vendored real-fixture suite `test_document_stamping_fixtures.py` carries the incident regression.
