# PostNord EORI/VAT fallback session checkpoint

Handoff for the session that created the `postnord-eori-vat-fallback` openspec change on 2026-09-29.
The next session should be able to self-direct from this note plus the change directory itself.

## State estimate (2026-09-29)

What was done: ran `/opsx:ff` end to end; research subagent swept the postnord connector and cross-connector EORI/VAT conventions; all four artifacts (proposal, spec delta, design, tasks) were written, validated, and committed as `35910cd2e` on `docs-openspec`; the feature branch `feat-postnord-eori-vat-fallback` was created at `.worktrees/feat-postnord-eori-vat-fallback` from `fix-postnord-eu-vat-territories` (verified ancestor of both earlier postnord lines), registered in `BRANCHES` as `509947a6c`, and `develop` was rebuilt to `967aa65db` containing all 20 branch tips.

What was learned: `ComputedAddress.tax_id` folds `federal_tax_id or state_tax_id`, so today a state-only shipper's value already reaches the invoice `vatNo` (`shipment/create.py:627`, core `units.py:1604`); no karrio connector sources EORI from an address field, making this change the first (dpd's option-then-address `vatNumber` is the nearest precedent); the user decided strict `federal_tax_id` for seller `vatNo` and the `state_tax_id` EORI fallback on both the CN22 and invoice branches plus the guard.

What remains: implementation landed 2026-09-29 on `feat-postnord-eori-vat-fallback` (now commits `5efa6d704`..`eeb52afa1` after the rebase onto `fix-postnord-customs-line-content` and the two review follow-up tests; the postnord suite is 239 OK), the fresh-context review passed (APPROVED, no blockers) with both nits closed by follow-up tests, and the change is archived as `2026-09-29-postnord-eori-vat-fallback` with the main `postnord/customs-declaration` spec updated (52 scenarios; 56 after the sibling archive). Only pushes remain, sanctioned and executed in the 2026-09-29 close-out.

Downstream impact: the `fix-postnord-customs-line-content` change edits the same `shipment/create.py` sites; its spec delta turned out to be an ADDED requirement rather than a MODIFIED block, so archiving it after this change (done 2026-09-29 as `2026-09-29-fix-postnord-customs-line-content`) applied additively — the earlier MODIFIED-block rebase concern was overstated. The code-side conflict was resolved 2026-09-29 by rebasing this branch onto it (both shared base `71aec8b61`; one two-line hunk in `_customs_declaration`), so the develop assembly skips line-content as already contained.

## Surprises

Accumulated surprise stayed low: no replanning trigger fired.
The `tax_id` fold was a moderate divergence from the presumed clean federal/state split and was resolved by the user's strict-federal decision rather than a design change.

## Confidence

The change sits at implementation confidence: the full postnord suite passes from the feature worktree (230 OK, 5 new tests) with the worktree pinned ahead of the main checkout on `PYTHONPATH`, and the production diff matches the design decisions point for point.
The fresh-context review gate passed 2026-09-29 with verdict APPROVED, no blockers, and two non-blocking nits recorded as optional follow-ups.

## Next session

Recommended entry: none outstanding — both postnord changes are archived, the review follow-ups landed (`cb6871b53`, `eeb52afa1`), and the pushes were sanctioned for the 2026-09-29 close-out; verify the end state with `develop-status.sh --fetch`.
Push state: `origin/develop` last matched everything at `bf66a14a6`; since then docs-openspec collected the `BRANCHES`-order swap, checkpoint refreshes, and task ticks, the feature branch collected the seven implementation commits and was rebased onto `fix-postnord-customs-line-content` (`5efa6d704`..`7cb95d1c6`, still a fast-forward push over its origin counterpart), and `develop` was rebuilt locally to `c5c83c3e2` before the archive and again after it — unpushed until the 2026-09-29 close-out, when the user sanctioned the three pushes (feature branch and docs-openspec as fast-forwards, develop as the dev-deploying force-with-lease).
Run `develop-status.sh --fetch` for the current tip before acting.
