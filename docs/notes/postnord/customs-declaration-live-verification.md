# PostNord customs declaration — live verification findings

Record of the live verification rounds for the `postnord-customs-declaration` OpenSpec change (task 5.2), all run on 2026-09-21.
Sandbox evidence comes from `openspec/changes/postnord-customs-declaration/verify_live.py` against the `atapi2` test host with test-mode bookings (`testIndicator=true`).
Production evidence comes from `verify_prod_probe.py` in the same directory against `api2.postnord.com`, on the real booking UX478114854SE — an SE→PL export letter booked as `postnord_export_letter` (`UX`), printId `87a6d74f58854bc1b8be5481ec47f803`, bookingId `ILPN001AVCW2ZHSWRWXUQZRKWOXQXQ`.
Credentials are referenced by environment variable name only (`POSTNORD_APIKEY` for the sandbox key; `POSTNORD_LIVE_APIKEY` and `POSTNORD_EORI` for production); no key or EORI value appears in this note or in the probe output.

## Sandbox: environment limits

The apikey probe (scenario 0, servicepoints byaddress) passes, isolating key and environment problems from the customs paths.

Test-mode bookings never propagate to the downstream print and declaration subsystems.
The by-id fetch returns per-id FAIL `id not found`, and the declaration POST returns:

```
{"message":"General client indata error","compositeFault":{"faults":[{"explanationText":"Unable to find EDI: UX304478491SE","faultCode":"SAO-BR-24041806"}]}}
```

The same responses at t+0 and at t+5 minutes rule out propagation delay: this is an environment limitation, not timing.
The consequence is a hard scope boundary — the sandbox can verify booking-time carriage and the local guard, but never standalone-document retrieval or declaration success.

## Booking-time carriage and the line-limit guard

Booking-time CN22 without a sender registration number is rejected with `SACUS-BR-24062502`, "Customs CN22/CN23 should have either EORI, VOEC, IOSS".
With `customs.options.eori_number` threaded (task 2.4), bookings succeed — three created across the scenarios — and `meta.printout_composition` reports `['cn22', 'label']`: the CN22 is composed into the booking printout.

A 14-line customs payload is rejected by the local `CUSTOMS_DECLARATION_MAX_LINES = 13` guard as a field error before any HTTP call (scenario C PASS), matching design D5's pre-submission stance.

## Production id taxonomy

A live A/B on the same real booking settles which id each surface keys on:

| Surface | Key | Live evidence |
|---|---|---|
| `/v3/labels/ids/{pdf,zpl}` | `printId` | item id → per-id FAIL `id not found`; printId → OK |
| `/v3/customs/declaration` | waybill (item id) with `idType` | request `itemId` camelCase accepted; response echoes `ITEMID` uppercase |
| shipment references | bookingId | rides as `referenceType: "IL"` |

The by-id result confirms the vendored swagger's `assignedIds.printId` description ("The printId is use to print the label, in the endpoints /v3/labels/ids/(zpl|pdf)") over the item-id-shaped request examples.
On by-id responses, `itemIds[].reference` is the references object — `{"item": [], "shipment": [{"referenceNo": ..., "referenceType": ...}]}` — matching the swagger `$ref`, not a string.

## Post-booking declaration

The post-booking declaration POST (`/v3/customs/declaration`) is rejected when the CN22 carries no registration number: `SACUS-BR-24062502` spans the post-booking endpoint, not only booking.
With the EORI threaded, the declaration is accepted.
Intra-EU SE→PL is not rejected as not-applicable on this account.
The success envelope is the bare `bookingResponseCN`, with no wrapper:

```
{"bookingId":"ILPN001AWXGPXVKFSFVQLLPLIEAJVV","idInformation":[{"ids":[{"idType":"ITEMID","value":"UX478114854SE","printId":"87a6d74f58854bc1b8be5481ec47f803"}],"status":"OK"}]}
```

This live-confirms the shape-tolerant parser fix (6e92b6dcb): the pre-fix code would have silently parsed this envelope to None.

## Standalone retrieval

After the declaration exists, the by-id fetch restricted with `onlyCustomsDeclarations` and keyed by printId returns composition `{'cn22': 1}` with a real PDF — 16,748 base64 characters, `%PDF-` magic.
The unrestricted by-id fetch returns `{'label': 1, 'cn22': 1}` (23,132 characters): the booking printout composes label + CN22, live-confirming the duplication design D2 accepted, and `definePrintout=onlyLabels` remains the documented future lever.

## Re-declaration and rendered documents

A further live round re-declared the same item with a realistic one-line merchandise CN22 ("Candy", HS 1704906500, EUR 30, 0.51 KG gross) using `updateIndicator: "Update"` over the earlier Original — accepted; the Swedish issuer Z12 supports Update (the swagger states that Update and Deletion are not supported for the DK/NO/FI issuers Z11, Z13, and Z14).
The `categoryType` string `"SALE OF GOODS"`, taken from the swagger-documented value list, is accepted.

The PDF-variant endpoint (`/v3/customs/declaration/pdf` with A4 rendering parameters) returns the wrapped envelope `{bookingResponse: {bookingId, idInformation}, labelPrintout: [...]}` — the inner key is `bookingResponse`, distinct from the digital endpoint's bare envelope — matching the shape the connector already parses (`karrio/providers/postnord/customs.py` reads both).
Its `labelPrintout` carries the rendered, pre-filled CN22 (17,040 base64 characters, composition `{'cn22': 1}`), the "filled form" deliverable, saved to the probe artifact directory for eye verification.

The post-update by-id ZPL fetch returns the CN22 as raw ZPL text in `printout.data` (2,866 characters, `^XA` magic): the base64 transport applies to the PDF endpoints only, live-confirming the raw-UTF-8 re-encoding design in `_printout_base64` that until this round was unit-tested only.

## Residuals

The server-side 14-line rejection is unprobed — the local guard is live-verified, and the optional direct-to-server probe (scenario D, `POSTNORD_PROBE_SERVER_LIMIT`) was not run.
An OK-but-empty by-id response — status OK, all-zero composition, no printout data — was observed before the declaration existed; surfacing that case as a message is recorded as OpenSpec task 3.6, alongside keying the connector's by-id fetch by printId.
