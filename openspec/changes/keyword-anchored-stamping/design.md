## Context

See `proposal.md` for motivation. The landed utility resolves placement in one step — a consumer-supplied `StampPlacement` used directly, or a `_SEED_REGISTRY` coordinate seed on omission — and then composites through format backends that this change does not touch. The PostNord CN22 ZPL fixture carries the anchor target in its own stream: `^FDDate and Sender's signature^FS` at `postnord_cn22.zpl:122`, its field origin in the nearest preceding `^FO20,35`, inside a one-command-per-line stream that also uses float `^FO` operands and `^FB` blocks emitted after their `^FS`.

## Goals / Non-Goals

**Goals:**

- Derive a ZPL stamp placement's position from the carrier form's own keyword field, with geometry owned by the consumer or the per-carrier seed.
- Let one registry seed anchor both formats of a carrier document: PDF by its measured coordinate placement, ZPL by keyword.
- Keep the compositing backends, bounds validation, rotation semantics, and date-prefixed single-call behavior untouched behind the resolution stage.

**Non-Goals:**

- No PDF-side keyword mechanism (PDF text extraction with coordinates is fragile; PDF keeps coordinate anchors).
- No derivation of rotation from the carrier stream's ambient `^FW` state.
- No change to the interim even date/signature strip split (Q9 stays open with the prior change).

## Decisions

### Resolution chain and mutual exclusivity

`stamp_document` and `StampRequest` gain a `keyword` parameter. The chain: a placement with both `x` and `y` set is used directly with no keyword or registry consultation; a keyword together with a fully anchored placement raises, rather than silently ignoring one of two contradictory anchors; a keyword with a geometry-only placement (`x`/`y` left `None`, extent and rotation set) resolves position from the form and geometry from that placement; a keyword with no placement takes geometry from the registry — the injected `registry` lookup when one is supplied, else the built-in seed, so injection owns resolution and a custom lookup never silently falls back to a shipped anchor; neither placement nor keyword consults the seed. Keeping `StampPlacement` as the geometry vehicle avoids a parallel geometry type, and the existing `_validate_anchor` already rejects a `None` anchor, so the geometry-only placement needs no new validation surface.

### Position derivation

The resolved position is the matched field's origin — the nearest preceding `^FO` in command order — converted from dots to millimetres at the geometry's `dpi`, plus a seed-owned offset in millimetres. Only position derives from the form; extent and rotation come from the geometry, so a keyword-resolved placement flows through `_validate_anchor`, the operand range check, and rotation exactly like a consumer placement. Rotation deliberately does not read the stream's `^FW` state: deriving it would require tracking format state across the stream for one input, and the seed's `rotation=90` already encodes the form's axis (confirmed against this fixture's `^FWR` in the prior change's seed provenance).

### Locator

The stream is scanned for `^FD...^FS` blocks; a block whose text contains the keyword locates the field, and the field's origin is the nearest preceding `^FO` command in stream order. The scan works on command tokens rather than line structure, since carrier streams mix inline and newline-separated styles; `^FO` operands may be floats and are parsed as such. The first match in stream order wins; zero matches raise an explicit error naming the keyword.

### Seed model

`StampSeed` gains `keyword` and `keyword_placement` fields. `placement` stays the PDF coordinate anchor; `keyword_placement` carries the ZPL strip's extent, rotation, `dpi`, and its offset in `x`/`y` (defaulting to the field origin itself). The PostNord entry keeps its existing PDF placement, adds the keyword and geometry, and the offset is measured against the current fixture the same way the PDF anchor was measured. `revision` stays at 2: it marks anchor supersession, the PDF placement is unchanged, and no code consumes it as a gate — the next genuine re-measurement bumps it. A ZPL document's natural key (`carrier/doc_type/ZPL/*`) reaches the same seed through a sibling registry entry sharing the `StampSeed` object, so `_default_registry`'s paper-only relaxation is untouched and no format-segment leakage is possible; the format-to-currency choice (PDF resolves `placement`, ZPL resolves `keyword` and `keyword_placement`) happens at resolution, not in the registry. `revision` continues to supersede: a carrier re-render that moves the line is absorbed by re-measuring the offset and bumping the revision.

### Keyword and PDF

Format detection already runs before resolution; a keyword supplied against a PDF document is rejected there with an explicit error, so no keyword plumbing reaches `stamp_pdf`.

## Risks / Trade-offs

- [Carrier re-render changes the keyword text] → the locator misses and raises explicitly; a seed revision with the new keyword ships the fix. No silent misplacement is possible.
- [`^FO` semantics vary across carrier generators (absolute vs contextual)] → the offset is measured against the real form, so the derived anchor is correct for it; the keyword's value is that the base point moves with the form across re-renders that shift the line.
- [Keyword matches multiple fields] → first match in stream order, documented here; an ambiguous keyword is a seed-authoring error fixed by a more specific keyword.
- [Fragmented `^FD` text across fields on some future form] → surfaces as an explicit keyword miss, not a wrong anchor.

## Migration Plan

Additive parameters and seed fields only; every call that omits `keyword` takes the identical path as before, byte-for-byte. No database, API, or dependency surface changes. Rollback is revert of the commits.
