# Tasks

## 1. Worktree setup

- [x] 1.1 Create `.worktrees/feat-postnord-eori-vat-fallback` with an explicit start point at the latest postnord connector branch tip per the `BRANCHES` list in `assemble-develop.sh` (never from generated `develop` directly), and register the branch in `BRANCHES` on `docs-openspec` per the fork workflow; verify `develop-status.sh --fetch` lists the new branch and `rebuild-develop.sh` succeeds.

## 2. EORI resolution helper and CN22 branch

- [ ] 2.1 Add a shared EORI resolution helper in `modules/connectors/postnord/karrio/providers/postnord/units.py`, next to `enforce_cn22_registration_numbers` (customs option `eori_number` first, `shipper.state_tax_id` second), make the guard consume it, and update the guard's error message to name the shipper state tax identifier fallback; verify by extending `test_create_shipment_customs_registration_numbers_empty_reject` in `tests/postnord/test_shipment.py` (no registration options, no `state_tax_id`) to assert the updated `customs.options` field-error text and that no request is sent.
- [ ] 2.2 Wire the helper into the CN22 payload site (`EORIorPersonalIdNumber` in `shipment/create.py`), replacing the options-only read; verify with a new CN22 fixture whose shipper carries `state_tax_id` while customs options omit `eori_number` — a new test asserts the built request's EORI field equals the state value, and a precedence case with both sources asserts the option value wins.
- [ ] 2.3 Update the registration-number decision rows in `PRDs/PRD_POSTNORD_INTEGRATION.md` (D21/D22 and the requirements-table row) to record the address fallback and its precedence; verify the rows state the new resolution rule without contradicting the specs delta.

## 3. Customs invoice branch

- [ ] 3.1 Wire the same helper into the invoice seller `eoriNo` in `shipment/create.py`, keeping customs-option precedence; verify with a new invoice fixture carrying `state_tax_id` and no `eori_number` option — the test asserts `invoice["seller"]["eoriNo"]` equals the state value.
- [ ] 3.2 Change seller `vatNo` to `shipper.federal_tax_id` and tighten the VAT requirement in `_customs_invoice_errors` to fail on a missing federal tax identifier alone; verify with a new test where only `state_tax_id` is set — the booking fails with the `shipper.federal_tax_id` field error and no request is sent — and the existing `test_..._without_seller_vat_number` still passes.

## 4. Guard relaxation and regression

- [ ] 4.1 Cover the relaxed guard end to end: a CN22 booking with no registration-number options but a shipper `state_tax_id` builds without field errors and the request carries the state value as EORI; verify with a new test mirroring the spec scenario "CN22 registration guard is satisfied by the shipper state tax identifier".
- [ ] 4.2 Run the full postnord connector suite from the feature worktree with the worktree pinned ahead of the main checkout on `PYTHONPATH` (fork venv pinning hazard — unpinned runs silently exercise the main checkout's provider code): `python -m unittest discover -v -f modules/connectors/postnord/tests`; verify every test passes, including the untouched suites (`TestPostNordCustomsDocument`, `TestPostNordEUVATArea`, `TestPostNordProductGroups`).
