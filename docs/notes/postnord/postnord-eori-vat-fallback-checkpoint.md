# PostNord EORI/VAT fallback session checkpoint

Handoff for the session that created the `postnord-eori-vat-fallback` openspec change on 2026-09-29.
The next session should be able to self-direct from this note plus the change directory itself.

## State estimate (2026-09-29)

What was done: ran `/opsx:ff` end to end; research subagent swept the postnord connector and cross-connector EORI/VAT conventions; all four artifacts (proposal, spec delta, design, tasks) were written, validated, and committed as `35910cd2e` on `docs-openspec`; the feature branch `feat-postnord-eori-vat-fallback` was created at `.worktrees/feat-postnord-eori-vat-fallback` from `fix-postnord-eu-vat-territories` (verified ancestor of both earlier postnord lines), registered in `BRANCHES` as `509947a6c`, and `develop` was rebuilt to `967aa65db` containing all 20 branch tips.

What was learned: `ComputedAddress.tax_id` folds `federal_tax_id or state_tax_id`, so today a state-only shipper's value already reaches the invoice `vatNo` (`shipment/create.py:627`, core `units.py:1604`); no karrio connector sources EORI from an address field, making this change the first (dpd's option-then-address `vatNumber` is the nearest precedent); the user decided strict `federal_tax_id` for seller `vatNo` and the `state_tax_id` EORI fallback on both the CN22 and invoice branches plus the guard.

What remains: implementation, all 8 tasks in the change's `tasks.md` are open; run `/opsx:apply` against the feature worktree; `openspec archive` is deliberately deferred until tasks complete, because archive applies the spec delta to the main `postnord/customs-declaration` corpus.

Downstream impact: the `fix-postnord-customs-line-content` change modifies the same requirement "Customs data is declared at booking time" and the same `shipment/create.py` sites; it is complete but unarchived, so whichever change archives second must rebase its MODIFIED block on the other's archived text, and whichever branch lands second in the develop assembly may need a small rebase. Sequence the two archives rather than running them concurrently.

## Surprises

Accumulated surprise stayed low: no replanning trigger fired.
The `tax_id` fold was a moderate divergence from the presumed clean federal/state split and was resolved by the user's strict-federal decision rather than a design change.

## Confidence

The change sits at proposal confidence: the spec delta passes `openspec validate`, and every code claim is anchored to `file:line` from the research pass, but no implementation evidence exists yet.
Task 4.2's full postnord suite run is the first promotion gate, and the fork's worktree venv pinning hazard applies to it (`PYTHONPATH` must pin the feature worktree ahead of the main checkout).

## Next session

Recommended entry: `/opsx:apply` on `postnord-eori-vat-fallback` from `.worktrees/feat-postnord-eori-vat-fallback`; task 1.1 (worktree, registration, rebuild verification) is already done and only needs its checkbox ticked after verification.
Alternative entry: watch for the two parallel changes to land first, then apply with a current base.
Every ref was pushed at close-out verification (`origin/develop` at `bf66a14a6`, all branches equal to their origin counterparts); the `BRANCHES`-ordering tidy afterwards regenerated `develop` locally, and pushing the regenerated develop — the dev-deploying push — remains the user's call.
Run `develop-status.sh --fetch` for the current tip before acting.
