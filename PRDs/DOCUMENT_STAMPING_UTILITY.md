# Generalized Document Stamping Utility and Workflow

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-09-21 |
| Status | Planning — decision record priming a future OpenSpec change |
| Owner | Joaqim Planstedt |
| Type | Architecture |
| Reference | [AGENTS.md](../AGENTS.md) |

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
12. [Appendices](#appendices)

---

## Executive Summary

Third-party consumers of the Karrio SDK and API need to composite raster images —
signatures and letterheads — onto carrier duty documents (CN22 declarations,
commercial invoices) that karrio returns as base64 in either PDF or ZPL format.
This PRD cements the design for a generalized, format-multiplexing stamping
utility plus the consumer workflow around it, so that a consumer hands over a
PNG and an intent and never branches on document format themselves.
The PRD is a decision record: implementation is deliberately deferred to a
future session driven by an OpenSpec change proposal (see
[Appendix D](#appendix-d-handoff-to-openspec)).

### Key Architecture Decisions

1. **Sniff-and-dispatch multiplexer**: the utility detects document format by
   magic bytes (reusing the DHL Freight Sweden `LABEL_MAGICS` precedent) and
   routes to a per-format backend.
2. **Host-side ZPL compositing**: PNG is dithered to 1-bpp and embedded as a
   `^Gfa` hex graphic field with Floyd–Steinberg dithering; no printer-firmware
   features are required.
3. **Overlay-page PDF compositing**: the PNG is placed on a transparent overlay
   page sized to the target and merged via pypdf; raster placement uses
   reportlab in the SDK and weasyprint in the server documents module.
4. **Neutral-unit placement registry**: anchors are keyed by
   (carrier, document category, format, paper variant) and stored in
   millimetres from the top-left; each backend converts to its native units.
5. **Responsibility boundary**: karrio composites pixels; the consumer owns the
   legal semantics of what a stamped signature asserts.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| Format-multiplexing stamp utility (PDF, ZPL) | Carrier-side signature injection (no such PostNord API exists) |
| Signature overlay and letterhead underlay semantics | Karrio storing or verifying stamped documents post-return |
| Placement registry seeded for PostNord CN22 and FedEx commercial invoice | Dashboard or UI changes |
| Consumer workflow documentation with FedEx ETD precedent comparison | Options-framework changes beyond what layer C requires |
| Handoff plan for the future OpenSpec change | Implementation itself (deferred to that change) |

---

## Open Questions & Decisions

### Pending Questions

These are deliberately left open in this PRD; the future OpenSpec proposal must
resolve them (see [Appendix D](#appendix-d-handoff-to-openspec) for which
question gates which phase).

| # | Question | Context | Options | Status |
|---|----------|---------|---------|--------|
| Q1 | Which FedEx stamping position is the product target? | Determines whether karrio needs anything at all for the pre-upload path | A) Path 1 only: stamp consumer-generated CI before ETD upload, B) Path 2 only: stamp FedEx-rendered `docs.invoice` post-hoc, C) Both | ⏳ Pending |
| Q2 | Is ZPL stamping a real requirement, or is ZPL about labels while duty documents can be PDF-always? | PostNord couples customs printout format to booking label format; the explicit `/v3/customs/declaration/pdf` endpoint is PDF regardless | A) Support both formats fully, B) PDF-always for duty documents, ZPL out of scope, C) Both, with PostNord format decoupling | ⏳ Pending |
| Q3 | Who owns and maintains the placement registry across carrier form revisions? | Anchors silently break when carriers re-render forms; a misplaced stamp is worse than none because it looks signed | A) Karrio-owned per carrier (community amortized), B) Consumer-supplied coordinates with karrio-supplied defaults, C) Registry in connector packages | ⏳ Pending |
| Q4 | What is the server (layer C) exposure shape? | API consumers cannot call an SDK utility | A) Shipment-level option carrying base64 image (implicit), B) Explicit documents endpoint (explicit), C) Documents-module configuration per org | ⏳ Pending |
| Q5 | Is reportlab an acceptable SDK dependency? | Only needed for SDK-side PDF raster placement; server side needs nothing new (weasyprint present) | A) Accept reportlab, B) SDK ZPL-only, PDF stamping server-side only, C) Consumer-side PDF via their own stack | ⏳ Pending |

### Resolved Decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| D1 | Capability shape | Generalized format-multiplexing utility plus documented workflow, not per-carrier features | PDF and ZPL compositing share no mechanics; the multiplexer is the only shared abstraction | 2026-09-21 |
| D2 | Format detection | Magic-byte sniff (`%PDF-`, `^XA`) with fallbacks, reusing the DHL Freight Sweden `_label_type` pattern | Precedent exists in-tree and is live-verified against real carrier bytes | 2026-09-21 |
| D3 | ZPL embedding | Host-side PNG → 1-bpp → `^Gfa` hex graphic field, Floyd–Steinberg dithering | Universal printer support and deterministic quality; signature strokes survive dithering but not naive thresholding | 2026-09-21 |
| D4 | PDF embedding | Transparent overlay page merged with pypdf; raster placement via reportlab (SDK) or weasyprint (server documents module) | pypdf cannot place rasters; PyMuPDF rejected (AGPL); weasyprint already a server dependency | 2026-09-21 |
| D5 | Anchor units and keying | Millimetres from top-left of a 1-based page; registry key (carrier, `ShippingDocumentCategory` name, format, paper variant) | Neutral units convert cleanly to PDF points (bottom-left flip) and ZPL dots (dpi-scaled); category enum already normalizes document names | 2026-09-21 |
| D6 | Letterhead semantics | Letterhead is an underlay (PDF merge order: content over background); ZPL letterhead is out of practical scope | ZPL has no z-order — insertion before the carrier field stream is structural surgery with no thermal use case | 2026-09-21 |
| D7 | Output contract | Stamped document replaces `ShippingDocument.base64` in place; `format` is unchanged and always matches the input format | The consumer's document list shape is stable; implicit format support means format never leaks into consumer code | 2026-09-21 |
| D8 | Legal responsibility | Karrio composites pixels only; the consumer owns signature validity, authority, and paper-workflow semantics | Extends the PostNord customs verdict: the digital declaration is implicitly signed at EDI level; the printout is deliberately unsigned | 2026-09-21 |

### Edge Cases Requiring Input

| Edge Case | Impact | Proposed Handling | Needs Input? |
|-----------|--------|-------------------|--------------|
| PostNord CN22 arrives as ZPL because labels are ZPL | Stamped-paper workflow wants PDF | Explicit-declaration PDF endpoint today; format decoupling if Q2 → C | ✅ Yes (Q2) |
| FedEx renders its own commercial invoice | Stamp must be post-hoc on `docs.invoice` | Path 2 backend flow (sequence diagram below) | ✅ Yes (Q1) |
| Carrier re-renders a form and shifts the signature block | Stamp lands in the wrong place, looking signed | Registry revision field plus a visual smoke fixture per carrier | ✅ Yes (Q3) |

---

## Problem Statement

### Current State

Karrio returns duty documents as base64 strings in
`Documents.extra_documents` (`ShippingDocument(category, format, print_format,
base64, url)`), with `format` carrying `PDF`, `ZPL`, or `PNG` per the
`LabelType` enum. Nothing in karrio touches document pixels after a carrier
returns them, so a consumer who wants a signature on a PostNord CN22 or a
FedEx commercial invoice must implement format handling themselves:

```python
# Current: every consumer re-implements format branching and placement
doc = shipment.docs.extra_documents[0]

if doc.format == "PDF":
    # decode base64, build an overlay page at MediaBox size,
    # convert mm anchors to points with a bottom-left origin flip,
    # flatten PNG alpha, merge, re-encode
    ...
elif doc.format == "ZPL":
    # decode PNG, dither to 1-bpp, pad rows to byte boundaries,
    # hex-encode to GRF, know the printer dpi, splice ^FO/^Gfa
    # into the carrier field stream
    ...
```

### Desired State

```python
import karrio.lib as lib

stamped = lib.stamp_document(
    shipment.docs.extra_documents[0],
    image=SIGNATURE_PNG,          # base64 PNG, provided by the consumer
    carrier="postnord",
    doc_type="cn22",
)
# stamped.format == doc.format; stamped.base64 carries the composited bytes
```

The consumer states intent; the utility sniffs format, resolves the anchor
from the registry (or takes explicit coordinates), composites, and returns the
document in the same shape and format it received.

### Problems

1. **Format duplication**: every consumer reimplements PDF and ZPL compositing,
   including two unrelated coordinate systems, two alpha/depth models, and the
   ZPL dpi trap (a 300-dpi assumption on a 203-dpi printer displaces the stamp
   by 50%).
2. **Silent quality failures**: naive thresholding destroys anti-aliased
   signature strokes; un-flattened RGBA overlays white-box over PDF form
   content; both failures look like success.
3. **No shared anchoring knowledge**: the signature block of each carrier form
   is per-carrier, per-paper-size knowledge that drifts when carriers re-render
   forms; today it exists nowhere.
4. **No precedent documentation**: consumers cannot see how the workflow
   relates to the established FedEx ETD document flow, which already solves the
   adjacent problem (consumer-generated versus carrier-rendered documents).

---

## Goals & Success Criteria

### Goals

1. One utility entry point that accepts any karrio duty document and a base64
   PNG, and returns a stamped document of the same format.
2. Deterministic ZPL output: host-side dithering and GRF encoding with zero
   printer-firmware dependencies.
3. A placement registry seeded for at least PostNord CN22 (PDF, A4) and FedEx
   commercial invoice (PDF, letter), keyed on normalized document categories.
4. A documented consumer workflow, per carrier, enriched by comparison with the
   FedEx ETD precedent.
5. An OpenSpec handoff precise enough that the implementation session starts
   from decisions, not open design.

### Success Criteria

| Metric | Target | Priority |
|--------|--------|----------|
| Consumer format branching | Zero branches in consumer code | Must-have |
| ZPL compatibility | Output valid on firmware without `~DY` PNG support | Must-have |
| Signature legibility after dithering | Stroke continuity preserved on 203 dpi fixtures | Must-have |
| PDF text layer | Untouched (no rasterization of carrier content) | Must-have |
| Registry coverage at launch | PostNord CN22 + FedEx commercial invoice | Must-have |
| Printer graphic caching (`~DY`/`^XG`) | Send-once-per-printer path available | Nice-to-have |

### Launch Criteria

**Must-have (P0):**

- [ ] Stamp utility passes the test strategy below (SDK scope)
- [ ] Registry seeded for the two launch documents
- [ ] Workflow guide published alongside the SDK guide conventions

**Nice-to-have (P1):**

- [ ] Server documents-module integration (gated on Q4)
- [ ] `~DY`/`^XG` caching variant

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| A. Pure consumer-side (karrio untouched) | Available today; zero karrio cost | Every consumer owns the mux, dithering, and anchor drift | Documented as fallback |
| B. SDK utility layer | Shared, tested, format-multiplexed; serves SDK consumers directly | reportlab dependency question (Q5) | **Selected** (primary) |
| C. Server documents-module pipeline | Zero new server deps (weasyprint present); serves API consumers implicitly | Options-framework plumbing is carrier-scoped; multi-tenant image handling | **Selected** (secondary, gated on Q4) |
| D. Carrier-native injection | FedEx ETD accepts consumer bytes pre-upload | PostNord has no injection API; solves only the FedEx pre-shipment case | Documented as Path 1 |

### Trade-off Analysis

B and C share all compositing logic; they differ only in raster-placement
library and exposure surface, so the multiplexer, ZPL encoder, and registry are
written once in the SDK and consumed by both. A remains available to any
consumer regardless of karrio releases, which keeps the utility non-blocking
and its adoption voluntary. D is not a utility at all but a workflow fact: where
a carrier accepts consumer-generated documents, stamping upstream of karrio is
always simpler, and the utility targets the residual carrier-rendered cases.

---

## Technical Design

### Existing Code Analysis

All components below were verified against `develop` on 2026-09-21.

| Component | Location | Reuse Strategy |
|-----------|----------|----------------|
| Document bundling dispatch (`bundle_pdfs`/`bundle_imgs`/`bundle_zpls`/`bundle_base64`) | `modules/sdk/karrio/core/utils/helpers.py:77-130` | Sibling `stamp_*` utilities follow the same dispatch shape |
| `zpl_to_pdf` (Labelary HTTP) | `modules/sdk/karrio/core/utils/helpers.py:134-143` | Not reused (network-dependent); referenced as prior art |
| Magic-byte format sniff | `modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/shipment/create.py:82-113` | `LABEL_MAGICS = ((b"%PDF-", "PDF"), (b"^XA", "ZPL"))` lifted into shared helper with contentType and config fallbacks |
| SDK dependencies (pypdf, Pillow, python-barcode) | `modules/sdk/pyproject.toml:20-33` | ZPL backend needs nothing new; PDF backend adds reportlab only if Q5 → A |
| `ShippingDocument` / `Documents` models | `modules/sdk/karrio/core/models.py:430-450` | Stamp operates on `ShippingDocument`, replaces `base64`, preserves `format` (D7) |
| `LabelType` enum (PDF, ZPL, PNG) | `modules/sdk/karrio/core/units.py:27-30` | Output format vocabulary |
| `ShippingDocumentCategory` StrEnum with `.map().name_or_key` | `modules/sdk/karrio/core/units.py:153+` | Registry document key; PostNord `printoutComposition` kinds must map into it |
| Documents server module (weasyprint, pyzint) | `modules/documents/pyproject.toml:19-20` | Layer C home; HTML overlay → PDF → pypdf merge with no new deps |
| FedEx ETD upload (`/documents/v1/etds/upload`, ETDPreshipment/ETDPostshipment) | `modules/connectors/fedex/karrio/mappers/fedex/proxy.py:89-115`, `providers/fedex/document.py:42-88` | Path 1 workflow precedent |
| FedEx ETD options (`doc_files`, `doc_references`, `fedex_electronic_trade_documents`) | `modules/connectors/fedex/karrio/providers/fedex/units.py:332,392-394` | Reference-workflow precedent for registry keying |
| FedEx `UploadDocumentType` vocabulary | `modules/connectors/fedex/karrio/providers/fedex/units.py:502-519` | Document-typing precedent |
| FedEx shipment document parse (INVOICE → `docs.invoice`, rest → `extra_documents`) | `modules/connectors/fedex/karrio/providers/fedex/shipment/create.py:62-107` | Path 2 target surface |
| FedEx ETD attachment and render request (`attachedDocuments`, `requestedDocumentTypes=["COMMERCIAL_INVOICE"]`) | `modules/connectors/fedex/karrio/providers/fedex/shipment/create.py:388-406` | Render-intent precedent |
| PostNord customs printouts (by-id `pdf`/`zpl`, coupled to booking label format) | `modules/connectors/postnord/karrio/mappers/postnord/proxy.py:108-252` | Coupling fact motivating Q2 |
| PostNord explicit customs declaration endpoints | `modules/connectors/postnord/karrio/mappers/postnord/proxy.py:309-340` | PDF-always escape hatch (paperSize/rotate params) |
| PostNord `_customs_documents` parse (category from `printoutComposition`, `labelFormat` fallback) | `modules/connectors/postnord/karrio/providers/postnord/shipment/create.py:91-223` | Category mapping input for the registry |
| Server API docs serialization | `modules/core/karrio/server/core/serializers.py:1415-1432` | Confirms `extra_documents` as the API surface name |

### Architecture Overview

```
                      ┌─────────────────────────────────────────┐
                      │                karrio SDK               │
                      │                                         │
  ShippingDocument    │  ┌─────────┐   ┌──────────────────┐     │
  (base64, format) ───┼─▶│ sniffer │──▶│ stamp_document() │     │
                      │  └─────────┘   └───┬─────────┬────┘     │
                      │                    │         │          │
                      │            ┌────────▼─┐  ┌───▼────────┐  │
                      │            │ PDF      │  │ ZPL        │  │
                      │            │ backend  │  │ backend    │  │
                      │            │ flatten  │  │ flatten    │  │
                      │            │ overlay  │  │ dither 1bpp│  │
                      │            │ merge    │  │ GRF hex    │  │
                      │            │ (pypdf + │  │ ^FO/^Gfa   │  │
                      │            │ reportlab│  │ splice     │  │
                      │            │ or weasy)│  │            │  │
                      │            └──────────┘  └────────────┘  │
                      └───────────────┬──────────────┬───────────┘
                                      ▼              ▼
                       ShippingDocument out: same format,
                       stamped base64 (D7)

  ┌────────────────────────────────────────────────────────────────┐
  │                            consumers                            │
  │                                                                │
  │  SDK consumer ────────── calls lib.stamp_document directly     │
  │  API consumer ────────── server documents module (layer C, Q4) │
  │  any consumer ────────── Path 1: stamp before carrier upload   │
  └────────────────────────────────────────────────────────────────┘
```

### Sequence Diagram

Post-hoc stamping (Path 2 applies to both carriers' carrier-rendered docs):

```
┌────────┐      ┌────────────┐      ┌───────────────┐      ┌───────────┐
│Consumer│      │ karrio SDK │      │ stamp utility │      │ registry  │
└───┬────┘      └─────┬──────┘      └──────┬────────┘      └─────┬─────┘
    │  book + customs │                   │                     │
    │────────────────>│                   │                     │
    │  docs.extra_documents (PDF or ZPL)  │                     │
    │<────────────────│                   │                     │
    │  stamp(doc, png, carrier, doc_type) │                     │
    │────────────────────────────────────>│  resolve anchor     │
    │                                     │────────────────────>│
    │                                     │  StampPlacement (mm)│
    │                                     │<────────────────────│
    │  sniff → backend → convert units → composite               │
    │  ShippingDocument, format unchanged │                     │
    │<────────────────────────────────────│                     │
```

### Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  FEDEX — PATH 1 (consumer-generated CI, stamp BEFORE karrio)     │
├──────────────────────────────────────────────────────────────────┤
│  stamp PNG onto own CI PDF ──▶ DocumentFile (base64)             │
│        ──▶ POST /documents/v1/etds/upload (ETDPreshipment)       │
│        ──▶ doc_id ──▶ options.doc_files / doc_references         │
│        ──▶ attachedDocuments at booking. Karrio stores nothing.  │
├──────────────────────────────────────────────────────────────────┤
│  FEDEX — PATH 2 (carrier-rendered CI, stamp AFTER karrio)        │
├──────────────────────────────────────────────────────────────────┤
│  booking requests requestedDocumentTypes=["COMMERCIAL_INVOICE"]  │
│        ──▶ shipmentDocuments INVOICE ──▶ docs.invoice (base64)   │
│        ──▶ stamp_document ──▶ stamped docs.invoice               │
├──────────────────────────────────────────────────────────────────┤
│  POSTNORD — post-booking customs printouts                       │
├──────────────────────────────────────────────────────────────────┤
│  UX booking, customs declared ──▶ by-id labels {pdf|zpl}         │
│        (format coupled to booking label format — Q2)             │
│        ──▶ docs.extra_documents (category from composition)      │
│        ──▶ stamp_document ──▶ stamped CN22                       │
│  alternative today: explicit /v3/customs/declaration/pdf         │
│        (paperSize param; PDF regardless of label format)         │
└──────────────────────────────────────────────────────────────────┘
```

### ZPL Conversion Pipeline

```
  PNG (RGBA)
    │  Pillow: flatten alpha onto white
    ▼
  grayscale
    │  Floyd–Steinberg dither
    ▼
  1-bpp bitmap ── pad rows to byte boundary ──▶ uppercase hex
                                                    │
                                                    ▼
              ^FO <x>,<y> ^Gfa,<total>,<rowbytes>,<rows>,<hex>
              spliced into the carrier ZPL field stream
```

Optional cache variant (P1): store the encoded graphic once on printer
flash via `~DY` and recall it per print with `^XG`, mirroring the
upload-once-reference-thereafter shape of FedEx ETD.

### Data Models

Illustrative only; final shape belongs to the OpenSpec design phase.

```python
@attr.s(auto_attribs=True)
class StampPlacement:
    """Anchor rectangle for compositing an image onto a document page."""

    page: int = 1
    x: float = None        # millimetres from top-left of the page
    y: float = None
    width: float = None
    height: float = None
    dpi: int = 203         # ZPL target density (203 / 300 / 600)


@attr.s(auto_attribs=True)
class StampRequest:
    """One image-compositing operation against a carrier document."""

    carrier: str = None                # registry key segment
    doc_type: str = None               # ShippingDocumentCategory name
    image: str = None                  # base64-encoded PNG
    placement: StampPlacement = None   # explicit anchor, else registry lookup
    layer: str = "overlay"             # overlay | underlay
```

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `carrier` | string | With registry lookup | Registry key segment; unused when `placement` is explicit |
| `doc_type` | string | With registry lookup | `ShippingDocumentCategory`-normalized name, e.g. `cn22`, `commercial_invoice` |
| `image` | string | Yes | base64 PNG; auto-trimmed to ink bounding box before compositing |
| `placement.page` | int | No (default 1) | 1-based page index for multi-page documents |
| `placement.x/y` | float | With registry lookup | Millimetres from page top-left |
| `placement.width/height` | float | No | Draw size; defaults to natural size at native PDF scale or dpi |
| `placement.dpi` | int | ZPL only | Target printer density for dot conversion |
| `layer` | string | No (default overlay) | `overlay` for signatures; `underlay` for letterheads (PDF only, D6) |

### FedEx ETD Precedent: Usage and Expectations by Comparison

The FedEx connector already resolves, for electronic documents, the same
design forces the stamping workflow faces for paper documents. The comparison
below is the documented expectation set this PRD builds on.

| Dimension | FedEx ETD precedent (in-tree today) | Generalized stamping analog |
|-----------|-------------------------------------|------------------------------|
| Document typing | `UploadDocumentType` closed vocabulary: `COMMERCIAL_INVOICE`, `PRO_FORMA_INVOICE`, `CERTIFICATE_OF_ORIGIN`, USMCA variants | `ShippingDocumentCategory` names as registry keys; PostNord `printoutComposition` kinds map into the same enum |
| Consumer-generated bytes | `DocumentFile` base64 passes through karrio untouched; karrio retains nothing | Path 1: the stamp happens upstream of karrio; the utility is not involved |
| Upload once, reference thereafter | upload → `doc_id` → `doc_files`/`doc_references` at booking | encode once → printer-stored graphic name → `^XG` recall per print |
| Workflow timing | `ETDPreshipment` vs `ETDPostshipment` | stamp upstream of the carrier vs stamp returned bytes |
| Render intent | `requestedDocumentTypes=["COMMERCIAL_INVOICE"]` asks the carrier to render | Format pinning: request PDF duty documents regardless of label format (PostNord explicit endpoint; Q2) |
| Return surface | `shipmentDocuments` routed to `docs.invoice` / `extra_documents` with `format=docType` | Stamped output replaces `base64` in place; `format` unchanged (D7) |
| Responsibility boundary | FedEx owns document validity; karrio transports bytes | Karrio composites pixels; consumer owns legal semantics (D8) |

Expected usage per consumer type follows from the table: an SDK consumer
stamps returned documents directly (Path 2 shape); an API consumer eventually
receives the same capability through the documents module (layer C); a
consumer generating its own commercial invoice stamps before upload and lets
the existing FedEx ETD reference workflow carry the bytes.

### PostNord Category Mapping Note

`_customs_documents` sets `ShippingDocument.category` from the sorted
`printoutComposition` kinds (e.g. `cn22`), falling back to
`customs_declaration`. The registry must resolve categories through
`ShippingDocumentCategory.map(...).name_or_key` so printout-composition
strings and normalized names converge on one key. If a composition kind has
no enum entry, the implementation session decides between extending the enum
and registering an alias.

---

## Edge Cases & Failure Modes

### Edge Cases

| Scenario | Expected Behavior | Handling |
|----------|-------------------|----------|
| Un-flattened RGBA signature on PDF | Transparent background preserved, no white box | Pillow pre-flatten onto white; reportlab `mask='auto'` |
| Anti-aliased thin signature strokes at 203 dpi | Strokes remain continuous | Floyd–Steinberg dithering, never naive threshold (D3) |
| ZPL document with unknown dpi | Stamp placed at correct physical size | `placement.dpi` explicit; refuse dot-coordinate ambiguity rather than guess |
| GRF row length not byte-aligned | Printer renders skewed graphic | Rows padded to byte boundary before hex encoding |
| Multi-page commercial invoice | Signature on page 1 by default | `placement.page`; registry may pin other pages |
| Carrier PDF with AcroForm fields | Form still fillable after stamping | Overlay merge does not touch form dictionaries |
| PostNord `rotate` variant | Anchor tracks the rotated layout | Paper-variant registry key segment |
| Sniff encounters PNG document | Passed through or rejected explicitly | `LabelType.PNG` recognized; stamping PNG-on-PNG out of scope, returns explicit error |
| Registry miss for (carrier, doc_type, format) | No silent fallback to a wrong anchor | Explicit error naming the missing key; consumer may supply `placement` |

### Failure Modes

| What Can Go Wrong | Impact | Mitigation |
|-------------------|--------|------------|
| Carrier re-renders form; anchor drifts | Stamp lands wrongly, document looks signed | Registry revision field; per-carrier visual smoke fixture in tests; Q3 governance |
| White-box alpha failure | Signature hides form content | Flattening step mandatory in both backends; golden PDF fixture asserts XObject transparency |
| Dithering regression | Broken, unprofessional signature | Snapshot fixtures for stroke continuity at 203 and 300 dpi |
| Oversized GRF floods printer memory | Print job fails | Image auto-trim plus size ceiling with explicit error |
| Firmware without `~DY` PNG support | Cache variant fails | `^Gfa` is the default path; caching is strictly optional (P1) |
| Stamped document misused legally | Invalid assertion of signature | D8 boundary documented in the utility docstring and workflow guide |

---

## Implementation Plan

All phases Pending; this table primes the OpenSpec `tasks.md`, it does not
execute it.

### Phase 1: SDK core utility

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Shared magic-byte sniff helper (generalize DHL `LABEL_MAGICS`) | `modules/sdk/karrio/core/utils/helpers.py` | Pending | S |
| ZPL backend: flatten, dither, GRF encode, `^FO/^Gfa` splice | `modules/sdk/karrio/core/utils/` (new `stamping.py`) | Pending | M |
| PDF backend: overlay build and merge (reportlab if Q5 → A) | same | Pending | M |
| `StampPlacement` / `StampRequest` models | `modules/sdk/karrio/core/models.py` or `stamping.py` | Pending | S |
| `lib.stamp_document` entry point with dispatch | `modules/sdk/karrio/lib.py` re-export | Pending | S |

### Phase 2: Placement registry

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Registry structure with category normalization | `modules/sdk/karrio/core/utils/stamping.py` | Pending | S |
| PostNord CN22 (PDF, A4) seed measured from live printout | registry module | Pending | S |
| FedEx commercial invoice (PDF, letter) seed | registry module | Pending | S |
| `~DY`/`^XG` cache variant | `stamping.py` | Pending | S |

### Phase 3: Server integration (gated on Q4)

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Documents-module stamping pipeline (weasyprint overlay) | `modules/documents/karrio/documents/` | Pending | M |
| Exposure surface per Q4 resolution | TBD | Pending | M |

### Phase 4: Documentation

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Workflow guide with FedEx comparison table | `docs/notes/` or guide location per repo convention | Pending | S |
| OpenSpec proposal, design, specs, tasks | `openspec/changes/add-document-stamping/` | Pending | S |

**Dependencies:** Phase 2 requires Phase 1 models; Phase 3 requires Q4 and
Phase 1; Phase 4's guide requires Phases 1-2 to describe real behavior.

---

## Testing Strategy

### Test Categories

| Category | Location | Coverage Target |
|----------|----------|-----------------|
| Sniff unit tests | `modules/sdk/tests/` | All `LabelType` values plus adversarial bytes |
| GRF encoder golden vectors | `modules/sdk/tests/` | Known bitmaps → exact hex, padded rows |
| Dither snapshot tests | `modules/sdk/tests/` | Stroke continuity fixtures at 203/300 dpi |
| PDF merge round-trip | `modules/sdk/tests/` | Page count, AcroForm survival, XObject presence |
| Registry resolution | `modules/sdk/tests/` | Key hits, misses, category normalization |
| Connector fixtures | `modules/connectors/postnord/tests/`, `modules/connectors/fedex/tests/` | Real carrier document bytes |

### Test Cases

```python
class TestStampDocument(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_stamp_pdf_preserves_format_and_pages(self):
        """Stamping a PDF CN22 keeps format, page count, and form fields."""
        stamped = lib.stamp_document(CN22_PDF_DOC, image=SIGNATURE, carrier="postnord", doc_type="cn22")

        self.assertEqual(stamped.format, "PDF")
        self.assertEqual(page_count(stamped.base64), page_count(CN22_PDF_DOC.base64))

    def test_stamp_zpl_embeds_grf_field(self):
        """Stamping a ZPL printout splices a padded-row ^Gfa field."""
        stamped = lib.stamp_document(CN22_ZPL_DOC, image=SIGNATURE, carrier="postnord", doc_type="cn22")

        self.assertEqual(stamped.format, "ZPL")
        self.assertIn(b"^Gfa,", base64_decode(stamped.base64))
```

### Running Tests

```bash
# From repository root
source bin/activate-env
python -m unittest discover -v -f modules/sdk/tests

# Connector fixture refresh against recorded bytes
python -m unittest discover -v -f modules/connectors/postnord/tests
```

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Anchor drift from carrier form revisions | High | Medium | Registry revisioning, visual smoke fixtures, Q3 governance decision |
| reportlab dependency rejected (Q5) | Medium | Low | Server path needs nothing new; SDK can ship ZPL-only |
| ZPL firmware variance | Medium | Low | `^Gfa` baseline targets all printers; caching optional |
| Legal misuse of stamped signatures | High | Low | D8 boundary in docs; utility asserts nothing about validity |
| Scope creep into document storage/verification | Medium | Medium | Out-of-scope table enforced at OpenSpec proposal review |

---

## Migration & Rollback

### Backward Compatibility

- **API compatibility**: no existing endpoint, serializer, or document payload
  changes; stamping is additive and opt-in.
- **Data compatibility**: no schema or migration impact; stamped documents are
  ordinary `ShippingDocument` values in flight.
- **Feature flags**: unnecessary; consumers invoke the utility explicitly
  (layer C exposure, if built, follows Q4 and would carry its own gating).

### Rollback Procedure

1. **Identify issue**: failing stamp tests or consumer-reported bad output.
2. **Revert**: remove the utility module and re-export; no data to unwind.
3. **Verify**: full SDK test suite plus connector suites green.

---

## Appendices

### Appendix A: Decision Provenance

Decisions D1-D8 were reached in an exploration session on 2026-09-21
(`/opsx:explore`), grounded by a read-only repository reconnaissance covering
SDK dependencies, the unified documents model, the DHL Freight Sweden
magic-byte sniff, the FedEx ETD surface, and the PostNord customs printout
path (all citations in Existing Code Analysis). The PostNord legal framing in
D8 extends the archived change
`openspec/changes/archive/2026-09-21-postnord-customs-declaration/` and its
guide `docs/notes/postnord/customs-declaration-sdk-guide.md`.

### Appendix B: ZPL Technical Reference

- `^FO x,y ^Gfa,total,rowbytes,rows,<hex>`: hex graphic field; universal
  Zebra support; `rowbytes` reflects byte-padded rows.
- `~DY` / `^XG`: printer-flash graphic storage and recall; requires
  Link-OS-era firmware; used only by the optional cache variant.
- Origins and units: ZPL is top-left in dots at printer density
  (203/300/600 dpi); PDF is bottom-left in points (1 pt = 1/72 in);
  registry stores millimetres and converts per backend.
- Dithering: Floyd–Steinberg error diffusion preserves anti-aliased strokes;
  ordered dithering is the acceptable fallback if diffusion artifacts appear
  on letterhead gradients.

### Appendix C: Carrier-Specific Reference

| Carrier | Surface | Notes |
|---------|---------|-------|
| PostNord | `POST /rest/shipment/v3/labels/ids/{pdf,zpl}?definePrintout=onlyCustomsDeclarations` | Implicit booking-time fetch; format coupled to label format |
| PostNord | `POST /rest/shipment/v3/customs/declaration/pdf` | Explicit; `paperSize`, `rotate`, alignment params; PDF always |
| FedEx | `POST /documents/v1/etds/upload` | `ETDPreshipment` / `ETDPostshipment` workflows; returns doc ids |
| FedEx | shipment create `attachedDocuments`, `requestedDocumentTypes` | Consumer-doc reference and carrier-render intent |

### Appendix D: Handoff to OpenSpec

Proposed change name: `add-document-stamping`.
Proposed capability path: `openspec/specs/documents/stamping/spec.md` —
deviating from the observed `<carrier>/<capability>` convention because the
capability is carrier-agnostic; carrier specificity lives in registry seeds,
not in the spec. The proposal session should:

1. Resolve Q1 and Q2 first — they decide whether Phase 1 includes both
   backends or PDF-first.
2. Resolve Q3 before Phase 2 — registry governance shapes where seeds live.
3. Resolve Q4 and Q5 before Phase 3 — they decide server exposure and the
   reportlab question.
4. Carry this PRD as the decision record; `design.md` owns the final model
   shapes, `specs/documents/stamping/spec.md` owns the SHALL-level behavior
   (format preservation, registry miss errors, dithering guarantees), and
   `tasks.md` derives from the Implementation Plan above.
