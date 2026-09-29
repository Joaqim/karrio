# Tasks

## 1. Branch setup

- [ ] 1.1 Create worktree `.worktrees/fix-postnord-customs-line-content` on a new branch `fix-postnord-customs-line-content` from `fix-postnord-eu-vat-territories` with `git -c submodule.recurse=false worktree add`, and verify HEAD equals `fix-postnord-eu-vat-territories`

## 2. Goods description check

- [ ] 2.1 Add `enforce_customs_line_content` to `modules/connectors/postnord/karrio/providers/postnord/units.py` and call it where the CN22 declaration and the customs invoice are assembled in `shipment/create.py` (and any other path that builds declaration lines), per design.md
- [ ] 2.2 Add connector tests for every scenario of the `postnord/customs-declaration` delta (CN22 index 0 rejected with no request sent, customs invoice index 1 rejected, description used when title empty, SE to PL not checked), and verify they fail before 2.1 and pass after with `python -m unittest discover -v -f modules/connectors/postnord/tests` in the nix dev shell from the worktree
- [ ] 2.3 Commit as `fix(postnord): reject customs lines without a goods description`

## 3. Error messages

- [ ] 3.1 Add `faultReferences` to the fault objects in `modules/connectors/postnord/schemas/shipment_response.json`, run `./bin/run-generate-on modules/connectors/postnord`, and verify the suite no longer prints "unknown arguments" for `faultReferences`; commit as `fix(postnord): declare fault references in the shipment response schema`
- [ ] 3.2 Add the subtype hint table and `details.summary` to `error.py` per design.md, listing in the commit body the evidence (spec path or fixture) for each hinted subtype
- [ ] 3.3 Add tests for every scenario of `postnord/error-messages` using the SE to CA fault captured in proposal.md as a fixture, update existing error fixtures whose expected messages or details change, verify red before 3.2 and green after, and commit as `fix(postnord): name the field to correct in known fault messages`

## 4. Integration

- [ ] 4.1 Run the PostNord suite and `./bin/run-sdk-tests` scope used by `rebuild-develop.sh` for the branch, and verify all pass
- [ ] 4.2 Push the branch, add it to `BRANCHES` after `fix-postnord-eu-vat-territories` on docs-openspec with the `develop-assembly.md` listing, commit, run `rebuild-develop.sh -r /home/joaqim/projects/karrio`, and verify it promotes local develop; leave the develop push to the user
