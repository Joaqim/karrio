# Document stamping

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-09-24 |
| Status | Completed |
| Owner | Joaqim Planstedt |
| Type | Enhancement |
| Reference | [AGENTS.md](../AGENTS.md); fork readers: the openspec `documents/stamping` spec on the `docs-openspec` branch |

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Open Questions & Decisions](#open-questions--decisions)
3. [Problem Statement](#problem-statement)
4. [Goals & Success Criteria](#goals--success-criteria)
5. [Alternatives Considered](#alternatives-considered)
6. [Technical Design](#technical-design)
7. [Edge Cases & Failure Modes](#edge-cases--failure-modes)
8. [Implementation Plan](#implementation-plan)
9. [Testing Strategy](#testing-strategy)
10. [Risk Assessment](#risk-assessment)
11. [Migration & Rollback](#migration--rollback)
12. [Appendix A: Contributing a carrier seed](#appendix-a-contributing-a-carrier-seed)

---

## Executive Summary

Carriers return duty documents such as customs declarations and commercial invoices that consumers must sign, date or brand before handing them over.
`lib.stamp_document` composites a consumer-supplied PNG onto a returned PDF or ZPL document, format in and format out, and `POST /v1/documents/stamp` exposes the same utility over REST.
The utility composites pixels only: it stores nothing and asserts nothing about the legal validity of the stamped content.

### Key Architecture Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Sniff the document bytes and dispatch to a per-format backend | Consumers never branch on format; magic bytes win over format hints |
| 2 | Millimetre placement from the page top-left, clockwise rotation anchored at the rotated extent's top-left corner | One coordinate model for PDF and ZPL; the anchor means the same thing rotated or upright |
| 3 | PDF: merge an image-PDF page through a scale/rotate/translate transformation, over or under the page content | The text layer, AcroForm fields and page count survive untouched |
| 4 | ZPL: a 1-bpp GRF graphic binarized with a fixed ink threshold and spliced before the trailing `^XZ` | ZPL has no z-order; a later field draws on top, and a threshold keeps thin strokes connected |
| 5 | Anchor resolution chain: placement, then keyword, then carrier seed | An explicit anchor always wins; a miss raises instead of guessing |
| 6 | Carrier plugins contribute seeds through `PluginMetadata.stamp_seeds` | The core stays carrier-neutral; seeds are declarative data like `options` and `services` |

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| PDF overlay (signature) and underlay (letterhead) | Signature validity, legal assertions, storage of stamped documents |
| ZPL overlay with an optional `~DY`/`^XG` printer cache | ZPL underlay (no z-order), multi-label ZPL streams |
| Rotation, a consumer date strip, keyword anchoring on ZPL fields | Date formatting and locale (the caller supplies the string) |
| Carrier seeds declared by plugins | Stamping PNG documents; keyword anchoring on PDF |

---

## Open Questions & Decisions

### Pending Questions

| # | Question | Context | Options | Status |
|---|----------|---------|---------|--------|
| Q1 | Should an injected `registry` lookup also return `StampSeed`? | Injection can express a PDF placement but not an implicit ZPL keyword seed | A) widen the return type, B) keep `StampPlacement` | Deferred |
| Q2 | Should the endpoint accept `keyword` and a geometry-only placement? | The keyword path is reachable from the SDK only | A) add both fields, B) keep the current request | Deferred |

### Resolved Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| D1 | Storage and validity | None | Stamping is a pure transformation of caller-supplied bytes |
| D2 | Format detection | Magic bytes first, then the content-type hint, then the caller default | Carrier format labels are sometimes wrong; bytes are not |
| D3 | Rotation semantics | Clockwise degrees, rotated extent's top-left anchored at `(x, y)` | A centre pivot moves the visible corner as the angle changes, which makes placements hard to measure |
| D4 | Transparency | Trim to the alpha bounding box, then flatten onto white | Pillow's PDF writer drops the soft mask, so unflattened alpha renders opaque |
| D5 | Date font | Pillow's built-in scalable font at 30% of the strip height, shrunk to fit | No bundled font asset; the height stays physically constant across densities |
| D6 | Date and signature split | Even split along the placement's primary axis, both halves drawn as parts of the one rotated rectangle | The pair lands exactly where a single image with the same placement would, at every angle |
| D7 | ZPL binarization | Fixed luminance threshold (200) | Error diffusion scatters anti-aliased glyph edges and faint strokes into speckle |
| D8 | Registry miss | Raise naming the composed key | A guessed anchor stamps silently in the wrong place |
| D9 | Seed supersession | `StampSeed.revision`, bumped only on re-measurement | A carrier re-rendering a form must not silently move a consumer-visible anchor |
| D10 | Seed ownership | `PluginMetadata.stamp_seeds`, resolved on demand through `karrio.references` | No import-order dependence and no carrier data in the core |
| D11 | Client input errors | `ValueError` from the SDK, 400 from the endpoint | Missing or undecodable images, unparseable PDFs, bad pages and unsafe graphic names are caller faults |
| D12 | Allocation bounds | ZPL operand range checked before the raster is built; PDF date raster capped at 20 000 px per side | A single request must not be able to allocate an unbounded canvas |

---

## Problem Statement

Every consumer that signs a carrier document re-implements format branching and coordinate maths, and ZPL offers neither a z-order nor a text layer to anchor against.

```python
# Before: per-consumer branching
if document.format == "PDF":
    ...  # open with a PDF library, convert mm to points, flip the y axis, merge
elif document.format == "ZPL":
    ...  # resize, binarize, hex-encode a GRF, splice before ^XZ

# After
stamped = lib.stamp_document(
    document,
    image=signature_png_b64,
    placement=lib.StampPlacement(x=40, y=200, width=60, height=20),
)
```

---

## Goals & Success Criteria

| Goal | Success criterion |
|------|-------------------|
| Format preservation | The returned document has the input's format and page count |
| Content preservation | PDF text layer and AcroForm fields are unchanged after stamping |
| Valid ZPL | Every emitted `^FO` origin and graphic extent lies within 0-32000 dots |
| Explicit failure | Each failure class raises `ValueError` naming its cause; the endpoint answers 400 |
| No regressions | SDK and connector suites pass unchanged |

---

## Alternatives Considered

| Topic | Alternative | Chosen | Reason |
|-------|-------------|--------|--------|
| PDF compositing | Rasterize the page and paste the image | Merge an image-PDF page | Rasterizing destroys the text layer and form fields |
| ZPL graphic | Inline `^GFA` only | Inline `^GFA` by default, `~DY`/`^XG` on request | The cache sends the raster once per printer for repeated labels |
| Rotation pivot | Rectangle centre | Rotated extent's top-left corner | Measured placements stay valid at any angle |
| Binarization | Floyd-Steinberg error diffusion | Fixed threshold | Diffusion breaks strokes and speckles text |
| Carrier anchors | Hardcoded in the core | Plugin-declared seeds | Keeps the core neutral and lets connectors ship measured data |
| Seed registration | Imperative `register_seed` at import time | Plugin metadata field | Registration by import depends on import order |

---

## Technical Design

### Existing Code Analysis

| Reused | Where | How |
|--------|-------|-----|
| `helpers.to_buffer`, `failsafe`, `decode_bytes` | `modules/sdk/karrio/core/utils/helpers.py` | Base64 decoding and tolerant text decoding |
| pypdf document cloning and page merging | `lib.bundle_pdfs` idioms after the pypdf migration | Clone the whole document, merge per page |
| `ShippingDocumentCategory` | `modules/sdk/karrio/core/units.py` | Normalizes the registry key's document type |
| `PluginMetadata` declarative fields | `modules/sdk/karrio/core/metadata.py` | `stamp_seeds` sits beside `options` and `services` |
| `DocumentGenerator` view | `modules/documents/karrio/server/documents/views/templates.py` | `BaseAPIView` without `LoggingMixin`, error envelope |

### Architecture Overview

```
 consumer / REST client
        |  document (base64 PDF|ZPL), image (base64 PNG),
        |  placement? carrier? doc_type? date? graphic_name?
        v
 +--------------------------+      POST /v1/documents/stamp
 | documents.views.stamping |<---- (authenticated, stateless)
 +------------+-------------+
              | lib.stamp_document(...)   (SDK callers may add keyword=)
              v
 +---------------------------------------------------------------+
 | karrio.core.utils.stamping.stamp_document                     |
 |                                                               |
 |  sniff_document_format --> PDF | ZPL | PNG(reject) | other(reject)
 |                                                               |
 |  anchor resolution:                                           |
 |   placement(x,y) ------------------------------> placement    |
 |   keyword (+geometry | seed.keyword_placement) -> ^FO origin  |
 |   neither --> seed lookup carrier/doc_type/FORMAT/paper       |
 |               |  PDF: seed.placement                          |
 |               |  ZPL: seed.keyword -> ^FO origin              |
 |               '--> miss: ValueError naming the key            |
 |                        ^                                      |
 |                        | PluginMetadata.stamp_seeds           |
 |              +---------+----------+                           |
 |              | carrier plugin     |                           |
 |              +--------------------+                           |
 |                                                               |
 |  backends:                                                    |
 |   stamp_pdf: flatten PNG -> image-PDF -> scale/rotate/        |
 |              translate -> merge over|under page (pypdf)       |
 |   stamp_zpl: range check -> flatten + date -> dot raster ->   |
 |              threshold 1-bpp -> rotate -> ^GFA | ~DY + ^XG    |
 |              -> splice before ^XZ                             |
 +---------------------------------------------------------------+
              |
              v
   ShippingDocument (same format, new base64)
```

### Data Models

| Type | Field | Meaning |
|------|-------|---------|
| `StampPlacement` | `page` | One-based page index (PDF), default 1 |
| | `x`, `y` | Millimetres from the page top-left; `None` in a keyword geometry means an offset of 0 |
| | `width`, `height` | Pre-rotation extent in millimetres |
| | `rotation` | Degrees clockwise, default 0 |
| | `dpi` | ZPL density, default 203; ignored by the PDF backend |
| `StampSeed` | `placement` | PDF anchor |
| | `keyword`, `keyword_placement` | ZPL anchor: field text and the strip geometry offset from its `^FO` |
| | `revision` | Supersession counter |

`lib` exports `stamp_document`, `StampPlacement` and `StampSeed`.

### API Changes

```json
POST /v1/documents/stamp
{
  "document": "<base64 PDF or ZPL>",
  "image": "<base64 PNG>",
  "placement": {"page": 1, "x": 40, "y": 200, "width": 60, "height": 20, "rotation": 0, "dpi": 203},
  "layer": "overlay",
  "carrier": "acme",
  "doc_type": "customs_declaration",
  "format": "PDF",
  "date": "2026-09-24",
  "graphic_name": "R:SIGN.GRF"
}

201 {"doc_file": "<base64, same format>", "format": "PDF"}
400 {"errors": [{"message": "..."}]}
```

`image`, `document` and, inside `placement`, `x`, `y`, `width` and `height` are required.

### Placement and Rotation Geometry

A placement's `(width, height)` is rotated clockwise by `rotation` about its own corner, and the rotated bounding box's top-left lands on `(x, y)` at every angle, so the drawn extent is `(x, y)` to `(x + w|cos r| + h|sin r|, y + w|sin r| + h|cos r|)`.
In PDF space (bottom-left origin, points) the overlay transformation is `scale(w/iw, h/ih) . rotate(-r) . translate(ax - min_x, ay - max_y)`, where `(ax, ay) = (pt(x), H - pt(y))` and `(min_x, max_y)` are the extrema of all four rotated corners, the unrotated origin corner included.
The mediabox check tests that drawn box.
In ZPL the raster is rotated with an expanding canvas and placed at `^FO{dots(x)},{dots(y)}`, which gives the same extent.
The date strip takes the leading half `d` of the primary axis; both halves are parts of the one rotated rectangle, so the date shares the rectangle's translation and the signature half's is offset by `(d cos r, -d sin r)`.

---

## Edge Cases & Failure Modes

| Input | Behaviour |
|-------|-----------|
| PNG or unrecognized document bytes | `ValueError` naming the format |
| No placement, no keyword, no seed for the key | `ValueError` naming `carrier/doc_type/FORMAT/paper` |
| Keyword with a fully anchored placement | `ValueError`: two contradictory anchors |
| Keyword on a PDF | `ValueError`: keywords locate ZPL fields only |
| Keyword matching no `^FD` text | `ValueError` naming the keyword |
| Negative `x`/`y`, non-positive `width`/`height` | `ValueError` naming the field |
| `page` outside `1..page_count` | `ValueError` naming `StampPlacement.page` |
| Rotated PDF extent leaving the mediabox | `ValueError` naming the edge |
| ZPL origin or extent outside 0-32000 dots | `ValueError`, raised before the raster is built |
| PDF date strip above 20 000 px per side | `ValueError`, raised before rendering |
| ZPL underlay | `ValueError`: ZPL has no z-order |
| Missing or undecodable image, unparseable PDF | `ValueError` |
| `graphic_name` other than `[device:]NAME[.GRF]` | `ValueError` (SDK) or 400 (serializer) |

Known ZPL limitations, documented rather than handled: the graphic splices before the last `^XZ`, so a multi-label stream is stamped on its last label only; the keyword locator reads `^FO` only and ignores `^LH`, `^FT` and `^CC`; the sniffer recognizes ZPL only when the stream starts with `^XA`.

### Security Considerations

The endpoint is authenticated and stateless and reads or writes no org-scoped data.
Base64 payloads stay out of `APILogIndex` because the view skips `LoggingMixin`.
Allocation is bounded by the ZPL operand check and the PDF date raster cap (D12).
`graphic_name` is validated because it is interpolated into ZPL commands.

---

## Implementation Plan

| Phase | Commit | Files |
|-------|--------|-------|
| 1 | `feat(sdk): add format-preserving pdf document stamping` | `karrio/core/utils/stamping.py`, `helpers.py` (`sniff_document_format`), `lib.py`, `tests/core/test_stamping_pdf.py`, `tests/core/stamping_helpers.py`, `tests/core/fixtures/signature_test.png` |
| 2 | `feat(sdk): add zpl document stamping backend` | `stamping.py`, `tests/core/test_stamping_zpl.py` |
| 3 | `feat(sdk): support rotated stamp placements and a consumer date strip` | `stamping.py`, `modules/sdk/pyproject.toml` (`Pillow>=10.1`), `tests/core/test_stamping_rotation_date.py` |
| 4 | `feat(sdk): resolve stamp placements from plugin seeds and zpl keywords` | `stamping.py`, `metadata.py`, `lib.py`, `tests/core/test_stamping_resolution.py` |
| 5 | `feat(documents): add document stamping endpoint` | `serializers/base.py`, `views/stamping.py`, `urls.py`, `tests/test_stamping.py` |
| 6 | `docs(documents): add document stamping guide` | `apps/www/docs/reference/guides/document-stamping.mdx`, `apps/www/sidebars.js` |

---

## Testing Strategy

The SDK suites split by capability: `test_stamping_pdf`, `test_stamping_zpl`, `test_stamping_rotation_date` and `test_stamping_resolution`, sharing generated fixtures and output oracles in `stamping_helpers.py`.
Carrier documents are generated in the tests (a Helvetica text-layer form, an AcroForm document, a carrier-style ZPL form); the one checked-in fixture is a real anti-aliased signature PNG.
Oracles read the written output: the merged overlay's `cm` matrices, parsed `^GFA` headers and raster pixels.
Expected values come from independent literals, never from the production expression under test.
Seeds are exercised through a synthetic `acme` plugin served by patching `karrio.references.collect_providers_data`.

```bash
python -m unittest discover -v -f modules/sdk/tests
karrio test --failfast karrio.server.documents.tests
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Pillow without FreeType (`load_default(size=...)` fails) | Low | Date stamps fail | `Pillow>=10.1`; wheels ship FreeType |
| A carrier re-renders a form and a seed drifts | Medium | Stamp lands off target | Revisioned seeds; seed oracles derived from measurements |
| Very large inputs | Low | Memory pressure | Operand range check before raster build, date raster cap |
| ZPL dialect variance | Medium | Keyword not found | Explicit keyword-miss error; consumer can pass a placement |

---

## Migration & Rollback

The change is additive: a new SDK utility, a new optional plugin metadata field and a new endpoint, with no data migration.
Rollback is reverting the commits.

---

## Appendix A: Contributing a carrier seed

A connector declares seeds on its plugin metadata, keyed `doc_type/FORMAT/paper`; the carrier segment comes from the plugin id.

```python
METADATA = PluginMetadata(
    id="acme",
    label="Acme",
    # ...
    stamp_seeds={
        "customs_declaration/PDF/A4": lib.StampSeed(
            placement=lib.StampPlacement(x=53.34, y=91.44, width=49.11, height=7.62, rotation=90),
            keyword="Sender signature",
            keyword_placement=lib.StampPlacement(x=-1.673, y=33.529, width=49.1, height=7.6, rotation=90),
            revision=1,
        ),
    },
)
```

A PDF key resolves `placement`; a ZPL key resolves `keyword` plus `keyword_placement`, whose `x`/`y` are offsets from the located `^FO`.
A key with a concrete paper variant never matches another variant; a `*` paper segment matches any page.

Measuring a seed:

- Measure the target strip on the PDF form in millimetres, then encode it under the placement semantics: pre-rotation extent, rotation, and the rotated extent's top-left as the anchor.
- For ZPL, map the PDF form's drawing onto the label frame and cross-check a few rules or separators at sub-dot precision; the same physical strip expressed as PDF millimetres and as a keyword offset in dots must agree.
- A seed is measured data tied to the placement semantics in force when it was measured. When the semantics change (for example from a centre pivot to a corner anchor), re-measure rather than convert algebraically: a conversion can preserve the centre while swapping the rendered axes.
- Test oracles for a seed derive from the measurement, not from the seed object, so a wrong seed cannot pass a circular check.
- Bump `revision` only on a genuine re-measurement, not when adding data such as a keyword.
- A per-form target region is seed-authoring data; the backends check only page and operand bounds.
