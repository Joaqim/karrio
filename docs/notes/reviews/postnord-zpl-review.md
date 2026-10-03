# PostNord ZPL label support — fresh-context review

Branch: postnord-carrier-connector. Scope: `git diff 9dd5dceb2..HEAD` (5 commits: PRD, parser normalization, proxy endpoint selection, tests, docs). Read-only review; no code modified. Tests: 42/42 pass (`python -m unittest discover modules/connectors/postnord/tests`). Diff is connector-local: no generated files (`mapper.py`, `karrio/schemas/postnord/*`) touched, no server/core files in the slice.

## Claim verdicts (from the review brief)

- Claim 1 "PDF path is byte-identical": CONFIRMED for the reachable contract, with one documented residual edge (Low finding 1). For `encoding: "base64"` printouts — the swagger example (`booking.swagger.json:3947-3951`), both committed PDF fixtures (`test_shipment.py:371,523`), and every live capture — `_printout_base64` is an identity passthrough (`create.py:122-123`), empirically verified. The `label_format` fallback change is unobservable for PDF bookings: `ctx.get("label_type", "PDF")` resolves to the string `"PDF"` on every default path, identical to the old literal. A PDF printout with `encoding` absent would now double-encode (old code passed it through) — difference exists but is unobserved and arguably less wrong than the symmetric old failure (raw ZPL passed through on absent encoding); see finding 1.
- Claim 2 `base64.b64encode` vs `lib.encode_base64`: CONFIRMED correct. `lib.encode_base64` is `encodebytes`-based and emits 76-char-wrapped output with trailing newline (`lib.py:1057-1061`); the implementation uses single-line `base64.b64encode` (`create.py:125`). Single-line is the consistent variant: `bundle_base64` itself emits `b64encode` single-line output (`helpers.py:131`), and both downstream consumers (`views/shipments.py:329` `get_file`, `zpl_to_pdf`) decode with lenient `base64.b64decode`, which tolerates either. No other postnord path produces label base64 (only call site is `create.py:125`), so no pipeline mixes variants.
- Claim 3 proxy branch shape: CONFIRMED robust. `(request.ctx.get("label_type") or "PDF").upper()` (proxy.py:105) maps missing/None/empty ctx to the PDF endpoint, and any value other than exactly `"ZPL"` post-upper also falls back to PDF — fail-safe to pre-change behavior for every malformed input. Every entry path into `proxy.create_shipment` receives a `Serializable` built by `shipment_request`, which always sets `label_type` (`create.py:250-258`): request-level via `LabelType.map(...).value_or_key` (so `"ZPL_4x6"` normalizes to `"ZPL"`, `"zpl"` is caught by the proxy's `.upper()`), else `connection_config.label_type.state`, else `"PDF"`. Returns reuse the same request builder (`return_shipment.py:12-13`), so they thread ctx identically. One residual input-hygiene gap (non-canonical casing like `"zpl_4x6"`) in finding 2.
- Claim 4 `multiZPL` default false: CONFIRMED correct. The swagger default is `false` (`booking.swagger.json:565-571`) and the proxy omits the param. With `false`, one printout per label arrives as multiple `labelPrintout` entries, which the connector bundles via `bundle_zpls`' newline join — empirically a valid ZPL stream (each format is a complete `^XA…^XZ` body; separators are whitespace). With `true` PostNord would return a single combined printout, which the single-printout passthrough handles. Both shapes are covered by construction.
- Claim 5 swagger `encoding` enum: CONFIRMED. `definitions.encoding` is `type: string` with description "Encoding of the data (base64)" and no enum (`booking.swagger.json:3947-3951`); `definitions.printout.required` is unset, so `encoding` is optional. The spec-gap note (`docs/notes/postnord/zpl-label-encoding.md`) is accurate, including the `"none"`-is-observed-only framing.
- Claim 6 pyright: CLEAN as far as statically evident. Both changed modules compile; the new expressions are None-safe by construction (`(printout.encoding or "").lower()`, `ctx.get(...)` with default, `or "PDF"` chains). The conditional-expression precedence in `create.py:255-257` parses as intended (`A if cond else (B or "PDF")`), and `value_or_key` never returns None, so `ctx["label_type"]` is always a string. Env-wide import-resolution diagnostics are unchanged noise, not new type errors.

## PRD compliance

- All four implementation phases present and matching the PRD's diagram: parser normalization + ctx threading (`create.py:78-97,250-258`), proxy endpoint selection (`proxy.py:102-117`), six new tests, README row + spec-gap note.
- All must-have success criteria have severe tests: exact base64-of-ZPL assertion (`test_parse_shipment_response_zpl` — fails under the old passthrough), exact proxy URL assertions at request level and config level plus a PDF-default guard (`test_create_shipment_pdf_url_by_default` — fails if the branch regresses to always-ZPL), and a multi-printout decode round-trip asserting the exact `bundle_zpls` join including the trailing newline.
- No scope creep: `multiZPL` never sent, no SVG, no Labelary conversion, no returns-specific endpoint, no schema regeneration.
- Existing PDF tests are untouched (the test diff is pure additions); pre-change fixtures pass unchanged, satisfying the byte-identical launch criterion.

## Open items (from the brief)

- Live ZPL `labelFormat` value never captured: handled safely — both the present and absent cases are fixture-tested, and the ctx fallback makes each produce the correct `label_type`.
- Bare `XA` paste artifact: recorded as unresolved in the spec-gap note; nothing in the connector inspects ZPL content, so no code impact.
- Live re-verification of `/labels/zpl` (PRD P1): still open, correctly tracked as nice-to-have; not a P0 gate item.

## Severity-ranked findings (no Critical, High, or Medium)

### LOW - PDF printout with `encoding` absent double-encodes
`printout.required` is unset in the swagger, so a PDF response omitting `encoding` is schema-legal; `_printout_base64` would treat its base64 data as raw text and re-encode it, corrupting the label (decode yields base64 text, not `%PDF`). Never observed: the swagger example, both fixtures, and all captures carry `encoding`, and for ZPL the absent case is the *expected* raw-text signal the fix exists for. Failure scenario: PostNord emits a PDF printout without `encoding` → served label is undecodable as PDF. This is the documented cost of decision D3 (trust the field, never sniff) and is recorded in the spec-gap note; revisit only if a live capture shows PDF printouts omitting the field.

### LOW - non-canonical-casing label types silently book PDF
Request-level `"zpl_4x6"` fails `LabelType.map` (member names are canonical-case) and flows through `value_or_key` as-is; the proxy's `"ZPL_4X6" != "ZPL"` check then selects the PDF endpoint, so the caller silently receives a PDF label. Canonical values (`"ZPL"`, `"ZPL_4x6"`, lowercase `"zpl"`) all work — `.upper()` catches the last. Not a regression (pre-change, every label type was ignored). Optional hardening: match on `"ZPL" in label_type` or normalize in `shipment_request`.

### LOW - untested input paths worth one test each
No test covers a request-level unified `"ZPL_4x6"` reaching the ZPL endpoint, nor asserts the proxy URL omits `multiZPL`. Both behaviors are correct by inspection; a test each would pin them against refactoring.

## Verdict: APPROVED

PRD-complete, connector-local, conventionally clean (`karrio.lib` throughout, functional style, no bare excepts, generated files untouched, no secrets beyond the pre-existing apikey-in-query pattern documented in `proxy._url`). All three findings are Low and none blocks the merge gate; the PRD's P1 live re-verification remains the follow-up.
