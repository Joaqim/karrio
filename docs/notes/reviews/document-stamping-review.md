# Document stamping P0 review

| Field | Value |
|-------|-------|
| Change | `add-document-stamping` |
| Branch | `add-document-stamping` |
| Commit range | `f01de9d1d..HEAD` (8 commits) |
| Reviewer | Code review subagent |
| Date | 2026-09-21 |
| Verdict | **PASS** |

---

## Phase 0: demo verification

Command run: `python -m unittest discover -f modules/sdk/tests/core`

Result: 95 tests, all OK.

Command run: `python -m unittest discover -f modules/sdk/tests`

Result: 115 tests, all OK. Matches the implementer's claimed count.

---

## Phase 1: spec compliance

Reviewed against `openspec/changes/add-document-stamping/specs/documents/stamping/spec.md`.
All SHALL requirements and every named scenario are satisfied.

### Requirement: format-preserving stamp entry point

Scenario "Stamping a PDF preserves format and structure":

- Format unchanged: `attr.evolve(document, base64=stamped)` at `stamping.py:221` leaves `document.format` untouched.
- Page count preserved: `clone_document_from_reader` copies the whole document, then a single `merge_transformed_page` on one page does not alter the page list. Test: `TestStampPdfBackend.test_preserves_format_and_page_count`.
- Fillable fields survive: `clone_document_from_reader` copies the `/AcroForm` dictionary at the PDF object level; `merge_transformed_page` only appends to the content stream. Test: `TestStampPdfBackend.test_acroform_fields_remain_fillable` uses a synthetic 2-page PDF with a `/Tx` widget field (`_acroform_pdf_b64` in `test_document_stamping.py:47-90`) and asserts `"signature_field"` is present in `get_fields()` after stamping.

Scenario "The carrier content layer is not rasterized":

Test `TestStampPdfBackend.test_carrier_text_layer_is_not_rasterized` uses the real `postnord_cn22.pdf` fixture (12 779 bytes, `%PDF-1.4`, 1 page, confirmed selectable text via `pypdf.extract_text()`). It extracts text before and after stamping and asserts equality. The real CN22 has no AcroForm (flat PDF), so the AcroForm-survival assertion correctly uses a separate synthetic fixture.

Input document not mutated: `test_returns_new_document_leaving_input_untouched` checks `document.base64 == original_b64` after `lib.stamp_document` returns, confirming `attr.evolve` creates a new object.

### Requirement: document format detection and dispatch

Scenario "A PDF is detected and routed to the PDF backend":

`sniff_document_format` at `helpers.py:169` checks magic bytes first (`%PDF-`, `^XA`, `\x89PNG...`) and falls back to content_type hints, then the `default` arg.
Test `TestSniffDocumentFormat.test_magic_bytes_win_over_content_type` submits `%PDF-1.4` bytes with `content_type="application/zpl"` and asserts "PDF" — magic bytes override the hint. The full suite exercises PDF, ZPL, PNG, adversarial bytes, leading whitespace, invalid base64, and truncated prefixes.

### Requirement: explicit rejection of unstampable formats

Scenario "A PNG document is rejected":

`stamp_document` calls `sniff_document_format`; when the detected format is not in `_BACKENDS` (`{"PDF": stamp_pdf}`), it raises `ValueError` with the format name in the message.
Test `TestStampDocument.test_rejects_png_document` checks `assertIn("PNG", str(ctx.exception))`.
Test `TestStampDocument.test_rejects_format_without_backend` does the same for ZPL, confirming ZPL rejection is explicit.

### Requirement: consumer-supplied placement takes precedence

Scenario "A supplied placement is used as given":

Code at `stamping.py:202`: `resolved = placement; if resolved is None: ...` — registry is only entered when `placement is None`.
Test `TestStampDocument.test_supplied_placement_skips_registry` passes an exploding registry (`raise AssertionError(...)` if called) alongside `placement=_placement()`. The test passes.

Scenario "A seed is consulted only on omission":

Test `TestStampDocument.test_registry_consulted_only_on_omission` omits `placement`, supplies a recording registry, and asserts `seen == ["postnord/cn22/PDF"]` — the registry was called exactly once with the expected key.

### Requirement: registry miss fails explicitly

Scenario "No seed and no placement":

Test `TestStampDocument.test_registry_miss_raises_naming_the_key` omits `placement`, uses the default `_empty_registry` (always returns `None`), and asserts `"postnord/cn22/PDF"` is in the error message.
Test `TestStampDocument.test_default_registry_always_misses` confirms that omitting both `placement` and a registry still raises.

### Requirement: layered compositing semantics

Scenario "Overlay draws above content":

`page.merge_transformed_page(overlay, transformation, over=True)` appends the image content stream after the carrier content stream. PDF content streams render in document order, so the image draws last (on top).

Adversarial probe run during this review: when `layer="overlay"`, the first content stream in the result begins with `q\nq\n1 0 0 1 148.8496...` (the carrier's content) and the image stream follows — correct z-order.

Scenario "Underlay draws beneath content":

`page.merge_transformed_page(overlay, transformation, over=False)` inserts the image content stream before the carrier content stream, so the carrier content draws on top of the image.

Adversarial probe: when `layer="underlay"`, the first content stream begins with `q\n1.47637795 0.0 0.0...` (the scaled/translated image) and the carrier content follows — correct z-order.

The test `TestStampPdfBackend.test_underlay_preserves_page_count` only asserts page count and format, not z-order. The z-order is correct by code analysis and the adversarial probe, but the test does not falsify a wrong z-order implementation. This is a minor test-coverage observation, not a defect.

### Requirement: no storage, verification, or validity assertion

No storage code exists. The utility returns `attr.evolve(document, base64=stamped)` and retains nothing. The docstring explicitly states the utility "stores nothing and asserts nothing about the legal validity or signature semantics of the result" at `stamping.py:184`.

### Tasks 1.1–1.6

| Task | Status |
|------|--------|
| 1.1 Q6 alpha spike resolved | White-flatten implemented at `stamping.py:94-101`; outcome documented in `design.md`. |
| 1.2 Magic-byte sniff helper | `helpers.py:169-203`; 11 unit tests in `TestSniffDocumentFormat`. |
| 1.3 StampPlacement/StampRequest models and mm conversion | `stamping.py:27-65`; 3 tests in `TestStampPlacementConversion`. |
| 1.4 PDF backend with overlay/underlay | `stamping.py:86-143`; 4 tests in `TestStampPdfBackend`. |
| 1.5 `lib.stamp_document` dispatch and re-exports | `lib.py:43-44,1052-1071`; 7 tests in `TestStampDocument`. |
| 1.6 Full SDK suite green | 115 tests, OK (confirmed by re-run). |

---

## Phase 2: code quality

### Adversarial probes

**mm-to-points conversion correctness:** `test_mm_to_points_known_inch` uses the physical fact that 25.4 mm = 1 inch = 72 points as an independent oracle, confirming the conversion constant `72.0 / 25.4` is correct. The `placement_to_pdf_rect` general case test (`test_placement_to_pdf_rect_flips_origin`) re-derives the same formula in the expected values — it confirms the formula is self-consistent but is not a fully independent oracle. The additional test `test_placement_at_top_left_sits_below_top_edge` provides an independent geometric check: at y=0mm from top-left, the PDF bottom-left y coordinate equals `page_height_pt - rect_height_pt`, without repeating the conversion formula. Together these are adequate, though the general-case test's oracle could be replaced with hard numeric values for stronger independence. Minor observation only — formula is mathematically correct.

**White-flatten correctness:** `PIL.Image.alpha_composite(backdrop, trimmed).convert("RGB")` at `stamping.py:101` correctly composites the RGBA image onto an opaque white backdrop before the PDF save. Semi-transparent marks render at their intended tone (blended toward white). The transparent surround becomes solid white. Converting to RGB before `save(format="PDF")` ensures Pillow emits no SMask in the image PDF, which is the Q6 resolved behavior.

**AcroForm-survival on underlay path:** the `test_acroform_fields_remain_fillable` test exercises the overlay path only. However, `merge_transformed_page` with `over=False` appends to the page's content streams without touching the `/AcroForm` dictionary, so AcroForm survival is equally guaranteed for underlay. The code structure at `stamping.py:135-137` makes this visible. Not testing underlay + AcroForm together is a minor coverage gap.

**Silent no-op path:** no path in `stamp_document` returns the input unchanged without raising. The two early-exit error conditions (format not in backends, registry miss) both raise `ValueError`. Format detection uses the magic-byte sniffer, which cannot produce an arbitrary unknown result for bytes that legitimately open as a PDF. No silent pass-through exists.

**Z-order verification (adversarial probe):** confirmed above under the underlay scenario.

### Import style

`import karrio.lib as lib` used in tests at `test_document_stamping.py:18`. The stamping module itself imports `karrio.core.models` and `karrio.core.utils.helpers` directly (no legacy `DP`, `SF`, `NF` utilities). `lib.py` re-exports via `import karrio.core.utils.stamping as stamping` at `lib.py:12`.

### Code style

No bare-except, no mutable default arguments, no imperative loops where comprehensions would apply, no noise comments. Docstrings on `StampPlacement`, `StampRequest`, `stamp_document`, `stamp_pdf`, `_build_overlay_page`, `placement_to_pdf_rect`, and `mm_to_points`. The `None`-default typing (`x: float = None`) matches the existing `models.py` attrs convention and is not a defect.

### No new dependencies

The implementation uses only `pypdf` and `PIL` (Pillow), both already pinned in `modules/sdk/pyproject.toml`. No reportlab, no new imports.

---

## Summary of findings

| Severity | Finding | Location |
|----------|---------|----------|
| Minor | `test_underlay_preserves_page_count` does not assert z-order; a wrong `over` value would not be caught by that test alone. The code and adversarial probe are correct. | `test_document_stamping.py:242-253` |
| Minor | `test_placement_to_pdf_rect_flips_origin` expected values re-derive the production formula; a stronger oracle would use pre-computed numerics. The physical mm→points oracle (`test_mm_to_points_known_inch`) and the top-left edge case independently ground the formula. | `test_document_stamping.py:165-180` |
| Minor | AcroForm survival is tested for overlay only; underlay + AcroForm is not exercised. Analysis shows it is guaranteed by implementation structure. | `test_document_stamping.py:231-239` |

No critical or important issues found. All three findings are minor test-coverage observations; the production code is correct in every case.

---

## Verdict: PASS

All spec scenarios are covered by real tests. The implementation is correct. The full SDK suite is green (115 tests OK). The three minor observations do not block approval.
