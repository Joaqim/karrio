# PostNord CN22 stamping

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-09-28 |
| Status | In Progress |
| Owner | Joaqim Planstedt |
| Type | Enhancement |
| Reference | [AGENTS.md](../AGENTS.md); [DOCUMENT_STAMPING.md](./DOCUMENT_STAMPING.md); fork readers: the openspec change `stamp-embedded-customs-forms` on the `docs-openspec` branch |

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
12. [Known Limits](#known-limits)

---

## Executive Summary

The PostNord connector declares stamp seeds for its CN22 customs declaration and the section markers that let the SDK classifier tell a lone CN22 from PostNord's composed label + CN22 printout.
PostNord's booking endpoint composes the international letter label and the CN22 into one printout in both formats: a single ZPL format (one `^XZ`) and a single A4 PDF page.
This PRD covers the connector-side data only: `document_sections`, the lone `cn22` seeds, the combined `label_cn22` seeds, and the live fixtures that pin them.

### Key Architecture Decisions

1. **Sections are declarative plugin data**: PostNord's markers live in `providers/postnord/stamping.py` beside the seeds and reach the SDK through `PluginMetadata.document_sections`, so the SDK classifier stays carrier-agnostic.
2. **ZPL markers are PostNord's own field comments**: `^FX CUSTOMS_CN22_ROTATED^FS` and `^FX SE_INTERNATIONAL_LETTER_LABEL^FS` name the sections; `^XZ` count and barcode presence cannot separate the forms.
3. **PDF markers are page text unique to each section**: `CUSTOMS DECLARATION` + `CN22` for the declaration, `Brev utrikes` + `Parcel ID` for the label.
4. **The combined form gets its own `label_cn22` seeds**: ZPL reuses the CN22 keyword anchor; PDF carries a placement measured on the combined page at revision 1, even though it currently equals the lone seed's region, so the two forms can diverge without disturbing `cn22`.
5. **Lone `cn22` seeds are unchanged**: revision 3 and its resolution stay as shipped.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| `DOCUMENT_SECTIONS` for ZPL and PDF, wired into the plugin metadata | The SDK classifier and stamping engine (`feat-document-stamping`) |
| `label_cn22/ZPL/*` and `label_cn22/PDF/A4` seeds | Booking-time composition verification (follow-on, `feat-postnord-customs-invoice`) |
| Live combined fixtures and their integrity tests | Opt-in standalone customs documents (follow-on, `feat-postnord-customs-invoice`) |
| Retaining the lone `cn22/ZPL/*` and `cn22/PDF/A4` seeds | CN23 and customs-invoice parcel products |

---

## Open Questions & Decisions

### Resolved Decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| D1 | PDF label markers | `("Brev utrikes", "Parcel ID")` | Both occur only in the label section of the combined capture and never on the customs-only page; they mirror the letter-specific ZPL label comment | 2026-09-28 |
| D2 | Lone PDF fixture | Reuse `postnord_cn22.pdf` | The customs-only by-id capture (`probe2b`) is byte-identical to the vendored fixture | 2026-09-28 |
| D3 | Separate PDF seed for the combined page | `label_cn22/PDF/A4`, revision 1 | The measurement matches the lone region today, but a distinct key lets the forms diverge later | 2026-09-28 |
| D4 | PDF stamp page | Taken from the seed placement (page 1), with a caller page override as an SDK dependency | Classification names page 1 for both captures; the page override is SDK work (`feat-document-stamping`, change task 1.6) | 2026-09-28 |

---

## Problem Statement

### Current State

The connector registers only `cn22/PDF/A4` and `cn22/ZPL/*`, so stamping presumes a caller already knows the document is a lone CN22.
PostNord's default booking printout is the composed label + CN22, and nothing on the connector declared how to recognize it.

```python
# before: the consumer must know the composition and the type
lib.stamp_document(document, image=signature, carrier="postnord", doc_type="cn22")
```

### Desired State

```python
result = lib.classify_customs_composition(document, carrier="postnord")
if result.doc_type:  # "cn22" or "label_cn22"
    document = lib.stamp_document(
        document, image=signature, carrier="postnord", doc_type=result.doc_type
    )
```

### Problems

| Problem | Impact |
|---------|--------|
| No declared sections | The classifier returns `none` for every PostNord document |
| No combined seeds | A composed printout has no registry key to stamp under |
| No combined fixtures | Nothing pins the live composed layout the seeds rely on |

---

## Goals & Success Criteria

### Goals

1. Classify every live PostNord capture correctly in both formats.
2. Stamp the combined printout at the lone CN22's signature strip without touching the label section.
3. Leave the lone CN22 seeds and their tests unchanged in behavior.

### Success Criteria

| Metric | Target |
|--------|--------|
| Combined ZPL and PDF captures | `label_with_declaration`, `label_cn22`, PDF page 1 |
| Lone ZPL and PDF | `declaration`, `cn22`, PDF page 1 |
| Combined ZPL stamp | Same `^GFA` field as the lone CN22; carrier bytes before `^XZ` unchanged |
| Combined PDF stamp | Within the measured strip on page 1; page count and text unchanged |
| `cn22/*` seeds | Revision 3, unchanged resolution |

---

## Alternatives Considered

| Alternative | Pros | Cons | Decision |
|-------------|------|------|----------|
| Let `cn22` seeds serve combined documents | No new keys | The consumer cannot tell the forms apart; forms cannot diverge | Rejected |
| `^XZ` count or barcode detection for ZPL | No carrier data | Combined and lone ZPL both have one `^XZ`; barcodes are no carrier contract | Rejected |
| Page count for PDF | Trivial | Both combined and lone PDFs are one A4 page | Rejected |
| `Parcel ID` alone as the PDF label marker | Service-agnostic | Diverges from the letter-specific ZPL marker, so formats could classify one service differently | Rejected for now (see Known Limits) |

---

## Technical Design

### Existing Code Analysis

| Component | Location | Reuse |
|-----------|----------|-------|
| Lone CN22 seed (revision 3) | `modules/connectors/postnord/karrio/providers/postnord/stamping.py` (`CN22_SEED`) | Keyword and ZPL offset reused by `label_cn22` |
| Seed and section lookup | `modules/sdk/karrio/core/utils/stamping.py` (`_carrier_seeds`, `_carrier_sections`) | Reads `stamp_seeds` and `document_sections` from plugin metadata |
| Classifier | `stamping.classify_customs_composition`, exported through `karrio.lib` | Consumes `DOCUMENT_SECTIONS`; a kind is present when all its markers match, whitespace collapsed |
| Plugin metadata field | `modules/sdk/karrio/core/metadata.py` (`document_sections`) | Shape `{FORMAT: {kind: markers}}` |
| Lone fixtures | `tests/postnord/fixtures/postnord_cn22.zpl`, `postnord_cn22.pdf` | Lone classification and seed tests |
| Combined fixtures | `postnord_label_cn22_booking.zpl`, `postnord_label_cn22_printid.zpl`, `postnord_label_cn22_printid.pdf` | Live export-letter (UX) captures: booking ZPL, by-id ZPL and PDF without `definePrintout` |
| CN22 measurement | Appendix B of `KEYWORD_ANCHORED_STAMPING.md` (keyword-anchored stamping change) | Label-dot strip and landmarks reused for the combined page |

### Architecture Overview

```
 +---------------------------- PostNord plugin -----------------------------+
 | providers/postnord/stamping.py                                           |
 |                                                                          |
 |  DOCUMENT_SECTIONS                       STAMP_SEEDS                     |
 |   ZPL cn22  ^FX CUSTOMS_CN22_ROTATED^FS   cn22/PDF/A4       CN22_SEED    |
 |       label ^FX SE_INTERNATIONAL_...^FS   cn22/ZPL/*        CN22_SEED    |
 |   PDF cn22  CUSTOMS DECLARATION + CN22    label_cn22/PDF/A4 LABEL_CN22_  |
 |       label Brev utrikes + Parcel ID      label_cn22/ZPL/*  SEED (rev 1) |
 +------------------+----------------------------------+--------------------+
                    | plugins/postnord/__init__.py      |
                    | PluginMetadata(document_sections, | stamp_seeds)
                    v                                   v
 +------------------ SDK (feat-document-stamping) -------------------------+
 | classify_customs_composition(doc, carrier="postnord")                    |
 |   -> composition, kinds, doc_type (cn22 | label_cn22), PDF page          |
 | stamp_document(doc, carrier="postnord", doc_type=...)                    |
 |   ZPL: seed keyword "Date and Sender's signature" -> ^FO7,303            |
 |   PDF: seed placement on page (seed page 1; page override: SDK task 1.6) |
 +--------------------------------------------------------------------------+
```

### Combined printout layout

```
 ZPL (one ^XA ... ^XZ)                    PDF (one A4 page, one /Form1)
 +------------------------------+          +---------------------------+
 | ^FX CUSTOMS_CN22_ROTATED^FS  |          | CN22 box (label y 15-695) |
 |  CN22 section, keyword once  |          |  "CUSTOMS DECLARATION"    |
 |  ^FO20,35 Date and Sender's  |          |  "CN22", signature strip  |
 |           signature          |          |  (label x 6.63-67.53,     |
 +------------------------------+          |   y 302.97-695.44 dots)   |
 | ^FX SE_INTERNATIONAL_LETTER_ |          +------ bottom rule y 695 --+
 |     LABEL^FS                 |          | letter label (y >= 711)   |
 |  label section, ^GFA logos,  |          |  "Brev utrikes"           |
 |  ^BCR barcode                |          |  "Parcel ID" + barcode    |
 +-- stamp ^GFA spliced here ---+          +---------------------------+
 ^XZ
```

### Section markers and uniqueness evidence

| Format | Kind | Markers | Evidence |
|--------|------|---------|----------|
| ZPL | `cn22` | `^FX CUSTOMS_CN22_ROTATED^FS` | Once in the lone fixture and in both combined captures, before the label marker |
| ZPL | `label` | `^FX SE_INTERNATIONAL_LETTER_LABEL^FS` | Once in both combined captures; absent from the lone fixture and from the CN22 section |
| PDF | `cn22` | `CUSTOMS DECLARATION`, `CN22` | Extracted as `CUSTOMS \nDECLARATIONCN22`, matched after whitespace collapse on both pages |
| PDF | `label` | `Brev utrikes`, `Parcel ID` | Present on the combined page, absent from the customs-only page; every run lies below the CN22 box's bottom rule |

### Seeds

| Key | Seed | Anchor | Revision |
|-----|------|--------|----------|
| `cn22/PDF/A4` | `CN22_SEED` | x 53.34, y 91.44 mm, 49.11 x 7.62 mm, rotation 90 | 3 (unchanged) |
| `cn22/ZPL/*` | `CN22_SEED` | keyword, offset (-1.673, 33.529) mm at 203 dpi | 3 (unchanged) |
| `label_cn22/ZPL/*` | `LABEL_CN22_SEED` | same keyword and offset as `cn22` | 1 |
| `label_cn22/PDF/A4` | `LABEL_CN22_SEED` | x 53.34, y 91.44 mm, 49.11 x 7.62 mm, rotation 90, page 1 | 1 |

### PDF measurement on the combined page

The combined page (`postnord_label_cn22_printid.pdf`) was measured with pypdf.
The page draws the whole printout as one `/Form1` XObject, placed by a pure translation to (148.84964, 151.74292) pt, with `BBox` 297.57635 x 538.40393 pt, the 839 x 1518-dot label frame at 203 dpi.
The keyword text matrix sits at form (8.867, 525.9902) pt, which is label (25.00, 35.00) dots, and the CN22 box's outer bottom rule at form y 291.9015 pt, label y 695.0 dots.
These are the landmarks of the lone CN22 form against which the signature strip (label x 6.63-67.53, y 302.97-695.44 dots) was measured, so on the combined page the strip spans page x 53.34-60.96 mm and y 91.44-140.55 mm.
The first 415 content-stream operations of `/Form1`, the whole CN22 section, are identical to the customs-only page's, so the combined region equals the lone seed's region; the seed is still registered separately.

---

## Edge Cases & Failure Modes

| Scenario | Behavior |
|----------|----------|
| ZPL label without the CN22 section | `none`, no `doc_type` |
| PDF yielding no marker text | `none`, not an error |
| CN22 keyword occurring zero or several times | Keyword resolution raises, as for `cn22` |
| Paper other than A4 | No `label_cn22/PDF/*` seed resolves; the A4 seed does not leak to LETTER |
| PostNord renames a field comment or label wording | Classification degrades to `none` or `declaration`; one constant to update |

---

## Implementation Plan

| Task | Commit | Files |
|------|--------|-------|
| 2.1 | `test(postnord): add live combined label and cn22 fixtures` | `tests/postnord/fixtures/postnord_label_cn22_*`, `tests/postnord/test_label_cn22_stamping.py` |
| 2.2 | `feat(postnord): declare customs document sections` | `karrio/providers/postnord/stamping.py`, `karrio/plugins/postnord/__init__.py`, test file |
| 2.3 | `feat(postnord): register label_cn22 zpl stamp seed` | `stamping.py`, test file, `test_cn22_stamping.py` (seed key set) |
| 2.4 | `feat(postnord): register measured label_cn22 pdf stamp seed` | `stamping.py`, test file, `test_cn22_stamping.py` (seed key set) |

Paths are relative to `modules/connectors/postnord/`.

Dependencies: `feat-document-stamping` provides the classifier, `document_sections`, and (task 1.6) the page override for seeded PDF stamps.
Follow-on on `feat-postnord-customs-invoice`: booking-time verification of the returned label with the classifier (a warning on unexpected composition) and opt-in standalone customs documents.

---

## Testing Strategy

`modules/connectors/postnord/tests/postnord/test_label_cn22_stamping.py`, unittest, no network.

| Class | Covers |
|-------|--------|
| `TestPostnordCombinedFixtures` | Each capture's structure: one `^XZ`, markers once and ordered, keyword once; one A4 page; marker text present or absent |
| `TestPostnordDocumentSections` | Metadata publishes `DOCUMENT_SECTIONS`; classification of all five fixtures and a label-only ZPL |
| `TestLabelCn22ZplStamp` | Seed reuses the CN22 anchor; both combined ZPLs yield the lone CN22's `^GFA` field; carrier bytes before `^XZ` unchanged |
| `TestLabelCn22PdfMeasurement` | The combined page's frame placement and landmarks match the measurement constants; the box rule separates the sections |
| `TestLabelCn22PdfStamp` | Seed resolves to the region derived from the measurement, never from the seed; revision 1; no LETTER leak; classify-then-stamp lands within the strip on page 1 above the label section, page count and text unchanged |

The pre-existing `test_cn22_stamping.py` behavior tests are unchanged; only the seed key-set assertion lists the new keys.

```bash
python -m unittest discover -v -f modules/connectors/postnord/tests
python -m unittest discover -v -f modules/sdk/tests
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Captures are by-id (and one booking) UX printouts, not every service | Medium | Medium | Live captures per change task 5.1 |
| PostNord changes layout | Low | Medium | Fixture-integrity tests fail first; re-measure with a revision bump |
| Combined and lone PDF regions diverge | Low | Low | Separate `label_cn22` seed |

---

## Migration & Rollback

Additive data only: new sections, new seed keys, new fixtures.
Rollback is reverting the commits; the `cn22` seeds and consumers stamping under `cn22` are unaffected.

---

## Known Limits

The label markers `Brev utrikes` (PDF) and `SE_INTERNATIONAL_LETTER_LABEL` (ZPL) are letter-specific, taken from export letter (UX) captures.
Service 91 is uncaptured; if its label prints other wording or another field comment, its composed printout would classify as a lone `cn22` in both formats.
This is revisited after the live booking captures of change tasks 5.1 and 5.2.
