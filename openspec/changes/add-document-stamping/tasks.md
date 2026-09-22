## 1. Launch — SDK core utility (PDF)

- [x] 1.1 Run the Q6 alpha spike: save a real CN22 signature PNG as a Pillow image PDF and inspect whether RGBA alpha survives as an SMask; record the outcome (true alpha vs. white-flatten fallback) in design.md before finalizing the backend
- [x] 1.2 Add a shared magic-byte sniff helper generalizing DHL Freight Sweden `LABEL_MAGICS` in `modules/sdk/karrio/core/utils/helpers.py`, with content-type and config fallbacks; verify unit tests cover PDF, ZPL, PNG, and adversarial bytes
- [x] 1.3 Add `StampPlacement` and `StampRequest` models in a new `modules/sdk/karrio/core/utils/stamping.py`; verify millimetre-to-points conversion (bottom-left flip) with a unit test
- [x] 1.4 Implement the PDF backend (Pillow single-page image PDF → pypdf `merge_transformed_page` with scale/translate `Transformation`), honoring the Q6 flattening outcome and the overlay/underlay layer; verify a round-trip test asserts preserved format, page count, and AcroForm survival
- [x] 1.5 Implement `lib.stamp_document` dispatch (sniff → backend, consumer-placement precedence, registry-miss error, explicit PNG rejection) and re-export from `modules/sdk/karrio/lib.py`; verify the spec scenarios pass, including PNG rejection and registry-miss error
- [x] 1.6 Run the SDK suite to confirm no regression: `python -m unittest discover -v -f modules/sdk/tests`

## 2. Launch — documentation

- [x] 2.1 Publish a consumer workflow guide (per-carrier, with the FedEx ETD precedent comparison table and the D8 responsibility boundary) following the repo guide conventions; verify it renders and links from the SDK guide index

## 3. Follow-up (P1) — ZPL backend

- [x] 3.1 Implement the ZPL backend (flatten onto white, Floyd–Steinberg dither, 1-bpp GRF hex with byte-padded rows, `^FO/^Gfa` splice into the carrier field stream); verify GRF golden-vector tests match exact hex and dither snapshot tests hold stroke continuity at 203 and 300 dpi
- [x] 3.2 Add the `~DY`/`^XG` send-once-per-printer cache variant behind an opt-in path; verify the default `^Gfa` path is unaffected when caching is off

## 4. Follow-up (P1) — optional registry seeds

- [x] 4.1 Extend the shipped three-part registry key (carrier, category, format) with the paper-variant segment and add the registry structure with `ShippingDocumentCategory` normalization and a per-seed revision field; verify key hit, miss, and category-normalization resolution tests
- [x] 4.2 Register the measured PostNord CN22 seed for the A4 paper variant (depends on 4.1): key `postnord/cn22/PDF/A4` once 4.1's paper-variant segment is in place, otherwise the three-part `postnord/cn22/PDF`; anchor x 53.3–61.0 mm, y 91.4–140.5 mm, rotation approximately 90 degrees, date-then-signature layout, from the `cn22_original-1.png` provenance in design.md; verify a fixture stamps a date + signature at the seeded anchor and confirms the ~90-degree rotation direction against the probe2b render (Q10). Supersedes the prior "measure against a live printout" framing now that the anchor is measured. Implemented with `revision=1`; the CW/CCW direction stays provisional because the probe render is not vendored (Q10 open), and the per-seed revision field is the supersession lever for a later live-render confirmation.
- [x] 4.3 (dropped) Add the FedEx commercial invoice (PDF, letter) seed. Descoped: FedEx commercial-invoice stamping is already served by FedEx's Electronic Trade Documents (ETD) flow, an untouched precedent (PRD D9 — the consumer-generated-CI path "needs nothing from karrio"). No measured anchor or fixture exists, so seeding one would duplicate a solved capability with unmeasured data; the registry stays open for a measured seed if a real need surfaces.

## 5. Deferred — server exposure (gated on Q7)

- [x] 5.1 Run the Q7 precedent survey for generalized server surfaces over SDK utilities; record findings in `docs/notes/` and decide go/no-go before any build. Findings in `docs/notes/documents/stamping-server-precedent-survey.md`: precedent is unqualified — `modules/documents/` already exposes a generalized server surface over an SDK document utility (`DocumentGenerator.post`, `POST /documents/generate`), so a stamping endpoint is a near-copy swapping weasyprint for `lib.stamp_document`. Survey recommends GO; the build (5.2) is a net-new API surface and so is gated on a PRD per the project PRD-first rule and on explicit user go-ahead.
- [ ] 5.2 (deferred) If precedent holds, build the documents-module pipeline in `modules/documents/karrio/documents/`; verify against a server fixture. PRD written at `PRDs/DOCUMENT_STAMPING_SERVER_ENDPOINT.md` (the endpoint wraps `lib.stamp_document` mirroring `POST /documents/generate`, not a new weasyprint pipeline). Decisions resolved 2026-09-22: REST-only at launch (Q1/D1), base64-in only with no stored-document/org-scoped variant at launch (Q2/D4), synchronous (D3); Q3 payload ceiling and Q4 registry-miss status code left for the build phase. Build DEFERRED by user decision — awaits an explicit go.

## 6. Follow-up (P1) — placement rotation and consumer-supplied date stamp

- [x] 6.1 Add a `rotation` field (degrees clockwise, default `0`) to `StampPlacement` and apply it in `stamp_pdf` by composing `pypdf.Transformation().rotate(...)` with the existing scale/translate chain; verify a rotated-overlay test asserts the image aligns with a sideways field at 90 degrees and that a `0`-degree placement is unchanged from the current upright behavior
- [x] 6.2 Add consumer-supplied date rendering: render a caller-supplied pre-formatted date string to a small image with Pillow and composite it preceding the signature within the placement at the same rotation, threading the date value through `stamp_document` / `StampRequest`; verify a date-present test asserts both the date text and the signature appear at the anchor with the date preceding the signature and sharing its rotation, and a date-absent test asserts only the signature is composited (backward compatible)
