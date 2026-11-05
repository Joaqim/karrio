# Tasks

## 1. Branch setup

- [x] 1.1 Create worktree `.worktrees/fix-dashboard-address-template-fields` on a new branch `fix-dashboard-address-template-fields` from `upstream/main` with `git -c submodule.recurse=false worktree add`, and verify HEAD equals `upstream/main`
- [x] 1.2 On docs-openspec, add `fix-dashboard-address-template-fields` to `BRANCHES` in `docs/notes/workflow/assemble-develop.sh` after `fix-dashboard-carrier-options`, update the branch listing in `develop-assembly.md`, commit, and verify `develop-status.sh` lists the branch as not yet contained

## 2. Shared helpers

- [x] 2.1 Move `extractAddressFromTemplate` and `extractParcelFromTemplate` into `packages/lib/helper.ts` as exports with their current field lists, import them in `addresses-management.tsx` and `parcels-management.tsx`, and verify `npx tsc --noEmit -p packages/ui` reports no new errors compared with `upstream/main` and `npx eslint` passes on the changed files
- [x] 2.2 Commit as `refactor(dashboard): share address and parcel template field helpers`

## 3. Selection and seeding

- [x] 3.1 In `packages/ui/components/address-combobox.tsx`, pass `extractAddressFromTemplate(template.address)` to `onValueChange` in `handleTemplateSelect`, and verify with `tsc` and `eslint` as in 2.1
- [x] 3.2 In `packages/core/modules/Shipments/create_label.tsx` `setInitialData`, seed `shipper` and `parcel` through the helpers so tax ids are assigned to a new object, and verify with `eslint` on the file and `tsc --noEmit -p packages/ui` (do not run `tsc` in `packages/core`, whose tracked `tsconfig.tsbuildinfo` would change)
- [x] 3.3 Commit as `fix(dashboard): copy only address and parcel fields from templates`

## 4. Integration checks

- [x] 4.1 Reassemble develop-next with `assemble-develop.sh -r /home/joaqim/projects/karrio -f`, verify no conflicts, and run `npm run build` for the dashboard (or the narrowest turbo build covering `apps/dashboard`) on develop-next
- [ ] 4.2 Push the branch, then after the user deploys develop, run the reproduction on dev (saved draft, Edit shipper address, pick "Hisingen" from the name suggestions, save) and verify the update succeeds, the request payload has no `object_type`, and the shipper keeps its own id; check a new draft seeded from the default templates carries no template `id` or `meta`
- [ ] 4.3 Open the upstream pull request against `karrioapi/karrio` `main` titled `fix(dashboard): copy only address and parcel fields from templates`, with the Fix PR body (Bug, Root Cause, Fix, Tests), after the user confirms 4.2
