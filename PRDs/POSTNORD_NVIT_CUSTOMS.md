# PostNord NVIT: per-line customs data for Norway-in-transit compliance

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-09-22 |
| Status | Planning (Q1-Q5 gate implementation) |
| Owner | Joaqim Planstedt |
| Type | Integration |
| Reference | [AGENTS.md](../AGENTS.md) |

## Table of Contents

- [Executive Summary](#executive-summary)
- [Open Questions & Decisions](#open-questions--decisions)
- [Problem Statement](#problem-statement)
- [Goals & Success Criteria](#goals--success-criteria)
- [Alternatives Considered](#alternatives-considered)
- [Technical Design](#technical-design)
- [Edge Cases & Failure Modes](#edge-cases--failure-modes)
- [Implementation Plan](#implementation-plan)
- [Testing Strategy](#testing-strategy)
- [Risk Assessment](#risk-assessment)
- [Migration & Rollback](#migration--rollback)
- [Appendices](#appendices)

## Executive Summary

From 1 April 2026 the temporary arrangement for norske varer i transitt (NVIT — Norwegian goods moving Norway-to-Norway via Sweden or Finland) has ended, and full per-goods-line customs data is required at booking: ordinary trade description, six-digit HS code, net weight, gross weight, and packaging details.
The carrier files the NCTS transit declaration; the merchant's obligation is complete data at booking, which lands on karrio's booking payload.
The postnord connector today collapses all unified customs into one shipment-level `customsDeclarationCN22` whose rows carry gross weight only, so the NVIT data set is inexpressible on the wire we send.
PostNord's schema is not the blocker: the `customsInvoice` branch already models line `netWeight` + `grossWeight`, per-parcel `refItemIds`, `totalNetWeight`, and `splitShipmentReference`; the gap sits in the unified model's single `Commodity.weight` and the connector's CN22-only mapping.
This PRD canonizes the 2026-09-22 investigation findings, documents the interim proxy workaround, and frames the decisions that gate implementation.

### Key Architecture Decisions

1. **Declaration branch: `customsInvoice` (recommended, gated by Q1)** — the only branch expressing line net+gross weight, split-shipment references, `totalNetWeight`, and `returnHsTariffNumber`; CN23 links parcels via `itemIds` but its rows are gross-only.
2. **Per-parcel association: invoice rows' `refItemIds` keyed to booking `goodsItem[].items[].itemIdentification.itemId` (gated by Q1/Q3)** — the connector must stop emitting the constant `itemId="0"` and assign unique per-parcel ids.
3. **Net-weight modeling: unified `Commodity` extension preferred (gated by Q2)** — semantically correct and eventually reusable by other carriers; a connector-local convention stays cheaper but untyped.
4. **Line source: `Parcel.items` for multi-parcel flows, `customs.commodities` as the shipment-level aggregate (gated by Q3)**.
5. **Interim workaround: consumer-built `customsInvoice` declarations via `gateway.proxy.create_customs_declaration` (D3)** — usable today, one declaration object per item id.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| Decision record and findings canonization (this document) | Dashboard or UI changes |
| Connector invoice-branch mapping with per-parcel linkage | Unified/server API surface for post-booking declarations (stays consumer-owned) |
| Optional SDK model extension per Q2 | CN23 branch mapping (unless Q1 resolves otherwise) |
| Returns-from-Norway customs coverage | Other carriers' net-weight adoption |
| Tests and sandbox verification plan | VOEC regime changes (already mapped via `customs.options`) |

## Open Questions & Decisions

### Pending Questions

| # | Question | Context | Options | Status |
|---|----------|---------|---------|--------|
| Q1 | Which declaration branch does PostNord expect for NVIT flows? | Public sources are silent; branch structure plus fetched postnord.se invoice guidance favor `customsInvoice` (inference grade, Appendix A) | A) customsInvoice B) CN23 + per-parcel declarations C) hold mapping until PostNord confirms | Pending |
| Q2 | How is net weight modeled? | CN22/CN23 rows are gross-only; invoice rows carry both; `Commodity` has a single `weight` | A) unified optional `Commodity.net_weight` B) connector convention over `Commodity.metadata` C) derive net from gross minus tare (no tare source; rejected) | Pending |
| Q3 | Unit of modeling: per-parcel lines or shipment-level lines? | toll.no's unit is the varelinje (goods line); PostNord's announcement phrases it per parcel; split/multi-parcel flows need the parcel association to survive | A) `Parcel.items` as the line source for multi-parcel shipments B) `customs.commodities` plus explicit parcel association | Pending |
| Q4 | Where do packaging details land? | NVIT requires packaging type, count, and mark per line; invoice rows offer `marksAndNumbers`, `units`, `quantity`; the envelope offers `totalNumberOfPackages` | A) map from `Commodity.metadata` B) new unified fields C) defer if Phase 0 confirms booking goodsItem data suffices | Pending |
| Q5 | Gate on NVIT applicability? | Affected flows are postcode bands 0001-7999 to 8000-9999 and 8000-9499 to 9500-9999 (Norway to Norway via SE/FI); sending complete data elsewhere is harmless | A) always send the invoice branch when per-line data is present B) detect the bands and only then deviate from CN22 | Pending |

### Resolved Decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| D1 | PRD-first workflow applies | This document precedes implementation | Multi-module change (possible SDK model extension plus connector mapping); repo rule `prd-and-review.md` | 2026-09-22 |
| D2 | PostNord confirmation email | Deferred (belayed by user) | User decision 2026-09-22; Phase 0 remains the gate before any mapping lands; also request SE manual section 7.6.1 | 2026-09-22 |
| D3 | Interim workaround | Documented proxy path (Appendix C) | `gateway.proxy.create_customs_declaration` with caller-built invoice declarations, one per item id, is compliance-shaped today | 2026-09-22 |
| D4 | Evidence basis | Vendored swagger wire capture plus fetched toll.no/postnord.no pages; full provenance in Appendix A | Developer portals are JS SPAs; official field descriptions are not fetchable without a portal key | 2026-09-22 |

### Edge Cases Requiring Input

None beyond the pending questions; the remaining edge cases below carry proposed handling.

## Problem Statement

### Current State

```python
# modules/connectors/postnord/karrio/providers/postnord/shipment/create.py:418-430
customs_options = lib.to_customs_info(
    payload.customs, option_type=provider_units.CustomsOption
).options
customs_declaration = lib.identity(
    _customs_declaration(payload.customs, options=customs_options,
        total_gross_weight=packages.weight.KG,
        country_of_origin=shipper.country_code)
    if payload.customs and payload.customs.commodities else None
)
```

- `_customs_declaration` (`create.py:280-341`) builds one `CustomsDeclarationCN22Type` from `customs.commodities`, attached once per shipment at `ShipmentType.customsDeclarationCN22` (`create.py:542`).
- `_customs_line` (`create.py:241-277`) maps `Commodity.weight` to row `grossWeight`; no net-weight source exists to map.
- The goodsItem loop (`create.py:500-541`) sets `itemId="0"`, never sets `goodsDescription`, and never reads `package.items`.
- Returns reuse the same create flow (`shipment/return_shipment.py:1-13`); `reasonForExportation` and `returnHsTariffNumber` are unmapped.

### Desired State

Contingent sketch (assumes Q1=A, Q2=A, Q3=A; adjust when questions resolve):

```python
# booking emits the invoice branch when per-line customs data is present
customs_invoice = lib.identity(
    _customs_invoice(
        parcels=[(item_id, package, items) for ...],  # unique itemId per parcel
        customs=payload.customs,
        options=customs_options,
        split_reference=lib.identity(
            str((payload.options or {}).get("split_shipment_reference") or "").strip()
            or None
        ),
    )
    if _has_per_line_customs(payload) else None
)
```

Each invoice row carries `content`, `hsTariffNumber` (six or more digits, no spaces), `netWeight` and `grossWeight`, `refItemIds` naming the parcels containing the goods, and `quantity`/`units`; the envelope carries `totalNetWeight`/`totalGrossWeight`, `totalNumberOfPackages`, and `splitShipmentReference` when supplied.
Shipments without per-line data keep today's CN22 path byte-identically.

### Problems

1. **Per-parcel association is impossible**: all commodities collapse into one shipment-level CN22 and every parcel shares the constant `itemId="0"`.
2. **Net weight is inexpressible**: CN22 rows are gross-only and `Commodity` has a single weight, so half the NVIT weight requirement cannot be sent.
3. **Per-parcel goods lines are dropped**: `Parcel.items` is never read by any postnord provider file.
4. **`goodsDescription` is never set** on goodsItem, losing the per-parcel description NVIT asks for.
5. **Split-shipment identity is unmapped**: `splitShipmentReference` is unused despite the swagger note "For export to Norway".
6. **Returns share the gap**: return-ness reaches only `categoryOfItem` ("RETURNED GOODS"), never `reasonForExportation` 1040 or `returnHsTariffNumber`.

## Goals & Success Criteria

### Goals

1. The NVIT per-line data set (description, HS code, net weight, gross weight, packaging) is expressible end-to-end at booking time through the unified API.
2. Requests without per-line customs data remain byte-identical to today's output.
3. Returns from Norway are covered by the same mapping.
4. The mapping is verified against the sandbox before merge and against production as a P1 follow-up.

### Success Criteria

| Metric | Target | Priority |
|--------|--------|----------|
| Multi-parcel fixture serializes the invoice branch with net+gross weights, unique itemIds, and refItemIds | assertDictEqual green | Must-have |
| Absent-data request unchanged | assertDictEqual against existing fixture | Must-have |
| postnord suite plus full SDK sweep | all green | Must-have |
| Sandbox declaration accepted | live-check note in docs/notes/postnord/ | Must-have |
| Production NVIT booking verified | live-check note | Nice-to-have |

### Launch Criteria

**Must-have (P0):**
- [ ] Q1 resolved (PostNord confirmation or explicit user acceptance of the inference)
- [ ] Invoice-branch mapping with per-parcel linkage, per the resolved Q2/Q3
- [ ] Full postnord connector suite green

**Nice-to-have (P1):**
- [ ] Service matrix across booking services in sandbox
- [ ] Production NVIT booking verified

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| A. Booking-time customsInvoice mapping | Full NVIT expressiveness in one request; schema already generated; matches PostNord invoice guidance | Branch expectation unconfirmed (Q1); requires net-weight modeling (Q2) | **Selected** (gated by Q1) |
| B. CN23 with per-parcel post-booking declarations | `itemIds` linkage exists; proxy already accepts declaration objects | CN23 rows are gross-only, so net weight stays inexpressible; extra calls; caller-built | Rejected as end state |
| C. Proxy-only stopgap | Zero connector change; available today | Consumer-owned; no unified surface; per-shipment bookkeeping on the consumer | Retained as interim (D3) |
| D. Status quo | None | Compliance failure risk: PostNord's announcement warns of delays for incomplete data | Rejected |

### Trade-off Analysis

Approach A concentrates the change where the obligation lands — the booking payload the merchant already sends — and reuses generated schema types plus the established CN22 builder pattern, so its cost is the mapping itself plus the Q2 model decision.
Approach B splits compliance across two calls and still cannot carry net weight, which is the clearest signal it is not the intended vehicle.
Approach C is the correct bridge: it exists, is live-verified in shape, and stays useful for corrections regardless of Q1.

## Technical Design

### Existing Code Analysis

| Component | Location | Reuse Strategy |
|-----------|----------|----------------|
| CN22 booking mapping | `providers/postnord/shipment/create.py:241-341,418-430,542` | Builder pattern and row assembly to mirror for the invoice branch |
| Invoice/CN23 schema types | `karrio/schemas/postnord/shipment_request.py:94-113,153-171,210-241` (mirrored in `customs_declaration_request.py`) | Already generated; instantiate directly, no regeneration |
| goodsItem loop | `create.py:500-541` | Extend: unique per-parcel itemIds, `goodsDescription` from parcel description/content |
| Connector CustomsOption enum | `providers/postnord/units.py:195-208` | Unchanged unless Q4 adds packaging options |
| 13-line guard | `units.py:262-286` (`CUSTOMS_DECLARATION_MAX_LINES = 13`) | Reuse for invoice rows once Phase 0 verifies the branch limit |
| Proxy declaration methods | `mappers/postnord/proxy.py:309-333`, `providers/postnord/customs.py:39-110` | Interim path (D3); unchanged |
| Unified models | `modules/sdk/karrio/core/models.py:35-55,58-80,105-120` | Q2/Q3 decision target: `Commodity`, `Parcel.items` (:77), `Customs` |
| Package/Products aggregation | `modules/sdk/karrio/core/units.py:770-780,646-697,841-844` | `Package.weight = max(declared, sum of item weights)` supplies per-parcel gross; `Products` sums quantities and weights |
| Raw option read | `create.py:159-168` (`options.language`) and entry-code successor | Pattern for `options.split_shipment_reference` |
| Reject-with-message channel | entry-code D6a (ctx flag + proxy short-circuit) | Pattern for HS validation rejection |
| Tests | `tests/postnord/test_shipment.py:1329+`, `test_customs_declaration.py` | Fixture and assertion patterns |

### Architecture Overview

```
CURRENT (CN22-only, shipment-level)         PROPOSED (invoice branch, per-parcel)

unified payload                              unified payload
  customs.commodities --+                      customs.commodities --+
  parcels (items -- X)  |                      parcels + Parcel.items|
                        v                                            v
             _customs_declaration                          _customs_invoice
                        |                                            |
                        v                                            v
     ShipmentType.customsDeclarationCN22       ShipmentType.customsInvoice
       one declaration, gross-only rows          rows: netWeight + grossWeight,
       itemId "0" for every parcel               refItemIds -> parcel itemIds
                        |                         splitShipmentReference option
                        v                                            v
                POST booking EDI                           POST booking EDI
```

### Sequence Diagram

```
Client          create.py             Proxy               PostNord      Toll (NCTS)
  | per-line data  |                     |                    |             |
  |--------------->| invoice branch      |                    |             |
  |                | unique itemIds      |                    |             |
  |                |---------------- --->| booking EDI body   |             |
  |                |                     |------------------->| accept +ids |
  |                |                     |<-------------------|             |
  |                | parse labels/ids    |                    | transit decl|
  |<---------------|                     |                    |------------>|
```

### Data Flow Diagram

```
REQUEST FLOW
unified Parcel.items + customs --> mapper --> unique itemId per parcel
  --> invoice rows (content, hs, net, gross, refItemIds)
  --> envelope totals + splitShipmentReference --> booking EDI body

RESPONSE FLOW (unchanged parser surface)
bookingResponse --> parse --> labels, shipment ids
```

### Data Models

Option A (Q2-A, preferred):

```python
# modules/sdk/karrio/core/models.py -- proposal only, gated by Q2
@attr.s(auto_attribs=True)
class Commodity:
    # ... existing fields unchanged ...
    weight: Decimal = None        # gross semantics when net_weight is set
    net_weight: Decimal = None    # NVIT: weight excluding packaging
```

Weight derivations under Option A: per-parcel gross is `Package.weight` (already `max(declared, sum of item weights)`); per-parcel net is the sum of item `net_weight` (falling back to `weight` when absent, per the Q2 fallback decision); envelope totals are the sums.

Option B (Q2-B, convention): net weight rides in `Commodity.metadata["net_weight"]`, read only by the postnord connector; no SDK blast radius, but the field is untyped and invisible to every other surface.

### Field Reference

NVIT requirement to PostNord invoice field to karrio source today:

| NVIT requirement | Invoice branch field | Karrio source today | Gap |
|------------------|----------------------|---------------------|-----|
| Trade description | `detailedDescription[].content` | `Commodity.title/description` | mapped on CN22 only |
| HS code (>=6 digits, no spaces) | `detailedDescription[].hsTariffNumber` | `Commodity.hs_code` | unmapped on invoice; no validation |
| Net weight | `detailedDescription[].netWeight`, `totalNetWeight` | none (`Commodity.weight` only) | Q2 |
| Gross weight | `detailedDescription[].grossWeight`, `totalGrossWeight` | `Commodity.weight`, `Package.weight` | unmapped on invoice |
| Packaging type/count/mark | `marksAndNumbers`, `units`, `quantity`, `totalNumberOfPackages` | `Parcel.packaging`, line `quantity` | Q4 |
| Per-parcel linkage | row `refItemIds`, envelope `ids` | none (`itemId="0"`) | unique ids plus rows |
| Split shipment | `splitShipmentReference` | none | new raw option |
| Returns | `invoice.reasonForExportation` (1040), `returnHsTariffNumber` | `customs.content_type` (category only) | new mapping |

### Branch Capability Matrix

Evidence: generated schemas plus vendored swagger (Appendix A); all three branches attach at the shipment element.

| Capability | CN22 | CN23 | customsInvoice |
|-----------|------|------|----------------|
| Line description | yes | yes | yes |
| Line HS code | yes | yes | yes (+ `returnHsTariffNumber`) |
| Line net weight | no | no | yes |
| Line gross weight | yes | yes | yes |
| Per-parcel link | no | envelope `itemIds` | row `refItemIds` + envelope `ids` |
| Split shipment | no | no | `splitShipmentId` (deprecated) / `splitShipmentReference` |
| Totals | `totalGrossWeight`, `totalValue` | same | `totalNetWeight` + `totalGrossWeight` + `totalNumberOfPackages` |
| Mapped by connector today | booking-time | proxy-only | proxy-only |

### API Changes

No karrio endpoint changes.
The unified surface grows only by optional commodity fields (Q2/Q4) and one raw option, `options.split_shipment_reference`, following the `options.entry_code` pattern (raw read, no `ShippingOption` enum membership).

## Edge Cases & Failure Modes

### Edge Cases

| Scenario | Expected Behavior | Handling |
|----------|-------------------|----------|
| Same goods line in several parcels | one row whose `refItemIds` lists every containing parcel | row aggregation by commodity key |
| Several lines in one parcel | several rows referencing that parcel's itemId | straightforward |
| Net weight absent on some lines | deterministic behavior, not silence | Q2 fallback decision (net=gross or reject) |
| HS shorter than 6 digits or containing spaces | toll.no rejects; catch before send | validation plus reject-with-message (entry-code D6a pattern) |
| Row count exceeds the branch limit | guard trips before submission | extend the 13-line guard after Phase 0 verifies the invoice limit |
| Single-parcel shipment with per-line data | invoice branch still emitted | data-presence gating (Q5) |
| Return from Norway | `reasonForExportation` 1040, `returnHsTariffNumber` rows | `customs.content_type` mapping |
| No per-line data at all | today's CN22 path, byte-identical | gate on data presence |
| Missing currency for line values | no silent currency guessing | derive from first line; reject when absent |

### Failure Modes

| What Can Go Wrong | Impact | Mitigation |
|-------------------|--------|------------|
| Branch inference wrong (Q1) | mapping rework | Phase 0 gate before merge; interim path (D3) unaffected |
| SDK model extension regresses other connectors | broad breakage | additive optional field; full `./bin/run-sdk-tests` sweep |
| PostNord rejects the invoice branch on some services | booking faults on those services | sandbox service matrix (Phase 4) |
| NVIT scope shifts again (toll.no phasing) | stale mapping | Appendix A provenance; re-verify at Phase 0 |

## Implementation Plan

### Phase 0: PostNord confirmation (gate)

| Task | Artifacts | Status | Effort |
|------|-----------|--------|--------|
| Confirm branch choice, `splitShipmentReference` semantics, invoice row limit, packaging expectations; request SE manual section 7.6.1 | mail to nvit@postnord.com (belayed per D2); answers fold into Q1/Q4 | Pending | S |

### Phase 1: Model decision (Q2/Q3)

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Resolve Q2/Q3; if unified, add optional `Commodity.net_weight` and `Products` aggregation support | `modules/sdk/karrio/core/models.py`, `modules/sdk/karrio/core/units.py` | Pending | S/M |

**Dependencies:** Phase 2 requires Phase 0 (Q1) and Phase 1 (Q2/Q3).

### Phase 2: Connector mapping

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| `_customs_invoice` builder; branch selection (invoice when per-line data present, else CN22) | `modules/connectors/postnord/karrio/providers/postnord/shipment/create.py` | Pending | M |
| Unique per-parcel itemIds; `goodsDescription` from parcel description/content | same | Pending | S |
| `options.split_shipment_reference` raw read and envelope wiring | same | Pending | S |
| Constants, HS validation, guard extension | `modules/connectors/postnord/karrio/providers/postnord/units.py` | Pending | S |

### Phase 3: Returns

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| `customs.content_type` return mapping to `reasonForExportation` 1040; `returnHsTariffNumber` rows | `create.py`, `units.py` | Pending | S |

### Phase 4: Verification and documentation

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Fixtures and tests (below) | `modules/connectors/postnord/tests/postnord/test_shipment.py` | Pending | M |
| README and sdk-guide notes | connector `README.md`, `docs/notes/postnord/customs-declaration-sdk-guide.md` | Pending | S |
| Sandbox live check including service matrix | note in `docs/notes/postnord/` | Pending | M |

## Testing Strategy

> All tests use `unittest` (never pytest), run from repository root, following the connector's existing fixture style.

### Test Cases

```python
def test_create_shipment_customs_invoice_request(self):
    """Two parcels with per-parcel items serialize the invoice branch with
    net and gross weights, unique itemIds, and refItemIds linking rows
    to parcels."""

def test_create_shipment_customs_absent_unchanged(self):
    """No per-line data: request payload byte-identical to the CN22-era
    fixture."""

def test_create_shipment_customs_invoice_hs_invalid(self):
    """Five-digit or space-containing HS: booking rejected with a message
    and no HTTP call (entry-code D6a ctx/proxy pattern)."""

def test_create_return_shipment_customs_invoice(self):
    """Return: reasonForExportation 1040 and returnHsTariffNumber on rows."""
```

### Running Tests

```bash
source bin/activate-env
python -m unittest discover -v -f modules/connectors/postnord/tests
./bin/run-sdk-tests   # pre-merge regression sweep
```

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Branch expectation unconfirmed | High (rework) | Medium | Phase 0 gate; D3 interim unaffected |
| Net-weight semantics chosen wrong (Q2) | Medium | Medium | additive optional field; explicit README semantics |
| SDK model blast radius | Medium | Low | optional field plus full sweep |
| Invoice row limit unknown | Low | Medium | verify at Phase 0/4; guard ready to extend |
| NVIT scope shifts again | Medium | Low | Appendix A provenance; re-verify at Phase 0 |

## Migration & Rollback

### Backward Compatibility

- **API compatibility**: additive optional fields plus one raw option; absence is the off state and the outbound body is unchanged.
- **Data compatibility**: no migrations in connector scope; if Q2-A lands, the field is optional and serializers pass it through as `None` by default (verified in Phase 1).
- **Feature flags**: none; data-presence gating, with Q5 deciding whether band detection is added.

### Rollback Procedure

1. Revert the mapping commit(s) on the feature branch.
2. Re-run the postnord connector suite.
3. No data cleanup; the interim proxy path (D3) is unaffected.

## Appendices

### Appendix A: Provenance and Evidence

| Source | Location | Statement | Grade |
|--------|----------|-----------|-------|
| toll.no news, published 2026-02-10 | <https://www.toll.no/no/bedrift/nyheter-for-naeringslivet/midlertidig-ordning-for-nvit-opphorer> | temporary NVIT arrangement ends 2026-03-31; six-digit HS required for transit goods | Fetched 2026-09-22 |
| toll.no NVIT page | <https://www.toll.no/no/bedrift/transport-og-tollager/norske-varer-i-transitt> | per-varelinje data list; NCTS-5 since 2025-01-21 | Fetched 2026-09-22 |
| postnord.no NVIT article (EN) | <https://www.postnord.no/en/news/new-requirements-for-norwegian-goods-in-transit-nvit/> | per varelinje not per sending; HS >=6 digits no spaces; channels (TA-system, EDI IFTMIN, API/Booking, Portal); never on the parcel; postcode bands; nvit@postnord.com | Fetched 2026-09-22 |
| postnord.se customs-documents page | <https://www.postnord.se/en/business/import-export-customs/customs-documents-and-shipping-documents> | commercial invoice requires net/gross per goods item and total gross; invoice is a sufficient basis for PostNord to create the export declaration; CN23 thresholds (<= SEK 2,000 commercial) | Fetched 2026-09-22 |
| Vendored booking swagger v3.5.29.1 | `vendor/booking.swagger.json` | field names; `voec` "For import to norway"; `splitShipmentReference` "For export to Norway" (example `21100023_1111111`); endpoints `POST /v3/customs/declaration{,/pdf}`, `/v3/customs/consolidation` | Wire capture |
| Live verification 2026-09-21 | `docs/notes/postnord/customs-declaration-live-verification.md` | booking-time CN22 and post-booking declarations accepted in sandbox and production; `SACUS-BR-24062502` registration-number fault behavior | Live |
| Packrooster changelog (third party) | <https://approosters.com/pages/packrooster-changelog> | `reasonForExportation` codes 1000 (sale) and 1040 (return) | Third-party |
| Developer portals | developer/atdeveloper/guide.postnord.com | JS SPAs; official field descriptions not fetchable without a portal application key | Limitation |
| Stale index flag | postnord.se | the quoted "From 1 April 2026 ... split shipments, multi-parcel ..." sentence is absent from the page as fetched 2026-09-22; postnord.no's article is the primary for scope | Caveat |

### Appendix B: NVIT Fact Sheet

| Fact | Value |
|------|-------|
| Expansion | norske varer i transitt — Norwegian goods in transit |
| Geography | Norway to Norway routed via Sweden or Finland; postcode bands 0001-7999 to 8000-9999 and 8000-9499 to 9500-9999 |
| Legal basis | Transit Convention; NCTS phase 5 (2025-01-21) makes a six-digit HS code mandatory for transit goods |
| Temporary arrangement | collective code 54.02.53 plus generic description; ended 2026-03-31 |
| Full requirement | from 2026-04-01, per goods line (varelinje): ordinary trade description, six-digit HS number, net weight, gross weight, packaging (type, count, mark) |
| Who files | the carrier files the NCTS transit declaration; the merchant supplies complete data at booking |
| Channels | TA-system, EDI (IFTMIN), API/Booking solution, Portal — never on the parcel |
| Contact | nvit@postnord.com |
| VOEC distinction | separate regime (Norwegian import VAT, B2C under NOK 3,000, Skatteetaten registration); rides the `voec` field present in all three declaration branches |

### Appendix C: Interim Workaround (D3)

The consumer builds a `CustomsInvoiceType` declaration and submits it per parcel id through the connector-local proxy: `gateway.proxy.create_customs_declaration` / `create_customs_declaration_pdf`, with `ids` maxItems 1 (exactly one item id per declaration object) and the shared 13-line guard.
The caller owns branch choice, ids, and `updateIndicator`; there is no lifecycle management.
Full recipe: `docs/notes/guides/postnord-customs-declaration-proxy.md`.

### Appendix D: Current karrio to PostNord Customs Mapping (2026-09-22, develop)

| Unified field | PostNord field | Where | Per-parcel |
|---------------|----------------|-------|------------|
| `customs.commodities[].title/description` | CN22 `detailedDescription[].content` | `create.py:255` | No |
| `customs.commodities[].quantity` | CN22 row `quantity` | `create.py:256-260` | No |
| `customs.commodities[].weight` + unit | CN22 row `grossWeight` (KGM) | `create.py:252,261-265` | No |
| `customs.commodities[].value_amount/currency` | row `value`, `totalValue` | `create.py:266-273,331-340` | No |
| `customs.commodities[].hs_code` | row `hsTariffNumber` | `create.py:274` | No |
| `customs.commodities[].origin_country` | row `countryCode` | `create.py:275` | No |
| `customs.content_type` | `categoryOfItem.categoryType[0]` | `create.py:306-321` | n/a |
| `shipper.country_code` | `countryOfOrigin` | `create.py:316` | n/a |
| packages total weight | `totalGrossWeight` (KGM) | `create.py:425,326-330` | No (whole shipment) |
| `customs.options` eori/voec/ioss | `EORIorPersonalIdNumber`/`voec`/`ioss` | `create.py:313-315` | n/a |
| row index | `rowNo` | `create.py:276` | n/a |
| `Parcel.weight` | `goodsItem.items[].grossWeight` | `create.py:518-521` | Yes (only per-parcel customs-adjacent datum) |
| `Parcel.items[]` | unmapped | — | — |
| `Parcel.description/content` | `goodsDescription` never set | — | — |
| (nothing) | CN23 `itemIds`, invoice `refItemIds`/`ids`, `splitShipmentReference`, net weights | schema only | — |
