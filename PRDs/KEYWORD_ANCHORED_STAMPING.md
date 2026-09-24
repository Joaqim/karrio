# Keyword-anchored stamp placement

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-09-24 |
| Status | In Progress |
| Owner | Joaqim Planstedt |
| Type | Enhancement |
| Reference | [AGENTS.md](../AGENTS.md) |

---

## Executive Summary

Stamping placement today requires a measured millimetre anchor: consumers supply coordinates or rely on a hand-measured registry seed per carrier, document type, format, and paper variant, and a carrier re-rendering a form can silently drift a shipped anchor.
The anchor is already printed in the carrier form itself — PostNord's CN22 carries a "Date and Sender's signature" field directly beside the strip a date-plus-signature stamp must fill — so this PRD derives ZPL placement from the document's own content through a keyword, with geometry owned by the consumer or the per-carrier seed.
The spec source of truth is the openspec change `openspec/changes/keyword-anchored-stamping/` (proposal, design, tasks, and the `documents/stamping` delta); this PRD precedes its implementation per the repo's PRD-first rule.

### Key architecture decisions

1. **Keyword stage ahead of the compositing pipeline**: a keyword locates the matching `^FD..^FS` field in the carrier ZPL stream and the placement's position derives from that field's `^FO` origin; the backends, bounds validation, rotation semantics, and date compositing are untouched behind the resolution stage.
2. **Explicit precedence with mutual exclusivity**: placement, then consumer keyword, then registry seed; a keyword together with a fully anchored placement raises rather than silently preferring one of two contradictory anchors.
3. **One seed, both formats**: `StampSeed` gains `keyword` and `keyword_placement` so a single entry anchors PDF by its measured coordinate placement and ZPL by its carrier form keyword, each format resolving implicitly with the consumer supplying neither.
4. **Command-token locator, first match, named miss**: the scan keys on `^FD..^FS` blocks with the nearest preceding `^FO`, tolerating line style, float operands, and multi-line block text; zero matches raise naming the keyword, so no silent misplacement is possible.
5. **Position-only derivation**: only the position comes from the form; extent, rotation, and `dpi` stay geometry-owned, so a keyword-resolved placement flows through `_validate_anchor`, the operand range check, and rotation exactly like a consumer placement.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| `keyword` on `stamp_document`, `StampRequest`, and the `lib` re-export | PDF keyword anchoring (PDF keeps coordinate anchors) |
| Resolution chain (placement / keyword / seed) with mutual exclusivity | Deriving rotation from the stream's ambient `^FW` state |
| ZPL command-token field locator (`^FD..^FS` blocks, nearest preceding `^FO`) | Date rendering changes (raster through the existing pipeline) |
| `StampSeed` `keyword` / `keyword_placement` + implicit ZPL seed resolution | The interim even date/signature split (Q9 stays open with the prior change) |
| PostNord CN22 keyword seed, measured against the vendored form | The accepted base64 PNG image contract |
| openspec delta for `documents/stamping` | Server serializer or API surface changes (`ValueError` already maps to 400) |
| Test oracles: locator, resolution chain, registry, fixture regression | |

---

## Open Questions & Decisions

### Pending Questions

| # | Question | Context | Options | Status |
|---|----------|---------|---------|--------|
| Q9 | Per-carrier date/signature partition | `DATE_STRIP_FRACTION = 0.5` is the interim even split, carried over unchanged from the corner-anchor change | A) keep the even split, B) measure a per-carrier partition on the group-4 CN22 | Open with the prior change; out of scope here |

### Resolved decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| D1 | ZPL anchor source | Carrier form keyword locates the field; geometry from the consumer or the seed | The anchor is printed in the form; a measured coordinate drifts on re-render while the keyword moves with the form | 2026-09-24 |
| D2 | Resolution precedence | Placement, then consumer keyword, then seed; a keyword with a fully anchored placement raises | Contradictory anchors must fail loudly; matches the spec's precedence requirement | 2026-09-24 |
| D3 | Geometry vehicle | `StampPlacement` doubles as the geometry vehicle (`x`/`y` left `None` means geometry-only) | Avoids a parallel geometry type; `_validate_anchor` is reused with no new validation surface | 2026-09-24 |
| D4 | Position derivation | Matched field's `^FO` origin, dots to millimetres at the geometry's `dpi`, plus a seed-owned offset in millimetres; rotation never reads `^FW` | Only position derives from the form; the seed's `rotation=90` already encodes the form's axis (prior change's Q10 closure) | 2026-09-24 |
| D5 | Locator | Command-token scan of `^FD..^FS` blocks, nearest preceding `^FO`, float operands, first match in stream order wins, miss raises naming the keyword | Carrier streams mix inline and newline-separated styles; the fixture's own `^FD` text spans physical lines | 2026-09-24 |
| D11 | Seed revision on keyword addition (was Q11) | Stay at `revision=2` | `revision` marks anchor supersession, and the PDF placement is byte-identical; adding keyword fields is not a re-measurement. The next genuine re-measurement bumps to 3. `revision` is metadata — no code consumes it as a gate | 2026-09-24 |
| D12 | ZPL registry keying (was Q12) | A sibling `"postnord/cn22/ZPL/*"` entry sharing the same `StampSeed` object | The natural `_registry_key` composition for a ZPL document hits without weakening `_default_registry`'s paper-only relaxation; the format-to-currency choice (PDF resolves `placement`, ZPL resolves `keyword`) happens at resolution, not in the registry | 2026-09-24 |
| D6 | Keyword and PDF | Rejected with an explicit error after the format sniff | PDF text extraction with coordinates is fragile; PDF keeps coordinate anchors and no keyword plumbing reaches `stamp_pdf` | 2026-09-24 |

### Edge Cases Requiring Input

None beyond Q9 above.

---

## Problem Statement

### Current state

```python
# stamping.py, stamp_document -- placement-or-seed, nothing between
resolved = placement
if resolved is None:
    paper = _detect_paper_variant(document.base64, document_format)
    key = _registry_key(carrier, doc_type, document_format, paper)
    resolved = lookup(key)
    if resolved is None:
        raise ValueError(
            "No stamp placement was supplied and no registry seed "
            f"resolves for key '{key}'"
        )
```

A consumer on an unseeded carrier must measure the form and supply millimetre coordinates.
A seeded carrier is anchored by a hand-measured registry entry, and a carrier re-rendering the form can move the target field while the shipped anchor stays put.
The revision mechanism recovers after the drift is noticed, but nothing in the document itself participates in placement.

### Desired state

```python
# stamp_document -- a keyword stage ahead of the backends
if keyword and document_format == "PDF":
    raise ValueError(...)  # keyword anchoring is unsupported for the format

# 1. a fully anchored placement (x and y set) is used as given,
#    with no keyword or registry consultation
# 2. a keyword raises on a fully anchored placement; otherwise the
#    position comes from the located ^FO origin (dots -> mm at the
#    geometry's dpi) plus the seed-owned offset, and the geometry
#    comes from the placement or the seed
# 3. neither input consults the seed: ZPL by the seed's keyword,
#    PDF by the seed's coordinate placement
```

### Problems

1. **Measurement burden**: placement needs coordinates or a hand-measured seed per carrier, document type, format, and paper variant; the consumer must know numbers the document already encodes as text.
2. **Silent drift**: a carrier re-render that moves the field misplaces the stamp without an error; the failure is visual, not mechanical.
3. **Unused in-document signal**: the ZPL stream names the target field in its own `^FD` text — PostNord's CN22 prints "Date and Sender's signature" directly beside the strip the stamp must fill — and placement ignores it.

---

## Goals & Success Criteria

### Goals

1. A ZPL stamp's position derives from the carrier form's own keyword field, with geometry owned by the consumer or the per-carrier seed.
2. One registry seed anchors both formats of a carrier document: PDF by its coordinate placement, ZPL by its keyword, the consumer supplying neither.
3. Every call that omits `keyword` takes the identical path as before, byte-for-byte.
4. The compositing backends, bounds validation, rotation semantics, and date-prefixed single-call behavior are untouched behind the resolution stage.

### Success criteria

| Metric | Target | Priority |
|--------|--------|----------|
| PostNord CN22 ZPL keyword resolution | deterministic placement with pinned `^FO` literals on the vendored form | Must-have |
| Keyword-absent path | byte-identical shipped behavior; existing suites green unchanged | Must-have |
| Keyword miss, keyword + PDF, unresolvable geometry | `ValueError` naming the keyword, the format, or the missing geometry source | Must-have |
| Full SDK suite | exit 0 | Must-have |

### Launch criteria

**Must-have (P0):**

- [ ] Red-first oracles for the locator, resolution chain, registry, and fixture regression (tasks.md group 1)
- [ ] Locator and resolution chain with PDF rejection (tasks 2.1, 2.2)
- [ ] Seed model and implicit ZPL seed resolution (task 2.3)
- [ ] PostNord CN22 keyword seed measured and pinned (task 3.1)
- [ ] openspec `documents/stamping` delta archived after verification

**Nice-to-have (P1):**

- [ ] Keyword seeds for further carrier ZPL forms as forms are vendored (mechanism ships with PostNord only)

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Keyword-anchored ZPL placement, geometry from consumer or seed | Anchor tracks the form across re-renders that shift the line; no consumer coordinates; misses are explicit | ZPL-only; keyword drift needs a seed revision; one more parse surface | **Selected** |
| Measured coordinate seeds only (status quo) | No parser; ships today | Measurement per carrier/format/paper; silent drift on re-render | Rejected |
| Keyword anchoring for PDF too | Format symmetry | PDF text extraction with coordinates is fragile; coordinate anchors already work | Rejected |
| Derive rotation from the stream's `^FW` state | One fewer seed field | Requires tracking format state across the stream for one input; the seed's `rotation=90` already encodes the axis | Rejected |
| Line-structured locator | Simpler scan | Streams mix inline and newline-separated styles; the fixture itself spans lines inside one `^FD` block | Rejected |
| Silent keyword precedence (ignore the keyword when a placement is set) | No new error path | Two contradictory anchors resolve silently; the conflict goes unnoticed | Rejected |

### Trade-off analysis

The parse surface is bounded — three caret commands (`^FO`, `^FD`, `^FS`) — and the worst failure mode converts from silent misplacement to a loud, named error.
The mechanism is deliberately ZPL-only: ZPL carries the field text verbatim in the stream, while PDF text extraction with coordinates is fragile, so the format symmetry cost buys nothing on the PDF side.
The seed stays the geometry owner, so a keyword never widens the validation surface: a derived placement meets the same `_validate_anchor`, operand-range, and mediabox checks as a consumer placement.

---

## Technical Design

### Existing code analysis

| Component | Location | Reuse strategy |
|-----------|----------|----------------|
| `stamp_document` dispatch | `stamping.py:662-723` | `keyword` parameter; resolution chain inserted after the format sniff (`stamping.py:689-699`); backend dispatch (`stamping.py:721`) untouched |
| `StampRequest` | `stamping.py:80-103` | Gains `keyword`; nothing past resolution consumes it |
| `StampPlacement` | `stamping.py:58-77` | Shape unchanged; doubles as the geometry vehicle with `x`/`y` left `None` |
| `_validate_anchor` | `stamping.py:185-207` | Reused verbatim; runs post-resolution, so a `None` anchor still rejects |
| `stamp_zpl` | `stamping.py:475-533` | Untouched behind resolution |
| `stamp_pdf` | `stamping.py:316-386` | Untouched; no keyword plumbing reaches it |
| `DATE_STRIP_FRACTION` | `stamping.py:42` | Untouched; the interim even split stays (Q9) |
| `StampSeed` / `_SEED_REGISTRY` / `_CN22_PLACEMENT` | `stamping.py:610-642` | Seed gains `keyword` and `keyword_placement`; PostNord entry adds the keyword geometry, keeps the measured PDF placement |
| `_default_registry` / `_registry_key` | `stamping.py:645-659` / `stamping.py:589-607` | Resolves ZPL seeds implicitly via the D12 sibling key |
| `lib.stamp_document` re-export | `modules/sdk/karrio/lib.py:1052-1083` | Gains the `keyword` pass-through |
| Keyword target | `modules/sdk/tests/core/fixtures/postnord_cn22.zpl:121-122` | `^FO20,35` then `^FDDate and Sender's signature^FS`; stream facts in Appendix A |
| Tests | `modules/sdk/tests/core/test_document_stamping.py`, `..._fixtures.py` | Oracle additions per the testing strategy |

### Resolution chain

```
          stamp_document(image, placement?, keyword?, carrier, doc_type)
                          │
                          ▼
                sniff the document format
                          │
        keyword and PDF ──┴──► ValueError: keyword anchoring
                               is unsupported for the format
                          │
                          ▼
             1. placement fully anchored (x and y set)?
                └── yes ──► use as given; no keyword or
                             registry lookup is performed
                          │
                          ▼
             2. keyword supplied?
                ├── placement also fully anchored ──► ValueError
                ├── geometry-only placement (x/y None) ──► position
                │      from the located field origin; extent,
                │      rotation, dpi from the placement
                └── no placement ──► geometry from the seed's
                       keyword_placement; absent ──► ValueError
                       naming the missing geometry source
                          │
                          ▼
             3. neither supplied ──► registry seed for the key
                ├── ZPL ──► seed.keyword locates the field;
                │      geometry from seed.keyword_placement
                └── PDF ──► seed.placement, as shipped
                     miss ──► ValueError naming the key
                          │
                          ▼
          resolved StampPlacement(x, y, w, h, rotation, dpi)
                          │
                          ▼
          backends unchanged: ZPL ^GFA raster splice / PDF
          transform merge, rotation, operand + mediabox
          bounds, date strip (Q9 split unchanged)
```

### Locator scan over the carrier stream

```
  the stream as command tokens (postnord_cn22.zpl:120-125)

    ^FB620,1, 0,L            not an ^FD..^FS block -- skipped
    ^FO20,35                 remembered as the running origin
    ^FDDate and Sender's signature^FS
        │                    block whose rendered text contains
        │                    the keyword -- MATCH (first wins)
        ▼
    field origin = ^FO20,35   the ^FO nearest preceding the
                              matched block in stream order
    ^FB680,1, 0,L            follows ^FS: opens the next
    ^FO665,35                field's layout; never consulted
    ^FDSweden Post^FS        no match; the scan would continue

  stream facts the scan tolerates
    - one command per line here, but the certification ^FD block
      (lines 117-119) spans three physical lines -- the scan works
      on tokens, not lines
    - ^FO operands may be floats (^FO385,488.3333333333333) and
      are parsed as such
    - ^FB blocks are emitted after their field's ^FS
```

### Position derivation

Only the position derives from the form.

```python
resolved.x = dots_to_mm(origin_x_dots, geometry.dpi) + offset.x  # mm
resolved.y = dots_to_mm(origin_y_dots, geometry.dpi) + offset.y  # mm
# dots_to_mm(v, dpi) = v * 25.4 / dpi  -- the inverse of mm_to_dots
```

The origin is the matched field's nearest preceding `^FO`, converted from dots to millimetres at the geometry's `dpi`, plus the seed-owned offset in millimetres.
Extent, rotation, and `dpi` come from the geometry, so the resolved placement meets `_validate_anchor`, the ZPL operand range check, and the rotation path exactly like a consumer placement.
Rotation deliberately does not read the stream's `^FW` state: deriving it would require tracking format state across the stream for one input, and the seed's `rotation=90` already encodes the form's axis (the prior change's Q10 closure).

### Seed model

`StampSeed` gains `keyword` and `keyword_placement`.
`placement` stays the PDF coordinate anchor; `keyword_placement` carries the ZPL strip's extent, rotation, `dpi`, and its offset in `x`/`y` from the located field origin.

```python
_CN22_KEYWORD_PLACEMENT = StampPlacement(
    # x/y are the measured mm offsets from the located ^FO origin
    # (task 3.1); extent, rotation, and dpi are the strip geometry
    x=<measured>, y=<measured>,
    width=7.6, height=49.1, rotation=90, dpi=203,
)
_CN22_SEED = StampSeed(
    placement=_CN22_PLACEMENT,  # unchanged: the PDF coordinate anchor
    keyword="Date and Sender's signature",
    keyword_placement=_CN22_KEYWORD_PLACEMENT,
    revision=2,  # unchanged: the PDF anchor is not superseded (D11)
)
_SEED_REGISTRY = {
    "postnord/cn22/PDF/A4": _CN22_SEED,
    "postnord/cn22/ZPL/*": _CN22_SEED,  # D12: same seed, ZPL currency
}
```

`revision` continues to supersede: a carrier re-render that moves the line is absorbed by re-measuring the offset (and, if the text changed, the keyword) and bumping the revision.
The ZPL lookup reaches the same seed through the sibling `ZPL/*` key (D12); a PDF hit resolves the seed's `placement`, a ZPL hit resolves its `keyword` and `keyword_placement`.

### Edge cases

| Scenario | Expected behavior | Handling |
|----------|-------------------|----------|
| Keyword text drifts on a carrier re-render | Explicit miss naming the keyword | Seed revision with the new keyword ships the fix; no silent misplacement |
| Keyword matches multiple fields | First match in stream order | Documented (D5); an ambiguous keyword is a seed-authoring error fixed by a more specific keyword |
| `^FD` text fragmented across fields | Explicit keyword miss, not a wrong anchor | Surfaces as a miss; the fix is a more specific keyword or a coordinate seed |
| Keyword supplied with a PDF document | `ValueError` identifying keyword anchoring as unsupported for the format | Format sniff precedes resolution |
| Keyword with a fully anchored placement | `ValueError` | Contradictory anchors (D2) |
| Keyword, no placement, no seed geometry | `ValueError` naming the missing geometry source | Chain raises before any backend work |
| Keyword, no placement, custom `registry` supplied | Injected lookup consulted for the keyword geometry; the built-in seed is suppressed | Injection owns resolution — an empty injected lookup raises the same explicit error a seedless key raises |
| Geometry-only placement (`x`/`y` `None`) | Position from the form, geometry from the placement | Resolution fills `x`/`y` before `_validate_anchor` runs |
| Float `^FO` operands | Parsed as floats | Locator parses operands as floats |
| `^FB` blocks after `^FS` | Ignored by the field scan | Token scan keys on `^FD..^FS` blocks |
| Keyword absent | Byte-identical shipped path | Chain falls through to placement/seed as today |

### Failure modes

| What can go wrong | Impact | Mitigation |
|-------------------|--------|------------|
| Carrier re-render moves the line, keyword intact | Derived anchor moves with it | That is the feature: the base point tracks the form |
| Carrier re-render changes the keyword text | Locator miss | Explicit error naming the keyword; seed revision with the new keyword |
| `^FO` semantics vary across carrier generators (absolute vs contextual) | Derived origin wrong for an unmeasured generator | The offset is measured against the real form; operand bounds reject off-label results loudly |
| Ambiguous keyword selects the wrong field | Stamp lands on the wrong field | First-match documented; fixture regression pins the real form |
| Locator misreads a stream style | Miss or wrong origin | Token-based scan; synthetic oracles in both inline and newline styles |

---

## Implementation plan

### Phase 1: PRD and failing tests

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| 1.1 This PRD | `PRDs/KEYWORD_ANCHORED_STAMPING.md` | This document | M |
| 1.2 Locator oracles: nearest preceding `^FO`, float operands, first match, named miss | `modules/sdk/tests/core/test_document_stamping.py` | Pending | M |
| 1.3 Resolution-chain oracles: exclusivity raise, geometry-only resolution, unresolvable geometry, PDF rejection | `modules/sdk/tests/core/test_document_stamping.py` | Pending | M |
| 1.4 Registry oracles: implicit ZPL seed, consumer keyword precedence, keyword-less seed miss, keyword-absent behavior | `modules/sdk/tests/core/test_document_stamping.py` | Pending | M |
| 1.5 PostNord fixture regression: keyword resolution with pinned `^FO` literals, one `^GFA` strip | `modules/sdk/tests/core/test_document_stamping_fixtures.py` | Pending | M |

### Phase 2: locator and resolution chain

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| 2.1 `_locate_zpl_field` command-token scan | `stamping.py` | Pending | M |
| 2.2 `keyword` through `stamp_document`, `StampRequest`, `lib` re-export; resolution chain; PDF rejection after the format sniff | `stamping.py`, `modules/sdk/karrio/lib.py` | Pending | M |
| 2.3 `StampSeed` `keyword` / `keyword_placement`; implicit ZPL seed resolution in `_default_registry` | `stamping.py` | Pending | M |

### Phase 3: PostNord CN22 seed

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| 3.1 Measure the keyword geometry and offset against the vendored form, cross-checked against the PDF seed strip; set the seed | `stamping.py` | Pending | M |

### Phase 4: verification

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| 4.1 Both stamping suites + `./bin/run-sdk-tests`, black clean; fresh-context review gate against the spec delta, this PRD, and `.claude/rules/prd-and-review.md` | — | Pending | S |

**Dependencies:** Phase 1 lands red, Phases 2 and 3 turn it green, Phase 4 gates the merge.
The openspec change `openspec/changes/keyword-anchored-stamping/` is already authored on this branch; its delta is archived in Phase 4.

---

## Testing strategy

All tests use `unittest` (never pytest), run from the repository root with the repo venv.
Every scenario in the spec delta maps to a concrete oracle; tasks.md group 1 lands these red against the shipped code before Phases 2 and 3 turn them green.

### Oracle table

| Spec scenario | Test (file, task) | Asserted observable |
|---------------|-------------------|---------------------|
| ADDED: consumer keyword anchors at the carrier's own field | `test_document_stamping.py`, 1.3 | Synthetic ZPL: output `^FO` equals the matched origin converted to dots plus the offset (pinned literals); the matched `^FD..^FS` text survives in the output; a derived out-of-range placement raises |
| ADDED: keyword matching no field fails explicitly | `test_document_stamping.py`, 1.2 | `assertRaises(ValueError)`, message names the keyword; no document returned |
| ADDED: keyword with unresolvable geometry fails explicitly | `test_document_stamping.py`, 1.3 | Keyword + no placement + no seed geometry: `ValueError` naming the missing geometry source |
| ADDED: keyword supplied for a PDF document is rejected | `test_document_stamping.py`, 1.3 | PDF bytes + keyword: `ValueError` identifying keyword anchoring as unsupported for the format |
| ADDED: seeded ZPL document resolves implicitly by keyword | `test_document_stamping.py`, 1.4 | Seeded key, no consumer input: one `^GFA` field at the seed-derived origin |
| ADDED: one seed anchors both formats | `test_document_stamping.py`, 1.4 | Seed with placement + keyword: the PDF leg reuses the standing `TestCn22Seed` band oracle; the ZPL leg pins the derived `^FO` |
| MODIFIED: supplied placement is used as given | `test_document_stamping.py`, 1.4 | Output identical with a keyword and a seeded key present: the placement wins, no lookup performed; standing placement suite stays green |
| MODIFIED: supplied keyword outranks the registry | `test_document_stamping.py`, 1.4 | Consumer keyword resolves against the consumer's keyword, not the seed's |
| MODIFIED: seed is consulted only on omission | `test_document_stamping.py`, 1.4 | ZPL + neither input against a keyword-less seed: registry-miss error naming the key; keyword-absent call keeps today's behavior |
| Fixture regression (PostNord CN22) | `test_document_stamping_fixtures.py`, 1.5 | Keyword "Date and Sender's signature" on the vendored form: deterministic placement with pinned `^FO` literals; the single call with image and date composites one `^GFA` strip at the derived origin with the standing raster assertions |

### Running tests

```bash
.venv/karrio/bin/python -m unittest discover -v -f modules/sdk/tests -p "test_document_stamping*"
./bin/run-sdk-tests
```

---

## Risk assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Locator misreads a generator's stream style | High | Medium | Token-based scan; synthetic oracles in both inline and newline-separated styles; explicit miss over silent anchor |
| Keyword drift on a carrier re-render | Medium | Medium | Explicit miss error naming the keyword; seed revision with the new keyword |
| Ambiguous keyword selects the wrong field | High | Low | First-match documented; specific keywords in seed authoring; fixture regression pins the real form |
| Keyword-absent regression | Medium | Low | Byte-identity oracle; existing suites must stay green unchanged |
| Full-suite regression | Medium | Low | `./bin/run-sdk-tests` before any commit |

---

## Migration and rollback

### Backward compatibility

- **API compatibility**: `keyword` is an additive parameter defaulting to `None`; every keyword-absent call takes the identical resolution path as before, byte-for-byte.
- **Data compatibility**: no persisted data carries placements or keywords; `_SEED_REGISTRY` converts in-tree.
- **Feature flags**: none, per the change-management preference.

### Rollback procedure

1. Revert the commits; the keyword-bearing seed fields revert with them.
2. The openspec change archive records the mechanism for forensics.
3. No data cleanup is required.

---

## Appendices

### Appendix A: the keyword target in the vendored form

The PostNord CN22 ZPL fixture runs its field region under `^FWR` with the whole form at `^LL1520` dots.

```
modules/sdk/tests/core/fixtures/postnord_cn22.zpl:120-125

^FB620,1, 0,L
^FO20,35
^FDDate and Sender's signature^FS
^FB680,1, 0,L
^FO665,35
^FDSweden Post^FS
```

The keyword target is `^FDDate and Sender's signature^FS` at line 122, its field origin the nearest preceding `^FO20,35` at line 121.
Stream facts the locator must tolerate: one command per line in general, but `^FD` block text spans physical lines (the certification block at lines 117-119); `^FO` operands may be floats (`^FO385,488.3333333333333` at line 107); `^FB` blocks are emitted after their field's `^FS`.

### Appendix B: measurement cross-check (task 3.1)

The PostNord keyword offset is measured against the vendored ZPL form and cross-checked against the PDF seed on the same CN22 layout, per this appendix's mandate that both formats' seeds pin the same physical strip.
The cross-check resolved the mapping, produced the measured ZPL seed, and found the shipped PDF placement to be the erroneous party.
The verification script's outputs (run 2026-09-24) are recorded below.

**Mapping.**
The CN22 PDF carries the label form as a `/Form1` XObject (`BBox` 839.0 x 1518.0 dots at 203 dpi; the form's `cm` placement on the page is a pure translation, label origin at page (52.51, 53.53) mm).
Fonts use a `/Differences` cipher, so text positions decode through `extract_text`'s visitor.
Validation: the PDF's vector separator columns land at label x 153.1/200.2/370.1/420.1/540.2/590.2/660.2/710.2 against the ZPL separators' integer dots, and the rule y-span [15.2, 694.9] against the `^FO10,15 ^GB820,680` form box — sub-dot agreement throughout.
Decoded landmarks: the keyword field at label (25.00, 35.00) against `^FO20,35`, "Sweden Post" at (670.00, 35.00) against `^FO665,35`, the certification block at (130.00, 35.00) against `^FO25,35`.
So `^FO` y is the line's reading start exactly and `^FO` x anchors the descender-side bottom (baseline + descender, 5 dots at fs20); `^FO20,35` is the field's absolute origin on the label.

**Measured keyword seed.**
Offset from the located origin (2.5025, 4.3793) mm: `(x=-1.673, y=+33.529)`, resolving to (0.829, 37.908) mm → `^FO7,303`; extent `width=49.1, height=7.6` (pre-rotation 392x61 dots → rotated 61x392, bpr 8, total 3136), rotation=90, dpi=203.
The strip (label x 7..68, y 303..695 dots) covers the signature column with its bottom edge on the form box's bottom rule.

**Cross-check outcome: the shipped PDF placement is the erroneous party.**
The shipped `_CN22_PLACEMENT` (32.55, 112.15, 7.6 x 49.1, rotation=90) maps to label x [-159.5, 232.9], y [468.5, 529.2]: a horizontal strip starting 19.96 mm off the label's left edge (confirmed on a 150 dpi render), and unexpressible as a keyword-anchored placement — `_validate_anchor` rejects the derived x of -19.961 mm.
The original archived probe (probe2b: page x [53.34, 60.96], y [91.44, 140.55] mm — a vertical 7.62 x 49.11 mm strip) maps on-form (label x [6.63, 67.53], y [302.97, 695.44], bottom edge on the form bottom rule).
The two strips share a centre (~(57.1, 115.9) page mm): the shipped extent is the archived strip rotated 90 degrees about its centre — the fossil of the revision-1 centre-pivot seed, faithfully converted by revision 2 but never re-measured, and that change's band oracles were circular against the same anchor.

**Decision (owner, 2026-09-24, option A).**
The ZPL keyword seed lands on the measured vertical strip.
The shipped PDF placement is documented here as the erroneous party, with a correction note beside `_CN22_PLACEMENT` in the module.
A follow-up change re-measures `_CN22_PLACEMENT` to `StampPlacement(x=53.34, y=91.44, width=49.11, height=7.62, rotation=90)` — width and height are pre-rotation dimensions and the rotated extent's top-left anchors at `(x, y)`, so this encoding renders the vertical 7.62 x 49.11 mm strip at page (53.34, 91.44); an earlier draft of this note said "rotation 0", which described the rendered rectangle's upright shape rather than the placement encoding, and rotation 0 would render the signature upright against the form's `^FWR` reading — and rewrites `TestDefaultRegistry`/`TestCn22Seed` and the fixtures band literals with non-circular oracles (change `cn22-pdf-seed-remeasure`, `PRDs/CN22_PDF_SEED_REMEASURE.md`).
The registry-seeded PDF path is not live in production, so the follow-up carries no deployment urgency.
