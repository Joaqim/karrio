# PostNord EORI/VAT fallback session checkpoint

Handoff for the session that created the `postnord-eori-vat-fallback` openspec change on 2026-09-29.
The next session should be able to self-direct from this note plus the change directory itself.

## State estimate (2026-09-29)

What was done: ran `/opsx:ff` end to end; research subagent swept the postnord connector and cross-connector EORI/VAT conventions; all four artifacts (proposal, spec delta, design, tasks) were written, validated, and committed as `35910cd2e` on `docs-openspec`; the feature branch `feat-postnord-eori-vat-fallback` was created at `.worktrees/feat-postnord-eori-vat-fallback` from `fix-postnord-eu-vat-territories` (verified ancestor of both earlier postnord lines), registered in `BRANCHES` as `509947a6c`, and `develop` was rebuilt to `967aa65db` containing all 20 branch tips.

What was learned: `ComputedAddress.tax_id` folds `federal_tax_id or state_tax_id`, so today a state-only shipper's value already reaches the invoice `vatNo` (`shipment/create.py:627`, core `units.py:1604`); no karrio connector sources EORI from an address field, making this change the first (dpd's option-then-address `vatNumber` is the nearest precedent); the user decided strict `federal_tax_id` for seller `vatNo` and the `state_tax_id` EORI fallback on both the CN22 and invoice branches plus the guard.

What remains: implementation landed 2026-09-29 on `feat-postnord-eori-vat-fallback` (commits `3ffa686ce`..`1eb3f35ff`, full postnord suite 230 OK with 5 new tests), and all 8 tasks in the change's `tasks.md` are ticked; the fresh-context review gate and `openspec archive` are pending, with archive applying the spec delta to the main `postnord/customs-declaration` corpus.

Downstream impact: the `fix-postnord-customs-line-content` change modifies the same requirement "Customs data is declared at booking time" and the same `shipment/create.py` sites; it is complete but unarchived, so whichever change archives second must rebase its MODIFIED block on the other's archived text, and whichever branch lands second in the develop assembly may need a small rebase. Sequence the two archives rather than running them concurrently.

## Surprises

Accumulated surprise stayed low: no replanning trigger fired.
The `tax_id` fold was a moderate divergence from the presumed clean federal/state split and was resolved by the user's strict-federal decision rather than a design change.

## Confidence

The change sits at implementation confidence: the full postnord suite passes from the feature worktree (230 OK, 5 new tests) with the worktree pinned ahead of the main checkout on `PYTHONPATH`, and the production diff matches the design decisions point for point.
The fresh-context review gate has not run yet; it is the next promotion step before archive.

## Next session

Recommended entry: fresh-context review of `feat-postnord-eori-vat-fallback` against the change artifacts and `PRDs/PRD_POSTNORD_INTEGRATION.md` (the repo's review gate), then `/opsx:archive` sequenced against `fix-postnord-customs-line-content`.
Push state: `origin/develop` last matched everything at `bf66a14a6`; since then docs-openspec collected the `BRANCHES`-order swap, checkpoint refreshes, and task ticks, the feature branch collected the seven implementation commits (`3ffa686ce`..`1eb3f35ff`), and `develop` was rebuilt locally to `c5c83c3e2` — none of it pushed, and pushing (including the dev-deploying develop force-with-lease) is the user's call.
Run `develop-status.sh --fetch` for the current tip before acting.
