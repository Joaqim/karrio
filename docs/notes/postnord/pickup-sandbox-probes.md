# PostNord pickup sandbox probes

Record of the sandbox probes for the `feat-postnord-pickup-by-item-id` branch, all run on 2026-10-13 against the `atapi2.postnord.com` test host.
The probe script and the redacted captures live in `~/.local/state/agent-logs/karrio/postnord-pickup-probe/` (`probe.py`, `booking-*.json`, `p1-*.json`, `p2-*.json`, `p2b-*.json`).
Request bodies were built by the branch connector (`feat-postnord-pickup-by-item-id` at `3f51434fd`) and POSTed by the script so the HTTP status is observable; responses were parsed with the branch's `parse_pickup_response`.
Credentials are referenced by environment variable name only (`POSTNORD_APIKEY` and `POSTNORD_CUSTOMER_NUMBER`, loaded through the repository's direnv environment); no application id was sent.
Every capture was checked against the values of all `POSTNORD_*` credential variables before writing; matches are replaced with `<redacted>`.
Each step ran once, and no rejected step was retried; P2b is a separate step against a changed connector, not a retry of P2.

## Booking for an item id

One `postnord_parcel` (basic service code 18, additional service A4) was booked from Sandhamnsgatan 61, 11528 Stockholm, SE to Östra Hamngatan 1, 41110 Göteborg, SE, 1 kg, through `POST /rest/shipment/v3/edi/labels/pdf` with `testIndicator` `true`.
The sandbox answered HTTP 200 with `idInformation[].status` `OK`.

| Id | Value |
|---|---|
| item id | 00173215400196064632 |
| printId | daf7d84d83de44869317e2c84c7e7ff7 |
| bookingId | ILPN0010L3Z3TAZMDGANKQLZXMWJUK |

PostNord has no cancellation endpoint, so the booking stays booked.

## P1: pickup by item id

`POST /rest/shipment/v3/pickups/ids` with one `pickupIdInfo` (the item id above, window 2026-10-14 08:00 to 16:00) returned HTTP 400:

```
{"message":"General client indata error","compositeFault":{"faults":[{"explanationText":"Edi not found for item Id: 00173215400196064632"}]}}
```

The booking was sent with `testIndicator` `true`, which the booking swagger describes as "No EDI will be sent to PostNord".
This matches the earlier sandbox result in `customs-declaration-live-verification.md`, where test-mode bookings were not found by the by-id and declaration endpoints ("Unable to find EDI").
The connector sets `testIndicator` from `test_mode`, so a sandbox connection cannot produce an item id that `/v3/pickups/ids` finds; the success response of `/v3/pickups/ids` was not observed.
The fault body parsed into one message with the explanation text and no code.

## P2: collection request without a consignee

`POST /rest/shipment/v3/pickups` with the connector's current collection request (service 20, `itemId` `"0"`, `testIndicator` `true`, consignor and pickup party at the Stockholm address, no consignee, freeText usage code `PICKUP`) returned HTTP 400:

```
{"message":"Invalid indata object EdiInstruction","compositeFault":{"faults":[{"explanationText":"usageCode must be at least 3 characters long and no more than 3 characters long","faultReferences":[{"key":"CustomerOriginValidationError.type","value":"MANDATORY_FIELDS_MISSING"},{"key":"CustomerOriginValidationError.subType","value":"USAGE_CODE"}]}]}}
```

The sandbox rejected the freeText usage code, which the booking swagger limits to three characters (`DEL`, `ICN`, `INS`, `ZRE`, `ZTG`, `ZHD`, `ZOI`, `ZUL`); the connector sends `PICKUP`.
No fault mentioned the consignee, so the sandbox gave no verdict on the missing consignee: validation stopped at the usage code.
The fault body parsed into one message with code `USAGE_CODE`.

## P2b: collection request with the usage code and messageFunction fixes

After P2 the connector was changed to send the pickup instruction under freeText usage code `ZHD` ("Handover description", the closest fit in the swagger's list) and to send `messageFunction` `PickupBooking`, which the swagger documents for "a pickup or a DPD Collection Request" (the default is `Instruction`).
`POST /rest/shipment/v3/pickups` with the branch connector at `45f31f9a1` (service 20, `itemId` `"0"`, `testIndicator` `true`, consignor and pickup party at the Stockholm address, no consignee, window 2026-10-14 08:00 to 16:00) returned HTTP 400:

```
{"message":"General client indata error","compositeFault":{"faults":[{"explanationText":"Service code is not valid for PickupBookings: 20"}]}}
```

The sandbox raised no usage-code fault and referred to the request as a PickupBooking.
It rejected basic service code 20 (`postnord_return_pickup`, the connector's default pickup service) for PickupBookings.
No fault mentioned the consignee, so the sandbox again gave no verdict on the missing consignee.
The fault body parsed into one message with the explanation text and no code.

## Consequences

Pickup remains unverified against the sandbox.
The sandbox accepted the `ZHD` usage code and the `PickupBooking` message function far enough to reach service validation, and rejected service code 20 for PickupBookings.
The swagger does not list which basic service codes PickupBookings accept.
Whether the sandbox requires a consignee on a collection request remains open; it would need a collection request with a service code the sandbox accepts for PickupBookings.
The sandbox did not find an item id from a test-mode booking, so the `/v3/pickups/ids` success path needs an item id from a booking sent with `testIndicator` `false`.
