## Context

See proposal.md — Why for motivation.
Karrio returns duty documents as base64 in `ShippingDocument(category, format, print_format, base64, url)`, with `format` carrying `PDF`, `ZPL`, or `PNG`.
Nothing in karrio touches document pixels after a carrier returns them.
The SDK already pins Pillow and pypdf (`modules/sdk/pyproject.toml`), and a live magic-byte sniff precedent exists in the DHL Freight Sweden connector (`LABEL_MAGICS = ((b"%PDF-", "PDF"), (b"^XA", "ZPL"))`).
The full decision record with citations is `PRDs/DOCUMENT_STAMPING_UTILITY.md` (D1-D13); this design owns the model shapes and the Q6/Q7 framing.

## Goals / Non-Goals

**Goals:**

- A single SDK entry point that multiplexes on detected format and composites via the matching backend.
- Zero new SDK dependencies for the launch (PDF) backend.
- A neutral placement vocabulary that converts cleanly to PDF points (bottom-left flip) and, later, ZPL dots (dpi-scaled).

**Non-Goals:**

- ZPL compositing at launch — the sniffer recognizes `^XA`, but the ZPL backend (dither, GRF, `^FO/^Gfa` splice) is a P1 follow-up carried in tasks.md, not a spec blocker.
- Any server or API surface — deferred pending the Q7 precedent survey.
- Registry seed coverage at launch — consumer-supplied placement is the complete primary path; seeds accrue incrementally as they are measured against live documents.

## Decisions

### Sniff-and-dispatch multiplexer over per-carrier features

Detect format by magic bytes (`%PDF-`, `^XA`) with content-type and config fallbacks, generalizing the DHL Freight Sweden `_label_type` pattern into a shared helper, then route to a per-format backend.
PDF and ZPL compositing share no mechanics; the multiplexer is the only shared abstraction, so a per-carrier feature set would duplicate it N times.
Alternative rejected: per-carrier stamping methods — reimplements the mux, dithering, and anchor conventions per connector.

### PDF backend via Pillow page + pypdf transformation merge, no reportlab

The PNG is white-flattened (alpha composited onto an opaque white background per the Q6 finding), becomes a single-page image PDF via Pillow, then is scaled and translated into place with a pypdf `Transformation().scale(s).translate(tx, ty)` fed to `merge_transformed_page`.
This reuses libraries the SDK already pins (D13 → no reportlab), keeps the carrier text layer intact, and leaves AcroForm dictionaries untouched.
Alternative rejected: reportlab overlay — adds an SDK dependency for no capability the transformation merge lacks; documented only as the escape hatch if the white-flatten path proves inadequate.

The Q6 spike (task 1.1) resolved the flattening path: Pillow's PDF writer emits no soft mask (SMask) for an RGBA image, so PNG alpha is dropped on save and a semi-transparent mark would otherwise render fully opaque.
The backend therefore composites the RGBA image onto an opaque white background before the image-PDF save, so a 50%-alpha stroke reads as its intended tone and the transparent surround reads as white — acceptable because signature anchors target blank blocks and the letterhead underlay draws beneath carrier content regardless.

### Neutral placement units, optional registry keying

Anchors are millimetres from the top-left of a one-based page.
Millimetres convert cleanly to PDF points (bottom-left origin flip) and, for the follow-up backend, ZPL dots at printer density.
The optional registry key shipped at launch is three-part — (carrier, document category, detected format) — joined into a single string with `*` standing in for a missing segment.
Category resolution goes through `ShippingDocumentCategory.map(...).name_or_key` so PostNord `printoutComposition` strings and normalized names converge on one key.
A paper-variant segment (the PostNord `rotate` / A4-vs-letter case) is deliberately deferred to the group-4 seed work, where it first becomes load-bearing; the launch registry ships empty, so key arity is behaviorally inert until seeds exist.
Alternative rejected: PDF points or ZPL dots as the public unit — leaks a coordinate system and origin convention into consumer code.

### Letterhead is an underlay via merge order

A letterhead is composited by merging the carrier content page over the letterhead page; draw order is the z-order (D6).
ZPL has no z-order, so ZPL letterhead is out of practical scope.

### Output replaces base64 in place; format is invariant

The stamped document replaces `ShippingDocument.base64` and leaves `format` unchanged (D7), so the consumer's document-list shape is stable and format never leaks into consumer code.

### Illustrative model shapes

Final field names belong to implementation, but the launch shape is:

```python
@attr.s(auto_attribs=True)
class StampPlacement:
    page: int = 1
    x: float = None        # millimetres from top-left of the page
    y: float = None
    width: float = None
    height: float = None
    dpi: int = 203         # ZPL target density; ignored by the PDF backend

@attr.s(auto_attribs=True)
class StampRequest:
    image: str = None                # base64 PNG
    placement: StampPlacement = None # consumer-supplied anchor (primary)
    carrier: str = None              # optional registry seed lookup
    doc_type: str = None             # ShippingDocumentCategory name
    layer: str = "overlay"           # overlay | underlay
```

## Risks / Trade-offs

- Pillow may drop PNG alpha (SMask) on PDF save (Q6) → white-flatten onto the block background is the bounded fallback, acceptable because signature anchors target blank blocks and the letterhead underlay is unaffected; reportlab re-evaluation is the documented escape hatch.
- pypdf transformation merge could interact badly with a carrier's page geometry → round-trip tests over real PostNord and FedEx fixtures before finalization.
- A carrier re-renders a form and a karrio-supplied seed anchor drifts → seeds are optional and carry a revision field; consumer-supplied anchors are unaffected by form drift.
- A stamped document is misused as a legal assertion → the responsibility boundary (D8) is stated in the utility docstring and the workflow guide; the utility asserts nothing about validity.

## Migration Plan

Stamping is additive and opt-in: no existing endpoint, serializer, or document payload changes, and no schema or migration impact.
Rollback removes the utility module and its `lib` re-export; there is no data to unwind, and the full SDK plus connector suites are the verification gate.

## Open Questions

- Q6 (alpha fidelity): resolved (task 1.1 spike) — Pillow's PDF writer does not preserve PNG alpha as an SMask; saving an RGBA image emits no soft mask, so alpha is dropped and a semi-transparent mark renders fully opaque. The PDF backend white-flattens (composites the RGBA image onto opaque white) before the image-PDF save. This tunes only the backend's flattening behavior; the specs, the Pillow + pypdf approach, and the task breakdown are unchanged.
- Q7 (server precedent): does precedent exist for a generalized server-side surface over an SDK utility? This gates the deferred server phase only; absent precedent the change stays SDK-scoped, so it does not affect the launch specs or tasks.
