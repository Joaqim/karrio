# Generalized Document Stamping Utility and Workflow

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.1 |
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
2. **PDF-first scope**: PDF is the initial and default target format; the ZPL
   backend is a planned follow-up, not a launch requirement.
3. **Overlay-page PDF compositing with zero new dependencies**: the PNG becomes
   a single-page image PDF via Pillow and is scaled into place with a pypdf
   transformation merge; reportlab is rejected for the SDK and weasyprint
   remains only a server-side option.
4. **Consumer-supplied placement as the primary path**: anchors are millimetre
   rectangles from the page top-left supplied by the consumer; karrio-supplied
   defaults are optional registry seeds keyed by (carrier, document category,
   format, paper variant), accruing incrementally.
5. **Responsibility boundary**: karrio composites pixels; the consumer owns the
   legal semantics of what a stamped signature asserts.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| Format-multiplexing stamp utility (PDF at launch, ZPL follow-up) | Carrier-side signature injection (no such PostNord API exists) |
| Signature overlay and letterhead underlay semantics | Changes to the existing FedEx ETD flow |
| Consumer-supplied anchor placement, plus optional registry seeds | Karrio storing or verifying stamped documents post-return |
| Consumer workflow documentation with FedEx ETD precedent comparison | API/server exposure (deferred pending a precedent survey, D12) |
| Handoff plan for the future OpenSpec change | Implementation itself (deferred to that change) |

---

## Open Questions & Decisions

### Pending Questions

The product questions Q1-Q5 are resolved (D9-D13 below). What remains open is
narrowly technical and belongs to the OpenSpec design phase.

| # | Question | Context | Options | Status |
|---|----------|---------|---------|--------|
| Q6 | Does Pillow's PDF writer preserve PNG alpha (SMask), or must the overlay be white-flattened? | Decides whether the PDF overlay can carry true transparency or relies on blank-block placement | A) SMask preserved — true alpha overlay, B) White-flatten — acceptable inside blank signature blocks, letterhead underlay unaffected | ⏳ Design spike |
| Q7 | Does precedent exist for a generalized server-side surface over an SDK utility? | D12 gates any API exposure on finding similar precedents (documents module, other generalized surfaces) | A) Precedent found — shape layer C on it, B) No precedent — SDK-only indefinitely | ⏳ Survey |

### Resolved Decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| D1 | Capability shape | Generalized format-multiplexing utility plus documented workflow, not per-carrier features | PDF and ZPL compositing share no mechanics; the multiplexer is the only shared abstraction | 2026-09-21 |
| D2 | Format detection | Magic-byte sniff (`%PDF-`, `^XA`) with fallbacks, reusing the DHL Freight Sweden `_label_type` pattern | Precedent exists in-tree and is live-verified against real carrier bytes | 2026-09-21 |
| D3 | ZPL embedding (follow-up scope) | Host-side PNG → 1-bpp → `^Gfa` hex graphic field, Floyd–Steinberg dithering | Universal printer support and deterministic quality; signature strokes survive dithering but not naive thresholding | 2026-09-21 |
| D4 | PDF embedding | PNG → Pillow single-page image PDF → pypdf `merge_transformed_page` with a scale/translate `Transformation` | Zero new SDK dependencies (Q5 → B); reportlab rejected; alpha fidelity is spike Q6 with a white-flatten fallback | 2026-09-21 |
| D5 | Anchor units and keying | Millimetres from top-left of a 1-based page; optional registry key (carrier, `ShippingDocumentCategory` name, format, paper variant) | Neutral units convert cleanly to PDF points (bottom-left flip) and ZPL dots (dpi-scaled); category enum already normalizes document names | 2026-09-21 |
| D6 | Letterhead semantics | Letterhead is an underlay (PDF merge order: content over background); ZPL letterhead is out of practical scope | ZPL has no z-order — insertion before the carrier field stream is structural surgery with no thermal use case | 2026-09-21 |
| D7 | Output contract | Stamped document replaces `ShippingDocument.base64` in place; `format` is unchanged and always matches the input format | The consumer's document list shape is stable; implicit format support means format never leaks into consumer code | 2026-09-21 |
| D8 | Legal responsibility | Karrio composites pixels only; the consumer owns signature validity, authority, and paper-workflow semantics | Extends the PostNord customs verdict: the digital declaration is implicitly signed at EDI level; the printout is deliberately unsigned | 2026-09-21 |
| D9 | Relationship to FedEx ETD (Q1) | Generalized utility alongside existing flows; the FedEx ETD flow is untouched; Path 1 (stamp consumer-generated CI before upload) needs nothing from karrio and Path 2 (stamp carrier-rendered docs post-hoc) is the utility's target | The goal is to mimic the signed, letterheaded document outcome carrier-agnostically, not to modify or replace any carrier's electronic document workflow | 2026-09-21 |
| D10 | Initial format scope (Q2) | PDF is the initial and default target format; ZPL is a nice-to-have follow-up | PDF-only is acceptable as the initial solution; the explicit PostNord `/v3/customs/declaration/pdf` endpoint already covers the PDF-always customs case | 2026-09-21 |
| D11 | Placement governance (Q3) | B — consumer-supplied coordinates are the primary and complete path; karrio-supplied defaults are optional seeds accrued incrementally | The consumer owns post-process stamping, so launch requires no defaults-injection point; seeds land only when measured and verified against live documents | 2026-09-21 |
| D12 | Server exposure (Q4) | SDK-first; API exposure is deferred and will be shaped only if a precedent survey finds similar generalized server solutions | Utilities are foremost SDK; inventing an API surface without precedent adds options-framework and multi-tenancy cost for unproven demand | 2026-09-21 |
| D13 | SDK dependency policy (Q5) | B — no reportlab in the SDK; PDF raster placement uses the Pillow + pypdf transformation merge instead | Keeps the SDK dependency surface unchanged; the weasyprint path remains available to a future server layer if Q7 finds precedent | 2026-09-21 |

### Edge Cases Requiring Input

| Edge Case | Impact | Proposed Handling | Needs Input? |
|-----------|--------|-------------------|--------------|
| Alpha loss in Pillow PDF output (Q6) | Signature overlay may need white-flattening | White-flatten fallback acceptable inside blank signature blocks; letterhead underlay unaffected (content draws over it) | ✅ Yes (spike) |
| PostNord CN22 arrives as ZPL because labels are ZPL | PDF-first launch cannot stamp it | Explicit-declaration PDF endpoint today; ZPL backend as follow-up (D10) | ❌ Resolved (Q2) |
| Carrier re-renders a form and shifts a karrio-supplied seed | Seed anchor lands in the wrong place | Seeds are optional (D11); consumer-supplied placements are unaffected by form drift; seeds carry a revision field | ❌ Resolved (Q3) |

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
    placement=lib.StampPlacement( # consumer-supplied anchor (primary path)
        x=150.0, y=250.0, width=45.0, height=18.0,
    ),
)
# stamped.format == doc.format; stamped.base64 carries the composited bytes
```

The consumer states intent and anchor; the utility sniffs format, composites
via the matching backend (resolving a registry seed only when the consumer
omits the anchor), and returns the document in the same shape and format it
received.

### Problems

1. **Format duplication**: every consumer reimplements PDF and ZPL compositing,
   including two unrelated coordinate systems, two alpha/depth models, and the
   ZPL dpi trap (a 300-dpi assumption on a 203-dpi printer displaces the stamp
   by 50%).
2. **Silent quality failures**: naive thresholding destroys anti-aliased
   signature strokes; un-flattened RGBA overlays white-box over PDF form
   content; both failures look like success.
3. **No shared anchoring convention**: each consumer invents its own coordinate
   conventions; karrio has no normalized placement vocabulary to document
   against, and no place to accrue verified defaults.
4. **No precedent documentation**: consumers cannot see how the workflow
   relates to the established FedEx ETD document flow, which already solves the
   adjacent problem (consumer-generated versus carrier-rendered documents).

---

## Goals & Success Criteria

### Goals

1. One utility entry point that accepts any karrio duty document, a base64
   PNG, and a consumer-supplied anchor, and returns a stamped document of the
   same format.
2. PDF backend at launch with zero new SDK dependencies (Pillow + pypdf only).
3. A placement vocabulary in neutral units, with an optional registry that
   accrues verified karrio-supplied seeds over time (PostNord CN22 as the
   first candidate).
4. A documented consumer workflow, per carrier, enriched by comparison with the
   FedEx ETD precedent.
5. An OpenSpec handoff precise enough that the implementation session starts
   from decisions, not open design.

### Success Criteria

| Metric | Target | Priority |
|--------|--------|----------|
| Consumer format branching | Zero branches in consumer code | Must-have |
| New SDK dependencies | Zero (Pillow and pypdf only) | Must-have |
| PDF text layer | Untouched (no rasterization of carrier content) | Must-have |
| Alpha fidelity or documented fallback | Spike Q6 resolved either way | Must-have |
| ZPL compatibility (follow-up) | Output valid on firmware without `~DY` PNG support | Nice-to-have |
| Registry seed coverage | PostNord CN22 (PDF, A4) verified against live printout | Nice-to-have |
| Printer graphic caching (`~DY`/`^XG`) | Send-once-per-printer path available | Nice-to-have |

### Launch Criteria

**Must-have (P0):**

- [ ] PDF stamp utility passes the test strategy below (SDK scope)
- [ ] Q6 alpha spike resolved with the outcome documented
- [ ] Workflow guide published alongside the SDK guide conventions

**Nice-to-have (P1):**

- [ ] ZPL backend (dither, GRF, splice)
- [ ] PostNord CN22 registry seed
- [ ] `~DY`/`^XG` caching variant
- [ ] Server documents-module integration (gated on Q7 survey, D12)

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| A. Pure consumer-side (karrio untouched) | Available today; zero karrio cost | Every consumer owns the mux, dithering, and anchor conventions | Documented as fallback |
| B. SDK utility layer | Shared, tested, format-multiplexed; serves SDK consumers directly; zero new dependencies via the Pillow + pypdf path | Alpha fidelity depends on spike Q6 | **Selected** (primary) |
| C. Server documents-module pipeline | Zero new server deps (weasyprint present); serves API consumers implicitly | Options-framework plumbing is carrier-scoped; multi-tenant image handling; no precedent established | Deferred (D12, gated on Q7 survey) |
| D. Carrier-native injection | FedEx ETD accepts consumer bytes pre-upload | PostNord has no injection API; solves only the FedEx pre-shipment case | Documented as Path 1 |

### Trade-off Analysis

B is the primary product: a consumer-owned post-process utility keeps karrio's
responsibility boundary at pixel compositing (D8) and needs no defaults-injection
point at launch (D11), which also insulates the utility from carrier form
drift. The Pillow + pypdf transformation merge (D4) removes the only dependency
objection by reusing libraries the SDK already pins; its one open risk —
alpha fidelity — is bounded by the white-flatten fallback, which is
acceptable precisely because anchors target blank signature blocks. A remains
available to any consumer regardless of karrio releases. D is not a utility at
all but a workflow fact: where a carrier accepts consumer-generated documents,
stamping upstream of karrio is always simpler, and the utility targets the
residual carrier-rendered cases.

---

## Technical Design

### Existing Code Analysis

All components below were verified against `develop` on 2026-09-21.

| Component | Location | Reuse Strategy |
|-----------|----------|----------------|
| Document bundling dispatch (`bundle_pdfs`/`bundle_imgs`/`bundle_zpls`/`bundle_base64`) | `modules/sdk/karrio/core/utils/helpers.py:77-130` | Sibling `stamp_*` utilities follow the same dispatch shape |
| `zpl_to_pdf` (Labelary HTTP) | `modules/sdk/karrio/core/utils/helpers.py:134-143` | Not reused (network-dependent); referenced as prior art |
| Magic-byte format sniff | `modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/shipment/create.py:82-113` | `LABEL_MAGICS = ((b"%PDF-", "PDF"), (b"^XA", "ZPL"))` lifted into shared helper with contentType and config fallbacks |
| SDK dependencies (pypdf, Pillow, python-barcode) | `modules/sdk/pyproject.toml:20-33` | Entire PDF backend needs nothing new; ZPL backend likewise (Pillow) |
| `ShippingDocument` / `Documents` models | `modules/sdk/karrio/core/models.py:430-450` | Stamp operates on `ShippingDocument`, replaces `base64`, preserves `format` (D7) |
| `LabelType` enum (PDF, ZPL, PNG) | `modules/sdk/karrio/core/units.py:27-30` | Output format vocabulary |
| `ShippingDocumentCategory` StrEnum with `.map().name_or_key` | `modules/sdk/karrio/core/units.py:153+` | Optional registry document key; PostNord `printoutComposition` kinds must map into it |
| Documents server module (weasyprint, pyzint) | `modules/documents/pyproject.toml:19-20` | Deferred layer C home; HTML overlay → PDF → pypdf merge with no new deps, only if Q7 finds precedent |
| FedEx ETD upload (`/documents/v1/etds/upload`, ETDPreshipment/ETDPostshipment) | `modules/connectors/fedex/karrio/mappers/fedex/proxy.py:89-115`, `providers/fedex/document.py:42-88` | Path 1 workflow precedent; untouched by this change (D9) |
| FedEx ETD options (`doc_files`, `doc_references`, `fedex_electronic_trade_documents`) | `modules/connectors/fedex/karrio/providers/fedex/units.py:332,392-394` | Reference-workflow precedent for registry keying |
| FedEx `UploadDocumentType` vocabulary | `modules/connectors/fedex/karrio/providers/fedex/units.py:502-519` | Document-typing precedent |
| FedEx shipment document parse (INVOICE → `docs.invoice`, rest → `extra_documents`) | `modules/connectors/fedex/karrio/providers/fedex/shipment/create.py:62-107` | Path 2 target surface |
| FedEx ETD attachment and render request (`attachedDocuments`, `requestedDocumentTypes=["COMMERCIAL_INVOICE"]`) | `modules/connectors/fedex/karrio/providers/fedex/shipment/create.py:388-406` | Render-intent precedent |
| PostNord customs printouts (by-id `pdf`/`zpl`, coupled to booking label format) | `modules/connectors/postnord/karrio/mappers/postnord/proxy.py:108-252` | Coupling fact; PDF-first launch relies on the explicit endpoint instead |
| PostNord explicit customs declaration endpoints | `modules/connectors/postnord/karrio/mappers/postnord/proxy.py:309-340` | PDF-always escape hatch (paperSize/rotate params) |
| PostNord `_customs_documents` parse (category from `printoutComposition`, `labelFormat` fallback) | `modules/connectors/postnord/karrio/providers/postnord/shipment/create.py:91-223` | Category mapping input for the optional registry |
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
                      │            │ (launch) │  │ (follow-up)│  │
                      │            │ flatten  │  │ flatten    │  │
                      │            │ Pillow   │  │ dither 1bpp│  │
                      │            │ page +   │  │ GRF hex    │  │
                      │            │ pypdf    │  │ ^FO/^Gfa   │  │
                      │            │ transform│  │ splice     │  │
                      │            │ merge    │  │            │  │
                      │            └──────────┘  └────────────┘  │
                      └───────────────┬──────────────┬───────────┘
                                      ▼              ▼
                       ShippingDocument out: same format,
                       stamped base64 (D7)

  ┌────────────────────────────────────────────────────────────────┐
  │                            consumers                            │
  │                                                                │
  │  SDK consumer ────────── calls lib.stamp_document directly     │
  │  API consumer ────────── deferred pending Q7 precedent survey  │
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
    │  stamp(doc, png, placement)         │                     │
    │────────────────────────────────────>│  seed lookup only   │
    │                                     │  if anchor omitted  │
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
│        (format coupled to booking label format)                  │
│        ──▶ docs.extra_documents (category from composition)      │
│  preferred at launch: explicit /v3/customs/declaration/pdf       │
│        (paperSize param; PDF regardless of label format)         │
│        ──▶ stamp_document ──▶ stamped CN22                       │
└──────────────────────────────────────────────────────────────────┘
```

### PDF Compositing Pipeline (launch scope)

```
  PNG (RGBA)
    │  Pillow: load, auto-trim to ink bounding box
    │  Pillow: save as single-page image PDF (alpha handling = spike Q6)
    ▼
  overlay PDF page (sized to the image)
    │  pypdf: Transformation().scale(s).translate(tx, ty)
    │         derived from mm anchor → points, bottom-left flip
    ▼
  target.merge_transformed_page(overlay, transformation)
    │  letterhead (underlay): merge the content page over the
    │  letterhead page instead — draw order is the z-order
    ▼
  ShippingDocument.base64 replaced, format stays "PDF"
```

### ZPL Conversion Pipeline (follow-up scope)

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

    image: str = None                  # base64-encoded PNG
    placement: StampPlacement = None   # consumer-supplied anchor (primary)
    carrier: str = None                # optional registry seed lookup
    doc_type: str = None               # ShippingDocumentCategory name
    layer: str = "overlay"             # overlay | underlay
```

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image` | string | Yes | base64 PNG; auto-trimmed to ink bounding box before compositing |
| `placement` | object | Primary path | Consumer-supplied anchor; omitted only when a registry seed exists |
| `placement.page` | int | No (default 1) | 1-based page index for multi-page documents |
| `placement.x/y` | float | With placement | Millimetres from page top-left |
| `placement.width/height` | float | No | Draw size; defaults to natural size at native PDF scale or dpi |
| `placement.dpi` | int | ZPL only | Target printer density for dot conversion |
| `carrier` | string | Registry seed path only | Seed key segment; ignored when `placement` is supplied |
| `doc_type` | string | Registry seed path only | `ShippingDocumentCategory`-normalized name, e.g. `cn22`, `commercial_invoice` |
| `layer` | string | No (default overlay) | `overlay` for signatures; `underlay` for letterheads (PDF only, D6) |

### FedEx ETD Precedent: Usage and Expectations by Comparison

The FedEx connector already resolves, for electronic documents, the same
design forces the stamping workflow faces for paper documents. The comparison
below is the documented expectation set this PRD builds on, per D9: the
utility mimics the outcome — signed, letterheaded documents — without
modifying the FedEx flow itself.

| Dimension | FedEx ETD precedent (in-tree today) | Generalized stamping analog |
|-----------|-------------------------------------|------------------------------|
| Document typing | `UploadDocumentType` closed vocabulary: `COMMERCIAL_INVOICE`, `PRO_FORMA_INVOICE`, `CERTIFICATE_OF_ORIGIN`, USMCA variants | `ShippingDocumentCategory` names as optional seed keys; PostNord `printoutComposition` kinds map into the same enum |
| Consumer-generated bytes | `DocumentFile` base64 passes through karrio untouched; karrio retains nothing | Path 1: the stamp happens upstream of karrio; the utility is not involved |
| Upload once, reference thereafter | upload → `doc_id` → `doc_files`/`doc_references` at booking | encode once → printer-stored graphic name → `^XG` recall per print |
| Workflow timing | `ETDPreshipment` vs `ETDPostshipment` | stamp upstream of the carrier vs stamp returned bytes |
| Render intent | `requestedDocumentTypes=["COMMERCIAL_INVOICE"]` asks the carrier to render | Format pinning: request PDF duty documents regardless of label format (PostNord explicit endpoint; D10) |
| Return surface | `shipmentDocuments` routed to `docs.invoice` / `extra_documents` with `format=docType` | Stamped output replaces `base64` in place; `format` unchanged (D7) |
| Responsibility boundary | FedEx owns document validity; karrio transports bytes | Karrio composites pixels; consumer owns legal semantics (D8) |

Expected usage per consumer type follows from the table: an SDK consumer
stamps returned documents directly with a consumer-supplied anchor (Path 2
shape); a consumer generating its own commercial invoice stamps before upload
and lets the existing FedEx ETD reference workflow carry the bytes; an API
consumer waits on the Q7 precedent survey before any server surface exists.

### PostNord Category Mapping Note

`_customs_documents` sets `ShippingDocument.category` from the sorted
`printoutComposition` kinds (e.g. `cn22`), falling back to
`customs_declaration`. Any registry seed lookup must resolve categories
through `ShippingDocumentCategory.map(...).name_or_key` so
printout-composition strings and normalized names converge on one key. If a
composition kind has no enum entry, the implementation session decides between
extending the enum and registering an alias.

---

## Edge Cases & Failure Modes

### Edge Cases

| Scenario | Expected Behavior | Handling |
|----------|-------------------|----------|
| Pillow drops PNG alpha on PDF save (Q6 outcome B) | Signature renders correctly inside blank blocks | White-flatten onto the block background; document the constraint; letterhead underlay unaffected |
| Anti-aliased thin signature strokes at 203 dpi (ZPL follow-up) | Strokes remain continuous | Floyd–Steinberg dithering, never naive threshold (D3) |
| ZPL document with unknown dpi (follow-up) | Stamp placed at correct physical size | `placement.dpi` explicit; refuse dot-coordinate ambiguity rather than guess |
| GRF row length not byte-aligned (follow-up) | Printer renders skewed graphic | Rows padded to byte boundary before hex encoding |
| Multi-page commercial invoice | Signature on page 1 by default | `placement.page`; seeds may pin other pages |
| Carrier PDF with AcroForm fields | Form still fillable after stamping | Transformation merge does not touch form dictionaries |
| PostNord `rotate` variant | Anchor tracks the rotated layout | Paper-variant seed key segment; consumer anchors measured per variant |
| Sniff encounters PNG document | Rejected explicitly | `LabelType.PNG` recognized; stamping PNG-on-PNG out of scope, returns explicit error |
| Registry miss when anchor omitted | No silent fallback to a wrong anchor | Explicit error naming the missing key; consumer supplies `placement` (primary path, D11) |

### Failure Modes

| What Can Go Wrong | Impact | Mitigation |
|-------------------|--------|------------|
| Alpha fidelity worse than white-flatten | Visible halo or occlusion around signatures | Spike Q6 before backend finalization; white-flatten fallback; reportlab re-evaluation documented as the escape hatch |
| Carrier re-renders form; a seed anchor drifts | Seed-stamped documents land wrongly | Seeds optional (D11); revision field per seed; consumer-supplied anchors unaffected |
| Dithering regression (ZPL follow-up) | Broken, unprofessional signature | Snapshot fixtures for stroke continuity at 203 and 300 dpi |
| Oversized image floods printer memory (ZPL follow-up) | Print job fails | Auto-trim plus size ceiling with explicit error |
| Firmware without `~DY` PNG support | Cache variant fails | `^Gfa` is the default path; caching is strictly optional (P1) |
| Stamped document misused legally | Invalid assertion of signature | D8 boundary documented in the utility docstring and workflow guide |

---

## Implementation Plan

All phases Pending; this table primes the OpenSpec `tasks.md`, it does not
execute it.

### Phase 1: SDK core utility (launch scope, PDF)

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Shared magic-byte sniff helper (generalize DHL `LABEL_MAGICS`) | `modules/sdk/karrio/core/utils/helpers.py` | Pending | S |
| Spike Q6: Pillow image-PDF alpha behavior against real CN22 bytes | throwaway script, findings into design | Pending | S |
| PDF backend: Pillow page build + pypdf transformation merge | `modules/sdk/karrio/core/utils/` (new `stamping.py`) | Pending | M |
| `StampPlacement` / `StampRequest` models | `stamping.py` | Pending | S |
| `lib.stamp_document` entry point with dispatch and PNG rejection | `modules/sdk/karrio/lib.py` re-export | Pending | S |

### Phase 2: ZPL backend (P1)

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Flatten, Floyd–Steinberg dither, GRF encode, `^FO/^Gfa` splice | `stamping.py` | Pending | M |
| `~DY`/`^XG` cache variant | `stamping.py` | Pending | S |

### Phase 3: Optional registry seeds (P1)

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Registry structure with category normalization and revision field | `stamping.py` | Pending | S |
| PostNord CN22 (PDF, A4) seed measured from live printout | registry module | Pending | S |
| FedEx commercial invoice (PDF, letter) seed | registry module | Pending | S |

### Phase 4: Server exposure (deferred, gated on Q7)

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Precedent survey: generalized server surfaces over SDK utilities | survey note in `docs/notes/` | Pending | S |
| Documents-module pipeline (weasyprint overlay) only if precedent holds | `modules/documents/karrio/documents/` | Pending | M |

### Phase 5: Documentation

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Workflow guide with FedEx comparison table | `docs/notes/` or guide location per repo convention | Pending | S |
| OpenSpec proposal, design, specs, tasks | `openspec/changes/add-document-stamping/` | Pending | S |

**Dependencies:** Phase 2 and Phase 3 are independent follow-ups to Phase 1;
Phase 4 requires the Q7 survey before any build decision; Phase 5's guide
requires Phase 1 to describe real behavior.

---

## Testing Strategy

### Test Categories

| Category | Location | Coverage Target |
|----------|----------|-----------------|
| Sniff unit tests | `modules/sdk/tests/` | All `LabelType` values plus adversarial bytes |
| PDF merge round-trip | `modules/sdk/tests/` | Page count, AcroForm survival, overlay placement, Q6 alpha outcome |
| GRF encoder golden vectors (ZPL phase) | `modules/sdk/tests/` | Known bitmaps → exact hex, padded rows |
| Dither snapshot tests (ZPL phase) | `modules/sdk/tests/` | Stroke continuity fixtures at 203/300 dpi |
| Registry resolution (seed phase) | `modules/sdk/tests/` | Key hits, misses, category normalization |
| Connector fixtures | `modules/connectors/postnord/tests/`, `modules/connectors/fedex/tests/` | Real carrier document bytes |

### Fixture vendoring policy

Real carrier documents used as test fixtures must be human-verified free of address and other personal data before being vendored.
The vendored `postnord_cn22.pdf` is a customs-declaration-only print with no label section and no address data, carrying only a dummy Swedish org number.

### Test Cases

```python
class TestStampDocument(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_stamp_pdf_preserves_format_and_pages(self):
        """Stamping a PDF CN22 keeps format, page count, and form fields."""
        stamped = lib.stamp_document(
            CN22_PDF_DOC,
            image=SIGNATURE,
            placement=lib.StampPlacement(x=150.0, y=250.0, width=45.0, height=18.0),
        )

        self.assertEqual(stamped.format, "PDF")
        self.assertEqual(page_count(stamped.base64), page_count(CN22_PDF_DOC.base64))

    def test_stamp_rejects_png_document(self):
        """PNG documents fail explicitly rather than silently passing through."""
        with self.assertRaises(ValueError):
            lib.stamp_document(PNG_DOC, image=SIGNATURE, placement=PLACEMENT)
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
| Pillow PDF alpha fidelity inadequate (Q6) | Medium | Medium | White-flatten fallback for blank signature blocks; reportlab re-evaluation documented as escape hatch |
| pypdf transformation merge interacts badly with a carrier's page geometry | Medium | Low | Round-trip tests over real PostNord and FedEx fixtures before finalization |
| Anchor drift on karrio-supplied seeds | Medium | Medium | Seeds optional (D11); revision field; consumer-supplied anchors unaffected |
| ZPL firmware variance (follow-up) | Medium | Low | `^Gfa` baseline targets all printers; caching optional |
| Legal misuse of stamped signatures | High | Low | D8 boundary in docs; utility asserts nothing about validity |
| Scope creep into document storage/verification or premature API surface | Medium | Medium | Out-of-scope table; Phase 4 gated on Q7 survey |

---

## Migration & Rollback

### Backward Compatibility

- **API compatibility**: no existing endpoint, serializer, or document payload
  changes; stamping is additive and opt-in.
- **Data compatibility**: no schema or migration impact; stamped documents are
  ordinary `ShippingDocument` values in flight.
- **Feature flags**: unnecessary; consumers invoke the utility explicitly.

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
path (all citations in Existing Code Analysis). Decisions D9-D13 resolve the
five product questions raised by that exploration, answered by the owner on
2026-09-21. The PostNord legal framing in D8 extends the archived change
`openspec/changes/archive/2026-09-21-postnord-customs-declaration/` and its
guide `docs/notes/postnord/customs-declaration-sdk-guide.md`.

### Appendix B: PDF and ZPL Technical Reference

- pypdf `Transformation` and `merge_transformed_page`: scale and translate an
  overlay page onto a target page in one merge; available in the pinned
  pypdf across its modern releases; the SDK already depends on it.
- Pillow PDF output: a single-page PDF whose MediaBox matches the image;
  whether RGBA alpha survives as an SMask is spike Q6 — white-flatten is the
  fallback and letterhead underlay is unaffected either way.
- `^FO x,y ^Gfa,total,rowbytes,rows,<hex>`: hex graphic field; universal
  Zebra support; `rowbytes` reflects byte-padded rows.
- `~DY` / `^XG`: printer-flash graphic storage and recall; requires
  Link-OS-era firmware; used only by the optional cache variant.
- Origins and units: ZPL is top-left in dots at printer density
  (203/300/600 dpi); PDF is bottom-left in points (1 pt = 1/72 in);
  placements are millimetres and convert per backend.

### Appendix C: Carrier-Specific Reference

| Carrier | Surface | Notes |
|---------|---------|-------|
| PostNord | `POST /rest/shipment/v3/labels/ids/{pdf,zpl}?definePrintout=onlyCustomsDeclarations` | Implicit booking-time fetch; format coupled to label format |
| PostNord | `POST /rest/shipment/v3/customs/declaration/pdf` | Explicit; `paperSize`, `rotate`, alignment params; PDF always — the launch-path source for stampable CN22s |
| FedEx | `POST /documents/v1/etds/upload` | `ETDPreshipment` / `ETDPostshipment` workflows; returns doc ids |
| FedEx | shipment create `attachedDocuments`, `requestedDocumentTypes` | Consumer-doc reference and carrier-render intent |

### Appendix D: Handoff to OpenSpec

Proposed change name: `add-document-stamping`.
Proposed capability path: `openspec/specs/documents/stamping/spec.md` —
deviating from the observed `<carrier>/<capability>` convention because the
capability is carrier-agnostic; carrier specificity lives in optional seeds,
not in the spec. The proposal session should:

1. Run the Q6 alpha spike first — it is the only technical unknown in the
   launch scope and decides the PDF backend's flattening behavior.
2. Scope Phase 1 (PDF, consumer-supplied placement) as the SHALL-level core;
   ZPL and seeds are P1 deltas in `tasks.md`, not spec blockers.
3. Record the Q7 precedent survey as a research task before any server
   surface is proposed; absent precedent, the spec stays SDK-scoped.
4. Carry this PRD as the decision record; `design.md` owns the final model
   shapes and the Q6/Q7 outcomes, `specs/documents/stamping/spec.md` owns the
   SHALL-level behavior (format preservation, explicit PNG rejection,
   registry-miss errors, placement precedence), and `tasks.md` derives from
   the Implementation Plan above.
