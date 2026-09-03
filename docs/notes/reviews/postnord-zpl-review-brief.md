# PostNord ZPL label support — review brief

2026-09-03. Prepared after implementation; the reviewer is expected to start
from this brief plus the repository, NOT from the implementing session's
context. Re-derive every finding independently — the "open items" below are
verification questions, not conclusions to adopt.

## Scope

Branch `postnord-carrier-connector`, commits `7f3059c82..ec526e28c` (5:
PRD, parser normalization, proxy endpoint selection, tests, docs).

```bash
git diff 9dd5dceb2..HEAD --stat
```

Files: `modules/connectors/postnord/karrio/providers/postnord/shipment/create.py`,
`.../mappers/postnord/proxy.py`, `.../tests/postnord/{test_shipment,fixture}.py`,
`.../README.md`, `PRDs/POSTNORD_ZPL_LABEL_SUPPORT.md`,
`docs/notes/postnord/zpl-label-encoding.md`.

## Entry points

- PRD: `PRDs/POSTNORD_ZPL_LABEL_SUPPORT.md` (decisions D1-D3, edge cases,
  out-of-scope list)
- Spec-gap note: `docs/notes/postnord/zpl-label-encoding.md`
- Reference connector for the label-type pattern: smartkargo
  (`providers/smartkargo/shipment/create.py` ~159, `mappers/.../proxy.py` ~39)
- Karrio base64 contract: `modules/sdk/karrio/core/utils/helpers.py`
  (`bundle_zpls`, `bundle_base64`)

## Verification commands

```bash
source bin/activate-env
python -m unittest discover -v modules/connectors/postnord/tests   # 42 tests
```

## Claims worth adversarial checking

1. **"PDF path is byte-identical"** — the PRD promises zero behavior change
   for existing PDF bookings. Verify against the pre-change fixtures, not
   just that tests pass: the `label_format` fallback changed from `"PDF"`
   literal to ctx-driven, and `_printout_base64` sits in front of the
   passthrough. Construct a PDF response with `encoding` absent and check
   what happens (is base64-with-encoding-absent double-encoded? Is that
   reachable in practice for PDF?).
2. **`base64.b64encode` vs `lib.encode_base64`** — the implementation uses
   the former (single-line) because the latter is `encodebytes`-based
   (76-char wrapping). Confirm this matches how the server/dashboard decode
   `Documents.label`, and that no other postnord path uses the wrapping
   variant.
3. **Proxy branch shape** — `label_type = (request.ctx.get("label_type")
   or "PDF").upper()`; consider malformed values (`"zpl"`, `"ZPL_4x6"` at
   proxy level, though `shipment_request` normalizes via `LabelType.map`).
   Does every entry path into `create_shipment` go through
   `shipment_request`? (The mapper could be called directly.)
4. **`multiZPL` parameter** — deliberately not sent (default `false`). Check
   the swagger: does `false` mean one printout per label (current bundle
   path) vs a single combined printout? Is the bundling behavior correct
   either way?
5. **Swagger `encoding` enum** — confirm from
   `vendor/booking.swagger.json` (~line 3947) that `"none"` is genuinely
   undocumented, so the observation note is accurate.
6. **Pyright diagnostics** — the implementing session dismissed import-
   resolution and Optional diagnostics as environment noise (unresolved
   connector-local imports). Spot-check rather than trusting this: nothing
   in the new code introduces a genuinely new type error.

## Session-known open items (verify, do not assume)

- Live ZPL response `labelFormat` value never captured; parser falls back
  to the requested type via ctx. Fixture covers the absent case.
- The original paste opened with a bare `XA` (no caret) — paste truncation
  or real payload artifact? Recorded in the spec-gap note as unresolved.
- Live re-verification of `/labels/zpl` against the test account is PRD P1,
  not yet performed.

## Output contract

Write findings to `docs/notes/reviews/postnord-zpl-review.md` following the
dhl-freight-phase0-review.md format: per-claim verdicts, severity-ranked
findings (MEDIUM/LOW/…), final APPROVED / NEEDS CHANGES verdict with
required actions.
