## Context

Address templates are loaded by `GET_ADDRESSES` and `GET_DEFAULT_TEMPLATES` (`packages/types/graphql/queries.ts`) with `id`, `object_type` and `meta` alongside the address fields.
`AddressCombobox` (`packages/ui/components/address-combobox.tsx:101-103`) hands the raw template to `onValueChange`, and the older `AddressForm` (`packages/ui/core/forms/address-form.tsx:47-48`) merges it with `{...state, ...value}`.
For a saved draft, `label-data.ts` then sends the address to `partial_shipment_update`, whose `UpdateAddressInput` (`modules/graph/karrio/server/graph/schemas/base/inputs.py:417-438`) requires `id` and accepts `meta` and `validate_location` but not `object_type`.
Server-side, the update deep-merges into the shipment's address JSON (`json_utils.py`), so a template `id` never touches the template record; it only replaces the shipment address id.
`create_label.tsx:203-208` seeds new drafts from `default_address` and `default_parcel` by reference, and then assigns workspace tax ids onto that same object.
`addresses-management.tsx:49-53` and `parcels-management.tsx:44-48` already strip template metadata with private helpers.

## Goals / Non-Goals

**Goals:**

- Template metadata never reaches a shipment or manifest address or parcel through template selection or default seeding.

**Non-Goals:**

- Filtering mutation payloads in `label-data.ts` or `bulk-shipments.ts` against the GraphQL input types.
- The newer `AddressForm`, `ParcelForm` and commodity dialogs, which already copy named fields.
- `createShipmentFromOrders`, which reads a template shape the query no longer returns (see proposal).

## Decisions

### Shared helpers in `@karrio/lib`

`extractAddressFromTemplate` and `extractParcelFromTemplate` move from the two management components to `packages/lib/helper.ts` with the same names and field lists, and the components import them.
Keeping the names keeps the diff in the management components to import changes, and `@karrio/lib` is already imported by `address-combobox.tsx` and `create_label.tsx`.
The helpers return a new object and accept `null` or `undefined`, returning an empty object, as the private versions do.

Alternative considered: a single generic `omitTemplateFields`; rejected because address and parcel templates strip different fields (`validate_location` is address-only), and two named helpers read better at the call sites.

### Strip at the selection and seeding sites

`AddressCombobox.handleTemplateSelect` passes `extractAddressFromTemplate(template.address)` to `onValueChange`, which covers every editor built on the combobox, including the manifest modal.
`create_label.tsx` seeds `shipper` and `parcel` through the helpers, falling back to `{}` and `DEFAULT_PARCEL_CONTENT` as today; because the helpers return new objects, the later tax id assignments no longer write into the cached template.

Alternative considered: filtering in the mutation hooks (option B in the investigation); rejected for this change because it needs a field list maintained against the GraphQL schema, and it would still let a template `id` replace the shipment address id.

### The shipment keeps its own address id

Stripping `id` at selection leaves the form's existing `id` in place, so a saved draft's shipper keeps its id and `UpdateAddressInput`'s required `id` is still sent.
A new draft's seeded shipper has no id, which is what REST `shipments.create` expects.

## Risks / Trade-offs

- [Another component spreads a template into a mutation later] → the shared helper is the documented path; a hook-level filter remains possible as a follow-up.
- [No automated dashboard tests exist] → verification is `tsc --noEmit`, `eslint`, and a browser check of the reproduction steps; see tasks.
- [Drafts saved before the fix keep a template id and `meta` on their addresses] → harmless: the server treats them as shipment JSON, and the next edit keeps them unless the user changes them; no migration.

## Migration Plan

Ship on a new branch from `upstream/main`, add it to `BRANCHES` after `fix-dashboard-carrier-options` (which also changes `create_label.tsx`), reassemble develop, and open the upstream pull request after the user has checked the flow on dev.
