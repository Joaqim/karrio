---
title: Connector impact of fix-core-pickup-shipment-ids
---

# Connector impact of fix-core-pickup-shipment-ids

Notes for upstream draft pull request #1149 from branch `fix-core-pickup-shipment-ids` (commits `a9ec855d2` and `2013eef17`, based on `upstream/main` at `deea10f85`).

## Change summary

The manager pickup serializer now populates the top-level `PickupRequest.shipment_identifiers` with the linked shipments' identifiers, which it previously sent only in `options["shipment_identifiers"]`.
It also forwards the linked shipments' `tracking_number` plus `meta.tracking_numbers` as `options["tracking_numbers"]`.
Both lists are ordered and deduplicated, with empty values dropped.
On update, the linked shipments default to the pickup's own shipments when the request carries no `tracking_numbers`, for the identifiers, tracking numbers, and `billing_number` alike.
The computed keys take precedence over keys spread from the pickup's `meta`.
The gateway drops `shipment_identifiers` when building the `Pickup` response datatype, which has no such field.

## Connector behaviour changes

Connectors were not modified; the following behaviour changes follow from the server change alone.

| Connector | Location | Before | After |
|---|---|---|---|
| dpd_meta | `pickup/create.py:85` | `shipmentNumbers` was `None` | `shipmentNumbers` carries the linked shipments' identifiers |
| teleship | `pickup/schedule.py:48` | `shipmentIds` was `[]` | `shipmentIds` carries the linked shipments' identifiers |
| easyship (community) | `pickup/update.py:73` | update read `options.shipment_identifiers` as `[]` | update reads the pickup's linked shipments' identifiers |
| dhl_parcel_de | `pickup/create.py:198` | a shipment without `shipment_identifier` or meta identifiers produced `[None]`, which is truthy, so `len(packages)` shipment entries were sent | the list is `[]`, so one shipment entry is sent |

No connector reads `options["tracking_numbers"]` for pickups, and no connector writes `shipment_identifiers`, `tracking_numbers`, or `billing_number` into pickup response meta.

## Open verification

Whether dpd_meta `shipmentNumbers` accepts karrio shipment identifiers is unverified; draft pull request #1149 carries this, and the teleship question below, as an open question for upstream review.
The dpd_meta shipment mapper stores `shipment.shipmentId` as `shipment_identifier` (`shipment/create.py:57`), and it is not yet confirmed against the DPD META-API specification that the pickup endpoint's `shipmentNumbers` expects that value rather than a different shipment or parcel number.
Teleship stores `shipment.shipmentId` likewise (`shipment/create.py:68`) and sends it as `shipmentIds`, which matches by name but is also unverified against the API.
