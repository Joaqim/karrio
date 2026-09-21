## 1. Launch — SDK core utility (PDF)

- [x] 1.1 Run the Q6 alpha spike: save a real CN22 signature PNG as a Pillow image PDF and inspect whether RGBA alpha survives as an SMask; record the outcome (true alpha vs. white-flatten fallback) in design.md before finalizing the backend
- [x] 1.2 Add a shared magic-byte sniff helper generalizing DHL Freight Sweden `LABEL_MAGICS` in `modules/sdk/karrio/core/utils/helpers.py`, with content-type and config fallbacks; verify unit tests cover PDF, ZPL, PNG, and adversarial bytes
- [ ] 1.3 Add `StampPlacement` and `StampRequest` models in a new `modules/sdk/karrio/core/utils/stamping.py`; verify millimetre-to-points conversion (bottom-left flip) with a unit test
- [ ] 1.4 Implement the PDF backend (Pillow single-page image PDF → pypdf `merge_transformed_page` with scale/translate `Transformation`), honoring the Q6 flattening outcome and the overlay/underlay layer; verify a round-trip test asserts preserved format, page count, and AcroForm survival
- [ ] 1.5 Implement `lib.stamp_document` dispatch (sniff → backend, consumer-placement precedence, registry-miss error, explicit PNG rejection) and re-export from `modules/sdk/karrio/lib.py`; verify the spec scenarios pass, including PNG rejection and registry-miss error
- [ ] 1.6 Run the SDK suite to confirm no regression: `python -m unittest discover -v -f modules/sdk/tests`

## 2. Launch — documentation

- [ ] 2.1 Publish a consumer workflow guide (per-carrier, with the FedEx ETD precedent comparison table and the D8 responsibility boundary) following the repo guide conventions; verify it renders and links from the SDK guide index

## 3. Follow-up (P1) — ZPL backend

- [ ] 3.1 Implement the ZPL backend (flatten onto white, Floyd–Steinberg dither, 1-bpp GRF hex with byte-padded rows, `^FO/^Gfa` splice into the carrier field stream); verify GRF golden-vector tests match exact hex and dither snapshot tests hold stroke continuity at 203 and 300 dpi
- [ ] 3.2 Add the `~DY`/`^XG` send-once-per-printer cache variant behind an opt-in path; verify the default `^Gfa` path is unaffected when caching is off

## 4. Follow-up (P1) — optional registry seeds

- [ ] 4.1 Add the registry structure with `ShippingDocumentCategory` normalization and a per-seed revision field; verify key hit, miss, and category-normalization resolution tests
- [ ] 4.2 Measure and add the PostNord CN22 (PDF, A4) seed against a live printout; verify a fixture stamps at the seeded anchor
- [ ] 4.3 Add the FedEx commercial invoice (PDF, letter) seed; verify a fixture stamps at the seeded anchor

## 5. Deferred — server exposure (gated on Q7)

- [ ] 5.1 Run the Q7 precedent survey for generalized server surfaces over SDK utilities; record findings in `docs/notes/` and decide go/no-go before any build
- [ ] 5.2 If precedent holds, build the documents-module pipeline (weasyprint HTML overlay → PDF → pypdf merge, no new deps) in `modules/documents/karrio/documents/`; verify against a server fixture
