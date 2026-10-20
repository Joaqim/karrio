## Why

Editing an address on a saved shipment draft fails when an address template is picked from the name field's suggestions:

```
Variable '$data' got invalid value {..., 'object_type': 'address', 'meta': {...}} at 'data.shipper'; Field 'object_type' is not defined by type 'UpdateAddressInput'.
```

`AddressCombobox.handleTemplateSelect` passes the whole template record to the address form, which spreads it over the shipment address, so the template's `id`, `object_type` and `meta` travel to `partial_shipment_update`.
The same spreading happens when `create_label.tsx` seeds a new draft from the default address and parcel templates; those drafts are saved over REST, which drops unknown fields, so nothing errors, but the template's `id` and `meta` (including `is_default`) are stored on the shipment.
The affected files are identical on `upstream/main`, and no upstream issue or pull request covers them.

## What Changes

- Add shared helpers to `@karrio/lib` that return only the address fields of an address template and only the parcel fields of a parcel template, dropping `id`, `object_type`, `meta`, `label`, `is_default`, `validate_location` and timestamps.
- Apply the address helper when a template is picked in `AddressCombobox`, which serves the shipper, recipient and return address editors on the shipment, order and bulk label pages and the manifest address.
- Apply both helpers when `create_label.tsx` seeds a new draft from the default templates, which also stops the seeding from writing tax ids into the cached template object.
- Point the private copies in `addresses-management.tsx` and `parcels-management.tsx` at the shared helpers.

## Capabilities

### New Capabilities

- `dashboard/address-templates`: how the dashboard copies address and parcel templates into shipment and manifest addresses and parcels.

### Modified Capabilities

None.

## Impact

- Code: `packages/lib/helper.ts`, `packages/ui/components/address-combobox.tsx`, `packages/core/modules/Shipments/create_label.tsx`, `packages/ui/components/addresses-management.tsx`, `packages/ui/components/parcels-management.tsx`.
- API: no server or GraphQL schema change; `partial_shipment_update` receives only fields `UpdateAddressInput` declares, and shipments keep their own address ids.
- Upstream: a `fix(dashboard)` pull request from a new fork branch `fix-dashboard-address-template-fields` on `upstream/main`.
- Fork: the branch is added to `BRANCHES` in `assemble-develop.sh`.
- Out of scope: `createShipmentFromOrders` in `packages/lib/helper.ts` reads `default_address.address` and `default_parcel.parcel`, which the flat template query no longer returns, so shipments created from orders never receive the default shipper or parcel; that is a separate fix.
