# Document stamping

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.2 |
| Date | 2026-09-28 |
| Status | In Progress |
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
12. [Customs composition classification](#customs-composition-classification)
13. [PDF keyword anchoring](#pdf-keyword-anchoring)
14. [ZPL reading-frame and format anchoring](#zpl-reading-frame-and-format-anchoring)
15. [Appendix A: Contributing a carrier seed](#appendix-a-contributing-a-carrier-seed)

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
| 7 | Classify a document's customs composition from carrier-declared section markers (`PluginMetadata.document_sections`) | A consumer learns the registry document type to stamp under without inspecting the document; see [Customs composition classification](#customs-composition-classification) |
| 8 | Anchor PDF stamps by a keyword located in page text, laid out along the text's direction | One seed serves carrier layouts that print the same form upright or turned; see [PDF keyword anchoring](#pdf-keyword-anchoring) |

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| PDF overlay (signature) and underlay (letterhead) | Signature validity, legal assertions, storage of stamped documents |
| ZPL overlay with an optional `~DY`/`^XG` printer cache | ZPL underlay (no z-order), multi-label ZPL streams |
| Rotation, a consumer date strip, keyword anchoring on ZPL fields and PDF page text | Date formatting and locale (the caller supplies the string) |
| Carrier seeds declared by plugins | Stamping PNG documents; PDF text set at angles other than multiples of 90 degrees |

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
| D13 | Endpoint protocol | REST `POST /v1/documents/stamp` only; a GraphQL mutation was rejected | Document generation (`DocumentGenerator`), the co-located precedent, is a REST view whose base64 request and response idiom maps directly onto stamping |
| D14 | Execution | Synchronous, no Huey task | Stamping is an in-process pypdf/Pillow transformation of one document with no network call, like the synchronous `DocumentGenerator` |
| D15 | Document input | Base64 in the request body only; stamping a stored shipment document is out of scope | A request-carried document has no stored resource to scope by org, so authentication is the whole tenancy story; a stored-document variant would need org-scoped access checks |
| D16 | Registry exposure | The endpoint accepts `carrier` and `doc_type` scalars and resolves the built-in registry server-side | The SDK `registry` argument is a `RegistryLookup` callable, which is not serializable, so the HTTP surface forwards only the seed key segments |

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
 |   keyword (+geometry | seed keyword geometry for FORMAT)     |
 |            ZPL -> ^FO origin | PDF -> page text run origin    |
 |   neither --> seed lookup carrier/doc_type/FORMAT/paper       |
 |               |  PDF: seed.keyword + pdf_keyword_placement    |
 |               |       -> page text run, else seed.placement   |
 |               |  ZPL: seed.keyword -> ^FO origin (label axes) |
 |               |       or text start (zpl_keyword_frame_...)   |
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
 |              -> splice before the keyword format's ^XZ      |
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
| `StampSeed` | `placement` | PDF coordinate anchor |
| | `keyword` | The form's own text beside the signature area, shared by both formats |
| | `keyword_placement` | ZPL keyword geometry: the strip offset in millimetres from the located `^FO`, in label axes |
| | `pdf_keyword_placement` | PDF keyword geometry: the strip in millimetres in the keyword's reading frame (see [PDF keyword anchoring](#pdf-keyword-anchoring)); when absent a PDF key resolves `placement` |
| | `zpl_keyword_frame_placement` | ZPL keyword geometry in the matched field's reading frame (see [ZPL reading-frame and format anchoring](#zpl-reading-frame-and-format-anchoring)); outranks `keyword_placement` when both are set |
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
| Keyword matching no `^FD` text, or no text run on the target PDF page | `ValueError` naming the keyword |
| Keyword on a PDF whose target page carries no extractable text | `ValueError`: the keyword cannot be located without page text |
| PDF keyword text not turned by a multiple of 90 degrees, skewed or mirrored | `ValueError` naming the keyword |
| Negative `x`/`y`, non-positive `width`/`height` | `ValueError` naming the field |
| `page` outside `1..page_count` | `ValueError` naming `StampPlacement.page` |
| Rotated PDF extent leaving the mediabox | `ValueError` naming the edge |
| ZPL origin or extent outside 0-32000 dots | `ValueError`, raised before the raster is built |
| PDF date strip above 20 000 px per side | `ValueError`, raised before rendering |
| ZPL underlay | `ValueError`: ZPL has no z-order |
| Missing or undecodable image, unparseable PDF | `ValueError` |
| `graphic_name` other than `[device:]NAME[.GRF]` | `ValueError` (SDK) or 400 (serializer) |

Known ZPL limitations, documented rather than handled: a placement without a keyword splices before the last `^XZ`, so a multi-label stream is stamped on its last label only (a keyword-resolved stamp splices into the format containing the keyword); the keyword locator reads `^FO` only and ignores `^LH`, `^FT` and `^CC`; the sniffer recognizes ZPL only when the stream starts with `^XA`.

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

## Customs composition classification

### Problem

`stamp_document` resolves a seed from the caller's `doc_type`, but it never inspects the document to decide that type.
Some carriers return a customs declaration composed with the shipping label in one printout: a single ZPL format, or a single PDF page, carrying both sections.
Neither page count nor `^XZ` count separates a lone declaration from a combined printout, so a consumer cannot tell which seed applies without reading carrier-specific markers itself.

### Design

A pure classifier reads carrier-declared section markers and returns the composition together with the registry `doc_type` to stamp under.
The SDK stays carrier-agnostic: markers are declarative plugin data beside `stamp_seeds`, and the classifier knows only the composed kind names.

```
 consumer / connector parser
        |  document (base64 PDF|ZPL), carrier? | sections?
        v
 +---------------------------------------------------------------+
 | karrio.core.utils.stamping.classify_customs_composition       |
 |                                                               |
 |  sniff_document_format --> ZPL | PDF | other(ValueError)      |
 |                                                               |
 |  sections: injected mapping, else                             |
 |            PluginMetadata.document_sections[FORMAT]           |
 |                        ^                                      |
 |              +---------+----------+                           |
 |              | carrier plugin     |                           |
 |              +--------------------+                           |
 |                                                               |
 |  ZPL: kind present when all its markers occur in the stream   |
 |  PDF: per-page text (pypdf), whitespace-collapsed; kind       |
 |       present when all its markers occur on one page          |
 |  AnyOf(set, set, ...): present when any one set matches       |
 |                                                               |
 |  cn22 absent            --> none                   doc_type - |
 |  cn22, label absent     --> declaration            cn22       |
 |  cn22 and label present --> label_with_declaration label_cn22 |
 |  PDF page = first page carrying the cn22 markers              |
 +---------------------------------------------------------------+
        |  CustomsClassification (frozen)
        v
 lib.stamp_document(document, carrier=..., doc_type=result.doc_type,
                    page=result.page, ...)
```

A seed's own placement names the page it stamps, which for a combined printout measured on one page need not be the page classification names.
`stamp_document` therefore takes an optional one-based `page` that applies a registry-resolved PDF placement (plugin seed or injected `registry`) on that page instead of the seed's; omitting it, or passing `None` as ZPL classification returns, keeps the seed's page.
An out-of-range `page` raises through the same bounds check as `StampPlacement.page`.
A `page` combined with a fully anchored placement raises, because that placement already names its page and two page anchors would contradict, mirroring the keyword-with-placement rule.
A `page` against ZPL raises, because a ZPL label has no pages to select.
The documents endpoint passes an optional `page` field through to `stamp_document`.

The declaration marker alone never implies a lone declaration: a combined printout carries it too, so `declaration` means the declaration kind is present and the label kind is absent.
A document with no matching markers, and a carrier declaring no sections for the format, classify as `none` rather than raising.
Only a format that is neither ZPL nor PDF raises, naming the detected format, because that is a caller error rather than a composition outcome.
Classification performs no I/O beyond the plugin metadata lookup and never modifies the document.

### Data model

| Type | Field | Meaning |
|------|-------|---------|
| `PluginMetadata` | `document_sections` | `{FORMAT: {kind: markers}}`; ZPL markers are field-comment substrings of the stream, PDF markers are page-text substrings; a kind is present when all its markers match; a single string is one marker; `lib.AnyOf(set, set, ...)` declares alternative sets, present when any one set fully matches |
| `AnyOf` | `sets` | Frozen tuple of marker sets, each a string or a sequence with the all-of meaning; a bare string, tuple or list stays a single set |
| `CustomsComposition` | `none`, `declaration`, `label_with_declaration` | String enum of the composition outcome |
| `CustomsClassification` | `composition` | A `CustomsComposition` member |
| | `kinds` | Sorted tuple of composed kinds present, such as `("cn22", "label")` |
| | `doc_type` | `cn22`, `label_cn22`, or `None` for `none` |
| | `page` | One-based PDF page carrying the declaration; `None` for ZPL and for `none` |

`lib` exports `classify_customs_composition`, `CustomsClassification`, `CustomsComposition` and `AnyOf`.
Alternative sets exist because carrier label templates differ: PostNord's sandbox booking PDF prints a tracked letter label without the letter label's text.

```python
METADATA = PluginMetadata(
    id="acme",
    label="Acme",
    document_sections={
        "ZPL": {"cn22": "^FX ACME_CN22^FS", "label": "^FX ACME_LABEL^FS"},
        "PDF": {"cn22": ("CUSTOMS DECLARATION", "CN22"), "label": ("Acme letter",)},
    },
)

result = lib.classify_customs_composition(document, carrier="acme")
if result.doc_type:
    stamped = lib.stamp_document(
        document, image=signature, carrier="acme", doc_type=result.doc_type, page=result.page
    )
```

### Implementation plan

| Task | Commit | Files |
|------|--------|-------|
| 1.1 | `feat(sdk): declare document sections in plugin metadata` | `modules/sdk/karrio/core/metadata.py`, `modules/sdk/karrio/core/utils/stamping.py` (`_carrier_sections`), `modules/sdk/tests/core/test_stamping_classification.py` |
| 1.2 | `feat(sdk): classify customs composition of zpl documents` | `stamping.py` (`CustomsComposition`, `CustomsClassification`, `classify_customs_composition`), `test_stamping_classification.py` |
| 1.3 | `feat(sdk): classify customs composition of pdf documents` | `stamping.py`, `modules/sdk/tests/core/stamping_helpers.py` (text-page PDF generator), `test_stamping_classification.py` |
| 1.4 | `test(sdk): reject unsupported formats in customs classification` | `test_stamping_classification.py` |
| 1.5 | `feat(sdk): export customs classification through karrio.lib` | `modules/sdk/karrio/lib.py`, `stamping.py` (module docstring), `test_stamping_classification.py` |
| 1.6 | `feat(sdk): apply a registry-resolved stamp placement on a named page` | `stamping.py` (`stamp_document` `page`), `lib.py`, `modules/sdk/tests/core/test_stamping_page_override.py` |
| 1.6 | `feat(documents): accept a seed page on the stamping endpoint` | `modules/documents/karrio/server/documents/serializers/base.py`, `views/stamping.py`, `tests/test_stamping.py` |
| 6.1 | `feat(sdk): accept alternative marker sets per document section` | `modules/sdk/karrio/core/utils/stamping.py` (`AnyOf`, `_kinds_present`), `modules/sdk/karrio/lib.py`, `modules/sdk/tests/core/test_stamping_classification.py` |

Carrier markers, combined seeds (`label_cn22/ZPL/*`, `label_cn22/PDF/A4`) and booking-time verification belong to the carrier connector and are out of scope for this SDK section.

### Testing strategy

`test_stamping_classification.py` exercises a synthetic `acme` plugin with synthetic markers, served by patching `karrio.references.collect_providers_data` as the seed tests do, and the injected `sections` mapping.

| Case | Expected |
|------|----------|
| ZPL with declaration and label markers in one format | `label_with_declaration`, `label_cn22`, page `None` |
| ZPL with the declaration marker only | `declaration`, `cn22` |
| ZPL with the label marker only, and with neither | `none`, no `doc_type` |
| PDF generated in-test with both sections on one page | `label_with_declaration`, `label_cn22`, page 1 |
| PDF with the declaration only | `declaration`, `cn22`, page 1 |
| Multi-page PDF with the declaration on page 2 | page 2 |
| PDF whose text matches no marker, and a PDF with a partial multi-marker kind | `none` |
| Carrier declaring no sections for the format | `none` |
| `AnyOf` label kind whose second set alone matches (ZPL and PDF) | label present; PDF names the declaration page |
| `AnyOf` with no set, or only part of a set, matching | kind absent |
| `AnyOf` wrapping one set, and a list declaration | same result as the bare set |
| PNG input | `ValueError` naming `PNG` |
| Any input | the document's `base64` is unchanged |

`test_stamping_page_override.py` stamps a two-page PDF under a page-1 `label_cn22/PDF/A4` seed.

| Case | Expected |
|------|----------|
| `page=2` | stamp on page 2 only, at the seed's coordinates; page count unchanged |
| `page` omitted or `None` | stamp on page 1 only |
| `page` of 3, 0, or -1 | `ValueError` naming the bounds and the page |
| `page=2` with an injected `registry` | stamp on page 2 only |
| `page` with a fully anchored placement | `ValueError` |
| `page` against ZPL (seeded, keyword, or placement) | `ValueError` naming `ZPL` |

```bash
python -m unittest discover -v -f modules/sdk/tests
```

---

## PDF keyword anchoring

### Problem

A PostNord sandbox booking of the export letter with a PDF label returned two A4 pages, a tracked letter label and an upright CN22, whereas the single-page combined and customs-only printouts turn the CN22 by 90 degrees beside the label.
The CN22 form sits at a different offset and orientation in each layout, so one `label_cn22/PDF/A4` coordinate seed cannot serve both, while the signature keyword is printed in every captured layout.

### Design

A keyword supplied for a PDF, or a seed carrying `pdf_keyword_placement`, is located in the page text instead of rejected.
The target page is the `page` override when given, else the first page whose text contains the keyword.
pypdf's text visitor reports each run's text matrix and the graphics matrix of the content stream it sits in, but extracts a form XObject from an identity matrix, so the locator tracks the invoking `cm` and each form's `/Matrix` from the operator callbacks and composes `Tm x CTM x form matrices` into page space; the form's whole text, which pypdf reports once more under the invoking stream, is discarded.
The origin is the start of the first run containing the keyword, and the run's x-axis is the text direction, snapped to a multiple of 90 degrees clockwise; any other direction raises.

```
 page (top-left mm, y down)            keyword reading frame
                                                 x (along the text)
      O = start of the matched run          O ------------------->
      d = text direction                    |   (x, y)
      n = d turned 90 deg clockwise         |     +-------------+
                                            |     |  width      | height
   upright  d=(1,0)   n=(0,1)               |     +-------------+
   turned   d=(0,1)   n=(-1,0)              v y (below the baseline)
   (90 cw)
                     page rect = O + along*d + across*n  (corner extrema)
                     page rotation = text angle + geometry rotation
```

The geometry is a `StampPlacement` in millimetres expressed in that frame: `x` along the text, `y` below the baseline, `width`/`height` the pre-rotation extent, `rotation` clockwise relative to the text; `None` offsets mean 0 and `page`/`dpi` are ignored.
Its rotated extent is mapped corner by corner onto the page, and the result, on the matched page and with the text angle added to its rotation, flows through the same PDF compositing and bounds validation as a consumer placement.
Units differ from the ZPL keyword geometry, which is offset in label axes from a dot origin, so the PDF geometry is a separate seed field.

The resolution chain stays placement before consumer keyword before seed.
A consumer keyword takes its geometry from a geometry-only placement, else from the injected `registry`, else from the seed's keyword geometry for the document's format.
With neither placement nor keyword, a PDF seed resolves by its keyword only when it carries `pdf_keyword_placement`; a seed with only a coordinate placement resolves there without consulting its keyword, so existing seeds are unchanged.
Classification's `page` flows into the keyword search as the target page.

Measured on the captures, the keyword run starts at page (157.717, 677.733) pt turned 90 degrees clockwise on the single-page layouts and at (157.717, 371.644) pt upright on page 2 of the two-page booking.

### Implementation plan

| Task | Commit | Files |
|------|--------|-------|
| 6.2 | `feat(sdk): anchor pdf stamps by keyword in page text` | `modules/sdk/karrio/core/utils/stamping.py` (`StampSeed.pdf_keyword_placement`, `_TextRunCollector`, `_resolve_pdf_keyword_placement`, `stamp_document`), `modules/sdk/tests/core/stamping_helpers.py` (`text_runs_pdf_b64`), `modules/sdk/tests/core/test_stamping_pdf_keyword.py`, `modules/sdk/tests/core/test_stamping_resolution.py` |

### Testing strategy

`test_stamping_pdf_keyword.py` generates PDFs whose keyword runs sit at explicit text matrices, and asserts the overlay's `cm` against literals derived from the keyword position placed in the test.

| Case | Expected |
|------|----------|
| Keyword upright, turned 90 degrees clockwise, and counter-clockwise | stamp at the keyword origin plus the geometry, oriented along the text |
| Keyword inside a form XObject with a `/Matrix`, drawn under a `cm` | origin composed into page space |
| Keyword within a longer run | anchored at the run's start |
| Keyword on pages 1 and 2 with `page=2`; keyword on page 2 only without `page` | stamp on page 2 only |
| Keyword on no page, or not on the named page | `ValueError` naming the keyword |
| Target page without text | `ValueError`: cannot be located without page text |
| Text at 45 degrees | `ValueError` naming the keyword |
| Seed with `pdf_keyword_placement`, with and without `page` | resolves by keyword on the target page |
| Seed with only a coordinate PDF placement and a ZPL keyword | resolves at the coordinates wherever the keyword sits |
| Consumer keyword with seed or injected-registry geometry | seed or registry geometry at the consumer's keyword |

## ZPL reading-frame and format anchoring

### Problem

A live International Parcel (`91`) ZPL booking returned two formats: the parcel label, then an upright (`^FWN`) CN22 with the keyword at `^FO25,785` in a format of `^LL840`.
The ZPL keyword geometry was a label-axis offset from `^FO`, measured on the rotated (`^FWR`) letter CN22, and the stamp was spliced before the stream's last `^XZ`; on the upright CN22 the seed resolved to `^FO12,1053`, beyond the format's printable length.

### Design

Formats are delimited by `^XZ` alone: a format spans from just after the previous `^XZ` (or the stream start) to its own `^XZ`, so a redundant header `^XA` opening a format (as PostNord emits) does not start another.
The keyword locator counts formats while it scans and resets its running `^FO`, `^FW` orientation and `^CF` height at each `^XZ`.
Every keyword-resolved ZPL stamp, whichever geometry it uses, is spliced before the `^XZ` closing the format that contains the matched field; a placement without a keyword keeps splicing before the last `^XZ`.

The matched field's effective orientation is its field font's (`^A<font><orientation>`, ending at the field's `^FS`) when it names one, else the format's latest `^FW`, else normal; `N`/`R`/`I`/`B` map to 0/90/180/270 degrees clockwise.
Its character height is the field font's height, else the format's latest `^CF` height, else the 9-dot power-on default.

`^FO` addresses the top-left of the field's box in label axes whatever the orientation, so it is where the text starts only for a normal field.
The reading frame's origin is where the text starts, on the glyph-top edge of its character cell:

```
   N (0)                         R (90 cw)
   ^FO = O                       ^FO    O = ^FO + (height, 0)
    O------------> x (along)       +----O
    | Date and Sender's...         |  D |      text runs down,
    v y (toward the underside)     |  a |      glyph tops face right
                                   |  t |
                                   v    v x (along)
                               y (underside) points left
```

An inverted or bottom-up field starts one rendered text length from `^FO`, which depends on the printer's font metrics and is not in the stream, so a reading-frame geometry against such a field raises naming the keyword and the orientation.

`StampSeed.zpl_keyword_frame_placement` carries geometry in that frame with the meaning of `pdf_keyword_placement`: `x` along the text, `y` toward its underside, `width`/`height` the pre-rotation extent, `rotation` relative to the text, plus `dpi`.
It is mapped onto the label by the same corner mapping as the PDF geometry, and the text's orientation adds to its rotation.
`keyword_placement` keeps its label-axis semantics, so the existing seeds resolve byte-identically; a consumer-supplied geometry and an injected registry's geometry remain label-axis offsets.
Redefining `keyword_placement` as reading-frame geometry was rejected because the PostNord CN22 seed (`x` -1.673, `y` 33.529 mm, rotation 90) would resolve elsewhere on the rotated layout.

The reading-frame geometry equivalent to that seed on the rotated layout (keyword `^FO20,35`, `^FWR`, `^CF0,20,20`, so text start at dots (40, 35)) is `x` 33.529, `y` -3.4245, 49.1 x 7.6 mm, rotation 0; it resolves to `^FO7,303` with a 61 x 392-dot raster there, and to `^FO293,758` with an unrotated 392 x 61-dot raster in the second format of the International Parcel capture (keyword `^FO25,785`, `^FWN`), inside its `^LL840`.

### Implementation plan

| Task | Commit | Files |
|------|--------|-------|
| 7.1 | `feat(sdk): anchor zpl keywords in the field's reading frame and format` | `modules/sdk/karrio/core/utils/stamping.py` (`StampSeed.zpl_keyword_frame_placement`, `StampRequest.zpl_format`, `_splice_zpl_field`, `_match_zpl_field`, `_zpl_text_origin`, `_frame_placement`, `_resolve_keyword_placement`, `stamp_document`), `modules/sdk/tests/core/test_stamping_zpl_frame.py` |

### Testing strategy

`test_stamping_zpl_frame.py` builds its ZPL in the test and asserts `^GFA` origins and byte counts against hand-computed literals.

| Case | Expected |
|------|----------|
| Rotated single format, label-axis seed | `^FO7,303`, 61 x 392 dots, spliced before the only `^XZ`, output otherwise unchanged |
| Rotated single format, equivalent reading-frame seed | byte-identical to the label-axis output |
| Label format then upright CN22 format with a header `^XA` | `^FO293,758`, 392 x 61 dots, before the second `^XZ`; first format byte-identical |
| Upright CN22 format then label format | spliced before the first `^XZ`; label format unchanged |
| `^A0R,30,30` field under `^FWN` | frame turned 90 degrees from text start `^FO` + 30 dots |
| `^FW` and `^CF` in an earlier format | do not leak into the next format |
| `^A` without an orientation | keeps the format's `^FW` |
| Frame geometry against an `^FWI` field | `ValueError` naming the keyword and 180 degrees |

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

A PDF key resolves `placement`, or `keyword` plus `pdf_keyword_placement` when the seed carries it; a ZPL key resolves `keyword` plus `zpl_keyword_frame_placement` in the field's reading frame when the seed carries it, else `keyword` plus `keyword_placement`, whose `x`/`y` are offsets from the located `^FO` in label axes.
A seed measured for PDF keyword anchoring expresses the strip in the keyword's reading frame (see [PDF keyword anchoring](#pdf-keyword-anchoring)), so it holds for every layout that prints the keyword at the same distance from the strip, upright or turned.
A key with a concrete paper variant never matches another variant; a `*` paper segment matches any page.

Measuring a seed:

- Measure the target strip on the PDF form in millimetres, then encode it under the placement semantics: pre-rotation extent, rotation, and the rotated extent's top-left as the anchor.
- For ZPL, map the PDF form's drawing onto the label frame and cross-check a few rules or separators at sub-dot precision; the same physical strip expressed as PDF millimetres and as a keyword offset in dots must agree.
- A seed is measured data tied to the placement semantics in force when it was measured. When the semantics change (for example from a centre pivot to a corner anchor), re-measure rather than convert algebraically: a conversion can preserve the centre while swapping the rendered axes.
- Test oracles for a seed derive from the measurement, not from the seed object, so a wrong seed cannot pass a circular check.
- Bump `revision` only on a genuine re-measurement, not when adding data such as a keyword.
- A per-form target region is seed-authoring data; the backends check only page and operand bounds.
