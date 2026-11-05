# DHL Freight Sweden access point — fresh-context review gate

Branch: dhl-freight-sweden-access-point (three commits off develop, ad1f5c0d2).
Scope: AccessPoint party mapping, missing-detail guard, option enums, tests, PRD v1.2.
Read-only review; the only file written by this review is this note.

## Verdict

PASS. Two LOW observations, neither blocking (see Findings).

## Checklist

- PRD decision #14 vs implementation: PASS. The connector requires the caller-supplied id plus five detail options (create.py:311-323), emits a complete AccessPoint party (create.py:341-357), defaults subType to ParcelShop (create.py:344-347), and imposes no product or country gating anywhere in `_service_point_party`.
- PRD field-reference rows: PASS. The seven `options.dhl_freight_sweden_service_point*` rows (PRD lines 296-302) name exactly the options implemented in units.py:101-117, and the "missing details raise a `SHIPPING_SDK_FIELD_ERROR` naming the missing options" claim matches the guard's error payload (create.py:330-339).
- Remaining `Servicepoint` claims: PASS. `rg -n 'Servicepoint' PRDs/PRD_DHL_FREIGHT_INTEGRATION.md` yields one hit (PRD line 335), which is the explicit disambiguation "(the subType enum — not `Servicepoint`)"; no text anywhere claims `Servicepoint` as a subType value.
- Scope creep: PASS. `git diff develop..HEAD --name-only` lists exactly the four files (PRD, create.py, units.py, test_shipment.py).
- Party emission shape: PASS. id, type=AccessPoint, subType, name, and AddressType(street, cityName, postalCode, countryCode) are all set (create.py:341-356); the guard guarantees non-empty values so `lib.to_dict` omits nothing unexpected.
- Guard mechanism: PASS. `ServicePointDetailsError` subclasses `errors.ShippingSDKDetailedError` with `code = "SHIPPING_SDK_FIELD_ERROR"` (create.py:23-26), structurally identical to the existing `DeclarationCurrencyError` customs-currency guard (create.py:17-20); both surface as a `Message` via `abort()` in karrio/api/interface.py:37-52, which carries `code` and `details` onto the message.
- Option serialization names: PASS. servicepointName / servicepointStreet / servicepointCity / servicepointPostalCode / servicepointCountryCode (units.py:103-117).
- postalCode string-vs-int: PASS. The generated AddressType annotates `postalCode: typing.Optional[int]` (transport_instruction_request.py:62) but constructs via plain attrs with no coercion, so the string survives serialization; the consignor/consignee `_party` helper uses the identical `str(x) if x else None` pattern (create.py:377) and its expected fixtures already assert string postal codes (test_shipment.py:652,665), so the new code follows the established precedent; live sandbox bookings 2906723792/2906723800/2906723826 returned 200 with string postal codes.
- Test coverage: PASS. 109 ParcelStation (test_shipment.py:77-85) and 109 ParcelShop (test_shipment.py:87-95) are both covered against DK fixtures, 103 ParcelShop against an SE fixture (test_shipment.py:58-66), and the negative test asserts the exact set of five full option-name detail keys (test_shipment.py:207-216).
- Suite: PASS. `python -m unittest discover -f modules/connectors/dhl_freight_sweden/tests` → Ran 35 tests, OK.
- Code quality: PASS. `import karrio.lib as lib` throughout, no legacy DP/SF/NF usage, functional style (comprehensions for details/missing/error-details), `meta=dict(category="PUDO")` matches the convention used by ten-plus other connectors, and `git diff develop..HEAD -- modules/connectors/dhl_freight_sweden/karrio/schemas/` is empty.
- Commit hygiene: PASS. `feat`/`test`/`docs` commits in `type(scope): summary` form with empty bodies, no Co-Authored-By or AI footer lines.
- Deliberate non-goals honored: PASS. No client-side product/country eligibility gating, no subType-per-country gating, no locator lookup inside create, and the ParcelShop default is unchanged from develop.

## Adversarial probes

All probes executed through the real request-building path (gateway mapper + `lib.to_dict`), not by reading alone.

- Partial details (id + street only): the guard fires and the message names exactly the missing subset ("missing name, city, postal_code, country_code") with details keyed by only those four full option names; the supplied street is not falsely reported.
- Details set but id absent: parties serialize as [Consignor, Consignee] only — no AccessPoint party is emitted and the orphan detail options are ignored, matching the PRD's "With service point" conditioning of the detail rows.
- Empty strings vs None: both are falsy under `if not value` (create.py:324), so an empty-string name is treated as missing and the guard fires ("missing name"); None-valued unset options behave identically.
- Invalid subType value: `PartySubType.map("NotASubType").value_or_key` returns the raw key verbatim (karrio/core/utils/enum.py:17-34,103-104), so it is emitted as `subType: "NotASubType"` and rejected by DHL server-side — consistent with decision #9 (DHL validation authoritative) and byte-identical to the develop behavior for this option.
- Integer postal code: an int 11225 supplied as the option value serializes as the string `'11225'` on the wire because of the explicit `str()` wrap (create.py:354), so alphanumeric postal codes and int-typed caller input both survive.
- Import/cycles: no new imports were added — the new function uses `dhl_freight_sweden_req.PartyType`/`AddressType` and `provider_units`, all already imported at create.py:3-14.
- Fixture drift: the negative test compares a set of detail keys (order-independent) and the positive fixtures carry string postal codes that match the serialized wire output; the 103/109 fixture party dicts were refreshed together with their payloads in the same commit.

## Findings

- CRITICAL: none.
- MEDIUM: none.
- LOW (observation, no action required for this change): whitespace-only detail values (e.g. name `"  "`) are truthy and pass the guard, so they are emitted and left to DHL's server-side validation; karrio option handling generally treats whitespace as present, and locator-sourced data is not expected to be whitespace-only.
- LOW (pre-existing, outside this diff): `black --check` flags create.py and test_shipment.py, but every flagged region exists on develop (procedure_code, `_party` consignor call, payerCode wrap, declaration_currency, `_access_point` helper); the code added by this branch is black-clean, so the deviation was inherited, not introduced.

## Evidence commands

- `git diff develop..HEAD` (four files) and `git diff develop..HEAD -- modules/connectors/dhl_freight_sweden/karrio/schemas/` (empty).
- `python -m unittest discover -f modules/connectors/dhl_freight_sweden/tests` → 35 OK.
- `rg -n 'Servicepoint' PRDs/PRD_DHL_FREIGHT_INTEGRATION.md` → one hit, line 335 (disambiguation only).
- Adversarial probe script driving `karrio.Shipment.create(...).parse()` through `modules/connectors/dhl_freight_sweden` with a mocked proxy `lib.request`, 2026-09-10.
