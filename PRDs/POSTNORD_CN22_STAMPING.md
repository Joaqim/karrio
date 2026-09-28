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
13. [Appendices](#appendices)

---

## Executive Summary

The PostNord connector declares stamp seeds for its CN22 customs declaration and the section markers that let the SDK classifier tell a lone CN22 from PostNord's composed label + CN22 printout.
PostNord's booking endpoint composes the international letter label and the CN22 into one printout in both formats: a single ZPL format (one `^XZ`), and in PDF either a single A4 page with the CN22 turned beside the label or, in the sandbox booking capture, two A4 pages with the label on page 1 and an upright CN22 on page 2.
For International Parcel (service 91) it composes the parcel label and an upright CN22 as two ZPL formats (label first), and in PDF as two A4 pages (label first).
This PRD covers the connector-side data only: `document_sections`, the lone `cn22` seeds, the combined `label_cn22` seeds, and the live fixtures that pin them.

### Key Architecture Decisions

1. **Sections are declarative plugin data**: PostNord's markers live in `providers/postnord/stamping.py` beside the seeds and reach the SDK through `PluginMetadata.document_sections`, so the SDK classifier stays carrier-agnostic.
2. **ZPL markers are PostNord's own field comments**: `lib.AnyOf` of `^FX CUSTOMS_CN22_ROTATED^FS` and `^FX CUSTOMS_CN22_V2^FS` for the declaration, and of `^FX SE_INTERNATIONAL_LETTER_LABEL^FS` and `^FX NORDIC_SHIPPING_LABEL^FS` for the label; `^XZ` count and barcode presence cannot separate the forms.
3. **PDF markers are page text unique to each section**: `CUSTOMS DECLARATION` + `CN22` for the declaration; for the label the letter template (`Brev utrikes` + `Parcel ID`), the tracked letter template (`PostNord Tracked Letter` + `Item-ID`) or the International Parcel template (`International Parcel` + `Item-ID`), declared with `lib.AnyOf`.
4. **The combined form gets its own `label_cn22` seeds**: both formats anchor on the CN22 keyword in its reading frame (revision 3), so one seed serves the rotated and upright layouts in ZPL and in PDF without disturbing `cn22`.
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
| D3 | Separate PDF seed for the combined page | `label_cn22/PDF/A4`, revision 1 | The measurement matches the lone region today, but a distinct key lets the forms diverge later; its PDF anchor is superseded by D6 | 2026-09-28 |
| D4 | PDF stamp page | The classified page, passed to `stamp_document(page=...)` | Page 1 for the single-page captures, page 2 for the two-page booking capture | 2026-09-28 |
| D5 | Tracked letter label markers | `lib.AnyOf(("Brev utrikes", "Parcel ID"), ("PostNord Tracked Letter", "Item-ID"))` | The two-page capture's label carries neither `Brev utrikes` nor `Parcel ID`; `PostNord Tracked Letter` and `Item-ID` occur on its label page and on no CN22 page of any PDF fixture; `DELIVERY CONFIRMATION` names an add-on service and is not used | 2026-09-28 |
| D6 | One keyword geometry for both PDF layouts | `pdf_keyword_placement` x 33.53, y -5.32, 49.11 x 7.62 mm, rotation 0, revision 2 | Edge-aligned on the single-page layout's measured strip; inside the upright layout's free signature area though not on its rules (owner, option 1); a per-layout seed would need a layout discriminator per template | 2026-09-28 |
| D7 | International Parcel (91) markers | ZPL `AnyOf` alternatives `^FX CUSTOMS_CN22_V2^FS` and `^FX NORDIC_SHIPPING_LABEL^FS`; PDF label alternative `("International Parcel", "Item-ID")` | Each occurs once in its own section of the 91 captures and in no CN22 section of any fixture | 2026-09-28 |
| D8 | One ZPL keyword geometry for both ZPL layouts | `zpl_keyword_frame_placement` x 33.529, y -3.4245, 49.1 x 7.6 mm, rotation 0, 203 dpi, revision 3 | The rotated letter CN22 keeps `^FO7,303`; the upright V2 CN22 resolves to `^FO293,758` inside its signature area; the label-axis offset of revision 2 placed the V2 stamp beyond `^LL840` | 2026-09-28 |
| D9 | Lone `cn22/ZPL/*` geometry | Unchanged label-axis offset | A reading-frame geometry is byte-identical for the seed keyword on the lone fixture but not for a consumer keyword resolved with the seed's geometry (`Total Weight (in kg)`), so the lone seed stays as shipped | 2026-09-28 |

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
| Combined ZPL and PDF captures | `label_with_declaration`, `label_cn22`, PDF page 1 (single page) or 2 (two-page booking, International Parcel) |
| Lone ZPL and PDF | `declaration`, `cn22`, PDF page 1 |
| Combined ZPL stamp | Letter: same `^GFA` field as the lone CN22, carrier bytes before `^XZ` unchanged; International Parcel: inserted into the CN22 format within its measured signature area, label format byte-identical |
| Combined PDF stamp | On the classified page only, oriented along the keyword, within the measured strip (single page) or free signature area (two-page); page count and text unchanged |
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
| Classifier | `stamping.classify_customs_composition`, exported through `karrio.lib` | Consumes `DOCUMENT_SECTIONS`; a kind is present when all markers of one of its sets match (`lib.AnyOf` for alternatives), whitespace collapsed |
| PDF keyword anchoring | `StampSeed.pdf_keyword_placement` in the SDK stamping module | Locates the keyword's text run on the classified page and lays the geometry out in its reading frame |
| ZPL reading-frame anchoring | `StampSeed.zpl_keyword_frame_placement` in the SDK stamping module | Lays the geometry out from where the keyword field's text starts, along its orientation, and splices the stamp into the format containing the field |
| Plugin metadata field | `modules/sdk/karrio/core/metadata.py` (`document_sections`) | Shape `{FORMAT: {kind: markers}}` |
| Lone fixtures | `tests/postnord/fixtures/postnord_cn22.zpl`, `postnord_cn22.pdf` | Lone classification and seed tests |
| Combined fixtures | `postnord_label_cn22_booking.zpl`, `postnord_label_cn22_printid.zpl`, `postnord_label_cn22_printid.pdf`, `postnord_label_cn22_booking_two_pages.pdf` | Export-letter (UX) captures: live booking ZPL, live by-id ZPL and PDF without `definePrintout`, sandbox booking PDF (two pages, test sender data only) |
| International Parcel fixtures | `postnord_label_cn22_international_parcel.zpl`, `postnord_label_cn22_international_parcel.pdf` | Live service 91 bookings of 2026-09-28 (test recipient data): two ZPL formats, two A4 PDF pages |
| CN22 measurement | [Appendix A](#appendix-a-cn22-measurement-derivation) | Label-dot strip and landmarks reused for the combined page |

### Architecture Overview

```
 +---------------------------- PostNord plugin -----------------------------+
 | providers/postnord/stamping.py                                           |
 |                                                                          |
 |  DOCUMENT_SECTIONS                       STAMP_SEEDS                     |
 |   ZPL cn22  AnyOf(CUSTOMS_CN22_ROTATED,   cn22/PDF/A4       CN22_SEED    |
 |               CUSTOMS_CN22_V2)            cn22/ZPL/*        CN22_SEED    |
 |       label AnyOf(SE_INTERNATIONAL_       label_cn22/PDF/A4 LABEL_CN22_  |
 |               LETTER_LABEL, NORDIC_       label_cn22/ZPL/*  SEED (rev 3) |
 |               SHIPPING_LABEL)                                            |
 |   PDF cn22  CUSTOMS DECLARATION + CN22                                   |
 |       label AnyOf(Brev utrikes + Parcel                                  |
 |         ID, PostNord Tracked Letter +                                    |
 |         Item-ID, International Parcel +                                  |
 |         Item-ID)                                                         |
 +------------------+----------------------------------+--------------------+
                    | plugins/postnord/__init__.py      |
                    | PluginMetadata(document_sections, | stamp_seeds)
                    v                                   v
 +------------------ SDK (feat-document-stamping) -------------------------+
 | classify_customs_composition(doc, carrier="postnord")                    |
 |   -> composition, kinds, doc_type (cn22 | label_cn22), PDF page          |
 | stamp_document(doc, carrier="postnord", doc_type=..., page=...)          |
 |   ZPL cn22: keyword "Date and Sender's signature" -> ^FO7,303            |
 |   ZPL label_cn22: keyword in its reading frame, in its own format        |
 |     rotated letter CN22 -> ^FO7,303; upright V2 CN22 -> ^FO293,758       |
 |   PDF cn22: seed placement; label_cn22: keyword run on the page          |
 +--------------------------------------------------------------------------+
```

### Combined printout layout

```
 ZPL (one ^XA ... ^XZ)                    PDF single-page layout (/Form1)
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

 International Parcel ZPL (two formats)
 +------------------------------+          +------------------------------+
 | ^FX NORDIC_SHIPPING_LABEL^FS |          | ^LL840 ^FWN                  |
 |  parcel label, ^BCN barcodes |          | ^FX CUSTOMS_CN22_V2^FS       |
 |  "International Parcel"      |          |  box ^FO10,15 ^GB820,820     |
 |                              |          |  certification ink to y 745  |
 |                              |          |  ^FO25,785 keyword (ink      |
 |                              |          |   x 26-229)  [stamp 293-684, |
 |                              |          |   y 758-818]                 |
 |                              |          |  bottom rule y 834           |
 +------------------------------+          +-- stamp ^GFA spliced here ---+
 ^XZ (byte-identical)                      ^XZ
```

### Section markers and uniqueness evidence

| Format | Kind | Markers (`lib.AnyOf` alternatives) | Evidence |
|--------|------|------------------------------------|----------|
| ZPL | `cn22` | `^FX CUSTOMS_CN22_ROTATED^FS` | Once in the lone fixture and in both combined letter captures, before the label marker |
| ZPL | `cn22` | `^FX CUSTOMS_CN22_V2^FS` | Once in the International Parcel capture, in its second format; in no label section of any ZPL fixture |
| ZPL | `label` | `^FX SE_INTERNATIONAL_LETTER_LABEL^FS` | Once in both combined letter captures; absent from the lone fixture and from the CN22 section |
| ZPL | `label` | `^FX NORDIC_SHIPPING_LABEL^FS` | Once in the International Parcel capture, in its first format; in no CN22 section of any ZPL fixture |
| PDF | `cn22` | `CUSTOMS DECLARATION`, `CN22` | Extracted as `CUSTOMS \nDECLARATIONCN22`, matched after whitespace collapse on every CN22 page |
| PDF | `label` | `Brev utrikes`, `Parcel ID` | Present on the combined page, absent from the customs-only page; every run lies below the CN22 box's bottom rule |
| PDF | `label` | `PostNord Tracked Letter`, `Item-ID` | Present on page 1 of the two-page capture (3 and 1 times); absent from every CN22 page of all four PDF fixtures |
| PDF | `label` | `International Parcel`, `Item-ID` | Present on page 1 of the International Parcel PDF (`Shipment Item-ID`); absent from all four CN22 pages of the four PDF fixtures |

### Seeds

| Key | Seed | Anchor | Revision |
|-----|------|--------|----------|
| `cn22/PDF/A4` | `CN22_SEED` | x 53.34, y 91.44 mm, 49.11 x 7.62 mm, rotation 90 | 3 (unchanged) |
| `cn22/ZPL/*` | `CN22_SEED` | keyword, offset (-1.673, 33.529) mm at 203 dpi | 3 (unchanged) |
| `label_cn22/ZPL/*` | `LABEL_CN22_SEED` | keyword, reading-frame offset (33.529, -3.4245) mm from the text start on its glyph-top edge, 49.1 x 7.6 mm, rotation 0 relative to the text, 203 dpi, in the keyword's format | 3 |
| `label_cn22/PDF/A4` | `LABEL_CN22_SEED` | keyword, reading-frame offset (33.53, -5.32) mm, 49.11 x 7.62 mm, rotation 0 relative to the text, on the classified page | 3 |

The seed keeps the single-page coordinates (x 53.34, y 91.44 mm, rotation 90) as its `placement`, but a PDF stamp without an explicit placement resolves by the keyword.
Revision 1 was coordinate-only and would have stamped the two-page capture's CN22 across its explanation, contents and tariff rows.
Revision 2 carried the lone CN22's label-axis ZPL offset, which on the upright V2 CN22 resolved beyond the format's `^LL840`; revision 3 replaces it with the reading-frame geometry, which resolves to the same `^FO7,303` field on the rotated letter CN22.

### PDF measurement on the combined page

The combined page (`postnord_label_cn22_printid.pdf`) was measured with pypdf.
The page draws the whole printout as one `/Form1` XObject, placed by a pure translation to (148.84964, 151.74292) pt, with `BBox` 297.57635 x 538.40393 pt, the 839 x 1518-dot label frame at 203 dpi.
The keyword text matrix sits at form (8.867, 525.9902) pt, which is label (25.00, 35.00) dots, and the CN22 box's outer bottom rule at form y 291.9015 pt, label y 695.0 dots.
These are the landmarks of the lone CN22 form against which the signature strip (label x 6.63-67.53, y 302.97-695.44 dots) was measured, so on the combined page the strip spans page x 53.34-60.96 mm and y 91.44-140.55 mm.
The first 415 content-stream operations of `/Form1`, the whole CN22 section, are identical to the customs-only page's, so the combined region equals the lone seed's region; the seed is still registered separately.

### PDF measurement on the two-page capture

Page 2 of `postnord_label_cn22_booking_two_pages.pdf` was measured the same way, with pypdf and a 300 dpi pdftoppm render for ink extents.
The page draws the upright CN22 as `/Form2`, placed by a pure translation to (148.84964, 187.21091) pt, with `BBox` 297.57635 x 467.468 pt, an 839 x 1318-dot label frame.
The keyword text matrix sits at form (8.867, 184.4335) pt, label (25, 798) dots, page (55.64, 165.89) mm, upright at 6.38 pt; on the single-page capture it sits at page (55.64, 57.91) mm, turned 90 degrees clockwise at 7.09 pt.
The CN22 box spans label x 10-830 and y 15-835 dots; its inner rules are at form x 3.9015 and 294.0296 pt and y 171.665 pt.

In the keyword's reading frame (mm along the text from the run origin; across, positive below the baseline) the two layouts measure:

| Landmark | Single page (turned) | Two-page, page 2 (upright) |
|----------|----------------------|----------------------------|
| Keyword ink ends | along 33.02 | along 29.79 |
| Box right rule | along 82.3-82.6 | along 100.57-100.72 |
| Box bottom rule | across +1.88 | across +4.51 inner, +4.63 outer |
| Nearest certification ink | across -4.98 | across -6.46 (last baseline -6.88) |
| 49.11 x 7.62 mm strip on the right and bottom rules | along 33.53-82.64, across -5.32 to +2.30 | along 51.61-100.72, across -2.99 to +4.63 |

The edge-aligned strips differ by about 18.1 mm along and 2.3 mm across, so no single geometry sits on the rules of both forms.
The seed takes the single-page strip, which on page 2 resolves to page x 89.17-138.28 mm and y 160.57-168.19 mm: inside the free signature area, 1.1 mm below the certification text, 2.2 mm above the bottom rule and 18.1 mm short of the right rule.
The single-page strip, unchanged from revision 1, reaches 0.34 mm into the certification text's descenders (ink at -4.98 against the strip's -5.32) and 0.42 mm past the box's outer bottom edge.

### ZPL measurement on the International Parcel capture

The V2 CN22 format of `postnord_label_cn22_international_parcel.zpl` was measured from a Labelary render (api.labelary.com, 8 dpmm, 203 dpi) of its static fields only: the box, the certification lines and the keyword, all in font 0 at 18 dots.
Font 0's advance is not carried by the stream, so the render measures the keyword's extent rather than an estimate from the character count.
Ink extents in label dots, inclusive:

| Landmark | Measurement |
|----------|-------------|
| Box rules | columns 10 and 829; bottom rule row 834 |
| Certification text | last ink row 745 |
| Keyword `^FO25,785` | ink x 26-229, y 784-800 |
| Format length | `^LL840` |
| Signature area | x 230-828, y 746-833 |
| Stamp (`^FO293,758`, 392 x 61 dots) | x 293-684, y 758-818: 63 dots past the keyword ink, 12 below the certification ink, 15 above the bottom rule |

The same kind of render of the rotated letter keyword (`^FWR`, `^FO20,35`, 20 dots) ends its ink at label y 263, so the letter strip (y 302.97-695.44) clears it by 40 dots.
The stamp is spliced before the second format's `^XZ`; the first format stays byte-identical.

### PDF measurement on the International Parcel capture

Page 2 of `postnord_label_cn22_international_parcel.pdf` was measured with pypdf and a 300 dpi pdftoppm render, as for the two-page capture.
The page draws the CN22 as `/Form2`, placed by a pure translation to (148.84964, 151.74292) pt, with `BBox` 297.57635 x 538.40393 pt, the 839 x 1518-dot label frame.
The keyword text matrix sits at form (8.867, 255.3695) pt, label (25, 798) dots; the box's inner rules are at form x 3.9015 and 294.0296 pt and y 242.601 pt, and the certification text's last baseline at form y 274.8769 pt.
The render puts the certification ink's bottom at page y 146.98 mm, the keyword ink's right edge at page x 85.51 mm and the box's inner bottom rule at 157.88 mm.
The `label_cn22/PDF/A4` seed resolves to page x 89.17-138.28 mm and y 148.06-155.68 mm: 3.7 mm past the keyword ink, 1.1 mm below the certification ink, 2.2 mm above the bottom rule and 18.0 mm short of the right rule, inside the signature area.

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
| 6.3 | `test(postnord): add two-page sandbox booking pdf fixture` | `tests/postnord/fixtures/postnord_label_cn22_booking_two_pages.pdf`, test file |
| 6.3 | `feat(postnord): recognize the tracked letter pdf label template` | `stamping.py`, test file |
| 6.3 | `feat(postnord): anchor the combined pdf stamp on the cn22 keyword` | `stamping.py`, test file |
| 6.3 | `test(postnord): classify then stamp every combined capture` | test file |
| 7.2 | `test(postnord): add international parcel label and cn22 fixtures` | `tests/postnord/fixtures/postnord_label_cn22_international_parcel.*`, `tests/postnord/test_label_cn22_international_parcel.py` |
| 7.2 | `feat(postnord): recognize international parcel label and cn22 sections` | `stamping.py`, both combined test files |
| 7.2 | `feat(postnord): anchor the combined zpl seed in the keyword's reading frame` | `stamping.py`, both combined test files |

Paths are relative to `modules/connectors/postnord/`.

Dependencies: `feat-document-stamping` provides the classifier, `document_sections`, and (task 1.6) the page override for seeded PDF stamps.
Follow-on on `feat-postnord-customs-invoice`: booking-time verification of the returned label with the classifier (a warning on unexpected composition) and opt-in standalone customs documents.

---

## Testing Strategy

`modules/connectors/postnord/tests/postnord/test_label_cn22_stamping.py` and `test_label_cn22_international_parcel.py`, unittest, no network.

| Class | Covers |
|-------|--------|
| `TestPostnordCombinedFixtures` | Each capture's structure: one `^XZ`, markers once and ordered, keyword once; one A4 page, or two A4 pages with the label then the CN22; marker text present or absent; tracked letter markers on no CN22 page |
| `TestPostnordDocumentSections` | Metadata publishes `DOCUMENT_SECTIONS`; classification of all six fixtures (two-page PDF on page 2) and a label-only ZPL |
| `TestLabelCn22ZplStamp` | Seed anchors the CN22 keyword in its reading frame; both combined letter ZPLs yield the lone CN22's `^GFA` field; carrier bytes before `^XZ` unchanged |
| `TestLabelCn22PdfMeasurement` | The combined page's frame placement and landmarks match the measurement constants; the box rule separates the sections |
| `TestLabelCn22TwoPageMeasurement` | Page 2's frame placement, keyword, box rules and certification baseline match the measurement constants |
| `TestLabelCn22PdfStamp` | Revision 3; no LETTER leak; classify-then-stamp lands along the keyword within the measured strip on the single page and within the measured free area on page 2 of the two-page capture, page 1 untouched, page count and text unchanged |
| `TestLabelCn22ClassifyThenStamp` | Every combined letter capture (two ZPL, two PDF) classified then stamped with the classified type and page |
| `TestInternationalParcelFixtures` | 91 ZPL: two formats, markers and keyword once each in their own format, the measured V2 layout; 91 PDF: two A4 pages, label then CN22 text |
| `TestInternationalParcelMarkers` | No label marker alternative in any CN22 section and no CN22 alternative in any label section across all ZPL fixtures; the International Parcel PDF markers on none of the four CN22 pages |
| `TestInternationalParcelClassification` | 91 ZPL `label_cn22` (page `None`); 91 PDF `label_cn22` on page 2; the 91 label format alone is not customs-bearing |
| `TestInternationalParcelZplStamp` | Measured keyword ink clears both signature areas; the V2 stamp in the CN22 format, upright, ink within the measured area and `^LL840`, label format byte-identical; the rotated letter stamp still at `^FO7,303`, rotated, within its strip |
| `TestInternationalParcelPdfStamp` | Page 2 landmarks match the measurement constants; classify-then-stamp lands upright within the measured signature area on page 2, page 1 untouched |

The pre-existing `test_cn22_stamping.py` behavior tests are unchanged; only the seed key-set assertion lists the new keys.

```bash
python -m unittest discover -v -f modules/connectors/postnord/tests
python -m unittest discover -v -f modules/sdk/tests
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Captures are by-id (and one booking) UX printouts, not every service | Medium | Medium | Live booking printouts cover the export letter (UX) in ZPL and the International Parcel (91) in ZPL and PDF; the UX PDF comes from a sandbox booking, and bookings that also fetch the standalone customs document are not captured; each further capture is added as a fixture and classified and stamped by the tests |
| PostNord changes layout | Low | Medium | Fixture-integrity tests fail first; re-measure with a revision bump |
| Combined and lone PDF regions diverge | Low | Low | Separate `label_cn22` seed |
| A further PostNord template places the keyword differently relative to its signature area | Medium | Medium | Add it as a fixture and an alternative marker set; the keyword geometry is re-verified against every captured layout |

---

## Migration & Rollback

Additive data only: new sections, new seed keys, new fixtures.
Rollback is reverting the commits; the `cn22` seeds and consumers stamping under `cn22` are unaffected.

---

## Known Limits

The label markers are template-specific: the letter (`Brev utrikes`, `SE_INTERNATIONAL_LETTER_LABEL`), tracked letter (`PostNord Tracked Letter`) and International Parcel (`International Parcel`, `NORDIC_SHIPPING_LABEL`) templates are captured.
A further template would classify as a lone `cn22` until its markers are added as another `lib.AnyOf` alternative.
The 91 ZPL and PDF come from separate live bookings of the same day; the 91 PDF stamp is verified here, and live PDF stamping remains consumer-side.
The V2 signature area was measured from a Labelary render, which emulates Zebra font 0; a printer's own font metrics may differ slightly, and the stamp clears the keyword ink by 63 dots.

The two-page PDF and the tracked letter label template come from a sandbox booking; whether a live booking returns the same template stays unconfirmed until a live UX PDF booking is captured.
On that layout the stamp sits inside the signature area rather than on the box rules, and on the single-page layout it overlaps the certification text's descenders by 0.34 mm.

---

## Appendices

### Appendix A: CN22 measurement derivation

The lone CN22 seed (`CN22_SEED`) was measured on the vendored ZPL form (`postnord_cn22.zpl`) and cross-checked against the lone CN22 PDF (`postnord_cn22.pdf`), so that both formats pin the same physical strip.

The PDF draws the label form as one `/Form1` XObject whose `BBox` (297.57635 x 538.40393 pt) is the 839 x 1518-dot label frame at 203 dpi, placed by a pure translation that puts the label origin at page (52.51, 53.53) mm.
The fonts use a `/Differences` cipher, so text positions are decoded through pypdf's `extract_text` visitor.
The mapping was validated before use: the PDF's vector separator columns land at label x 153.1, 200.2, 370.1, 420.1, 540.2, 590.2, 660.2 and 710.2 dots against the ZPL separators' integer dots, and the rule y-span [15.2, 694.9] against the `^FO10,15` `^GB820,680` form box, agreeing to under one dot throughout.
The decoded landmarks are the keyword field at label (25.00, 35.00) against `^FO20,35`, "Sweden Post" at (670.00, 35.00) against `^FO665,35`, and the certification block at (130.00, 35.00) against `^FO25,35`.

On this sideways (`^FWR`) form, `^FO` y is exactly where the line's reading starts, and `^FO` x anchors the descender-side bottom of the text (baseline plus the 5-dot descender at font size 20), so `^FO20,35` is the keyword field's absolute origin on the label.
From that origin, (2.5025, 4.3793) mm, the keyword offset `(x=-1.673, y=33.529)` mm resolves to (0.829, 37.908) mm, which is `^FO7,303`.
The `49.1 x 7.6` mm extent at rotation 90 is a pre-rotation 392 x 61-dot raster, rotated to 61 x 392 dots, so the strip covers label x 7-68 and y 303-695 dots: the signature column, with its bottom edge on the form box's bottom rule.
Mapped through `/Form1`, the same strip spans page x 53.34-60.96 mm and y 91.44-140.55 mm (label x 6.63-67.53, y 302.97-695.44 dots), which is the coordinate `placement` (x 53.34, y 91.44 mm, 49.11 x 7.62 mm, rotation 90) of the current seed.

The cross-check also showed that the earlier PDF placement (x 32.55, y 112.15 mm, 7.6 x 49.1 mm, rotation 90) mapped to label x -159.5 to 232.9 and y 468.5 to 529.2 dots, a horizontal strip starting 19.96 mm off the label's left edge.
It shares its centre, about page (57.1, 115.9) mm, with the measured vertical strip: it was the measured strip turned 90 degrees about its centre, a residue of the first seed revision's centre-pivot rotation that had been converted to the corner-anchored rotation without re-measurement.
The PDF placement was re-measured to the vertical strip, the coordinate `placement` that `CN22_SEED` and `LABEL_CN22_SEED` now carry.
