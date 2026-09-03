# PostNord ZPL Label Support

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-09-03 |
| Status | Planning |
| Owner | Joaqim Planstedt |
| Type | Integration / Enhancement |
| Reference | [AGENTS.md](../AGENTS.md), [PRD_POSTNORD_INTEGRATION.md](./PRD_POSTNORD_INTEGRATION.md) |

---

## Executive Summary

The PostNord connector's documented `label_type` connection setting is currently inert: the proxy always books against `/rest/shipment/v3/edi/labels/pdf`, and the response parser assumes `labelPrintout[].printout.data` is base64. A live observation of the ZPL endpoint (`/rest/shipment/v3/edi/labels/zpl`) shows PostNord returns `encoding: "none"` with raw UTF-8 ZPL text in `data` — a transport-encoding contract the swagger does not document and the parser would mishandle. This PRD proposes full ZPL support: endpoint selection driven by label type, an encoding-aware parser that normalizes every printout to karrio's base64 label contract, tests for both endpoints, and a working note recording the spec gap.

### Key Architecture Decisions

1. **Documents.label stays base64 for all formats**: karrio core's ZPL bundling (`bundle_zpls`, `helpers.py:107`) b64-decodes its inputs, and the server serves labels as base64 documents — so raw ZPL text is normalized to base64 at parse time via `lib.encode_base64`, never passed through raw.
2. **Label type resolution mirrors SmartKargo**: `payload.label_type or settings.connection_config.label_type or "PDF"`, threaded to the proxy through `request.ctx`, following the established reference connector pattern.
3. **Encoding is trusted per-printout, not sniffed**: `printout.encoding == "base64"` passes through; anything else (`"none"`, absent) is treated as raw text and encoded. Content sniffing is rejected as fragile and unnecessary given the field exists.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| Endpoint selection `/labels/pdf` vs `/labels/zpl` in proxy | Exposing the `multiZPL` query param (left at default `false`) |
| Encoding-aware normalization in `_extract_details` | SVG label format (`labelFormat` allows it; no endpoint observed) |
| ZPL unit tests: request routing, parse, multi-printout bundling | Server-side ZPL→PDF conversion (Labelary) — UPS-style conversion flow |
| README + working-note documentation of the spec gap | Return-shipment ZPL (`/v3/returns/edi/labels/zpl`) |
| | Manifest/pickup label retrieval endpoints |

---

## Open Questions & Decisions

### Resolved Decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| D1 | Fix scope | Full ZPL support | `label_type` is already documented in README as a setting; completing it is the coherent unit of work. Parser-only would leave a documented knob dead. | 2026-09-03 |
| D2 | Label representation in `Documents.label` | Always base64 | Core contract: `bundle_base64`/`bundle_zpls` (`modules/sdk/karrio/core/utils/helpers.py:107-131`) operate on base64 inputs; server document endpoints serve base64. | 2026-09-03 |
| D3 | Raw-vs-base64 discrimination | Read `printout.encoding` field | Field exists on the generated schema (`karrio/schemas/postnord/shipment_response.py:78`); sniffing heuristics are fragile. | 2026-09-03 |

### Edge Cases Requiring Input

| Edge Case | Impact | Proposed Handling | Needs Input? |
|-----------|--------|-------------------|--------------|
| Does the live ZPL response carry `labelFormat: "ZPL"`? | The observed fragment showed `encoding` but the `labelFormat` value was not captured | Parser falls back to the *requested* label type from `ctx` when the response omits `labelFormat`, so both behaviors are safe | ❌ No (fallback covers both) |

---

## Problem Statement

### Current State

`proxy.py:102-111` hardcodes the PDF endpoint regardless of configuration:

```python
def create_shipment(self, request: lib.Serializable) -> lib.Deserializable[str]:
    response = lib.request(
        url=self._url("/rest/shipment/v3/edi/labels/pdf"),
        ...
    )
```

`shipment/create.py:73-84` assumes base64 data unconditionally, and the
docstring (line 8) asserts "``labelPrintout`` entries with base64 label data":

```python
printouts = response.labelPrintout or []
label_format = next(
    (p.printout.labelFormat for p in printouts if p.printout), "PDF"
)
label_data = [
    p.printout.data for p in printouts if p.printout and p.printout.data
]
label = lib.identity(
    label_data[0]
    if len(label_data) == 1
    else lib.bundle_base64(label_data, label_format) if label_data else None
)
```

### Desired State

```python
# proxy.py — endpoint selected from the label type threaded on request.ctx
label_type = request.ctx.get("label_type", "PDF")
path = "/rest/shipment/v3/edi/labels/zpl" if label_type == "ZPL" else \
       "/rest/shipment/v3/edi/labels/pdf"
```

```python
# shipment/create.py — each printout normalized to base64 before bundling
label_data = [
    _printout_base64(p.printout)
    for p in printouts
    if p.printout and p.printout.data
]
```

### Problems

1. **Dead configuration knob**: `ConnectionConfig.label_type` (`units.py:10`) and README row `label_type | PDF | Label document type` promise ZPL selection that the proxy never performs.
2. **Parser violates the base64 contract on ZPL responses**: single printout → raw ZPL text lands in `Documents.label` (breaks server label download); multiple printouts → `lib.bundle_base64(raw_zpl_list, "ZPL")` runs `base64.b64decode` on non-base64 text, producing padding errors or silently corrupted labels.
3. **Undocumented carrier contract**: the swagger defines `encoding` as `"description": "Encoding of the data (base64)"` with no enum (`booking.swagger.json:3947-3952`); the live ZPL endpoint's `encoding: "none"` is known only by observation and is recorded nowhere in the repo.

---

## Goals & Success Criteria

### Goals

1. Booking against the ZPL endpoint when the effective label type is ZPL (request-level override, else connection config, else PDF).
2. `Documents.label` is valid base64 for both PDF and ZPL responses, single or bundled.
3. Zero behavior change for existing PDF bookings (byte-identical parsed output).

### Success Criteria

| Metric | Target | Priority |
|--------|--------|----------|
| ZPL parse test: `docs.label` == base64 of captured raw ZPL | Exact match | Must-have |
| ZPL proxy test: URL is `/labels/zpl?apikey=…` when label type ZPL | Exact match | Must-have |
| Multi-printout ZPL bundling produces valid base64 of joined ZPL | Decodable round-trip | Must-have |
| All existing postnord tests unchanged and passing | 100% | Must-have |

### Launch Criteria

**Must-have (P0):**
- [ ] `python -m unittest discover -v -f modules/connectors/postnord/tests` green
- [ ] PDF fixtures assert identical output before/after the change
- [ ] Spec-gap note committed to `docs/notes/postnord/`

**Nice-to-have (P1):**
- [ ] Live re-verification of the ZPL endpoint against the test account

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Full ZPL support (endpoint select + normalize) | Completes documented knob; honors carrier contract | More surface than parser-only | **Selected** |
| Parser robustness only (stay on PDF) | Smallest diff | Documented setting stays dead; ZPL customers unserved | Rejected (D1) |
| Content sniffing (detect `^XA`/`%PDF` magic) | Immune to wrong `encoding` values | Reinvents a field the response already carries; brittle for short/empty payloads | Rejected (D3) |
| Always book PDF, convert to ZPL via Labelary (`zpl_to_pdf` inverse) | One endpoint to maintain | External HTTP dependency in label path; fidelity loss; UPS-style conversion exists for a different reason (enforced PDF output) | Rejected |

### Trade-off Analysis

Trusting `printout.encoding` keeps the parser declarative and per-printout, which matters because PostNord composes responses item by item (mixed success/fault items already occur — see `PartialFailureResponse` fixture). Sniffing would couple the parser to ZPL/PDF syntax details that belong to the carrier, not to karrio.

---

## Technical Design

### Existing Code Analysis

| Component | Location | Reuse Strategy |
|-----------|----------|----------------|
| `lib.bundle_base64` / `bundle_zpls` | `modules/sdk/karrio/core/utils/helpers.py:107-131` | Reused as-is once inputs are normalized to base64 |
| `lib.encode_base64` | `modules/sdk/karrio/lib.py` | UTF-8 bytes → base64 for raw ZPL printouts |
| SmartKargo label-type flow | `modules/connectors/smartkargo/karrio/providers/smartkargo/shipment/create.py:159-160`, `proxy.py:39` | Reference for resolution chain + ctx threading |
| `ConnectionConfig.label_type` | `modules/connectors/postnord/karrio/providers/postnord/units.py:10` | Already defined (default `PDF`); becomes consumed |
| `LabelType` StrEnum | `units.py:23-31` | Maps unified `ZPL_4x6`/`PDF_4x6` to carrier values |
| Generated schema `PrintoutType.encoding` | `karrio/schemas/postnord/shipment_response.py:74-78` | Read per printout; no regeneration needed |
| Server label serving (incl. zpl token type) | `apps/api/karrio/server/urls/tokens.py:57` | Confirms downstream base64 expectation; no change required |

### Architecture Overview

```
┌────────────────────┐
│ ShipmentRequest    │  label_type="ZPL" (request override)
│ (unified payload)  │  or connection_config.label_type
└─────────┬──────────┘
          │ shipment_request()
          ▼
┌────────────────────┐     ctx = {shipment_id, label_type}
│ provider           │────────────────────────┐
│ shipment/create.py │                        │
└─────────┬──────────┘                        │
          │ Serializable(request, ctx)        │
          ▼                                   ▼
┌────────────────────┐              ┌─────────────────────┐
│ proxy              │  label_type  │  endpoint select    │
│ create_shipment    │─────────────>│  ZPL → /labels/zpl  │
└─────────┬──────────┘              │  else → /labels/pdf │
          │                         └─────────────────────┘
          │ POST
          ▼
┌────────────────────┐
│ PostNord Booking   │
│ /rest/shipment/v3/ │
│ edi/labels/{zpl│pdf}│
└─────────┬──────────┘
          │ labelPrintout[]: {encoding, data, labelFormat}
          ▼
┌────────────────────┐   encoding=base64 ──> pass through
│ _printout_base64   │────────────────────────────────────┐
│ (normalize)        │   encoding=none/absent             │
└─────────┬──────────┘   → lib.encode_base64(utf-8) ─────┤
          │                                               │
          ▼ all base64                                    │
┌────────────────────┐                                    │
│ single → pass      │                                    │
│ multi  → bundle_   │                                    │
│         base64     │                                    │
└─────────┬──────────┘                                    │
          ▼                                               ▼
┌──────────────────────────────────────────────────────────┐
│ Documents(label=<base64>), ShipmentDetails.label_type    │
└──────────────────────────────────────────────────────────┘
```

### Data Flow Diagram (encoding normalization)

```
┌───────────────────────────── RESPONSE FLOW ──────────────────────────────┐
│                                                                          │
│  PDF endpoint:  printout{encoding:"base64", data:"JVBERi0x…"}           │
│       ────────────────────────────────> unchanged pass-through          │
│                                                                          │
│  ZPL endpoint:  printout{encoding:"none", data:"^XA\n^LL1520\n…"}       │
│       ───> lib.encode_base64(data.encode("utf-8"))                      │
│       ───> "XlhBXkxM…"(base64) ──> identical downstream path            │
│                                                                          │
│  multi ZPL:    [b64(zpl1), b64(zpl2)]                                   │
│       ───> lib.bundle_base64(list, "ZPL")                               │
│       ───> base64( zpl1 + "\n" + zpl2 )   (bundle_zpls join)            │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### Field Reference

| Karrio field | Carrier field | Mapping |
|--------------|---------------|---------|
| `ShipmentDetails.label_type` | `printout.labelFormat` | direct; falls back to requested type from `ctx` when absent |
| `Documents.label` | `printout.data` | base64 passthrough or UTF-8→base64 encode per `printout.encoding` |
| `ShipmentRequest.label_type` | endpoint path segment | `ZPL` → `/labels/zpl`, else `/labels/pdf` |
| `connection_config.label_type` | endpoint path segment | same, lower precedence than request field |

---

## Edge Cases & Failure Modes

### Edge Cases

| Scenario | Expected Behavior | Handling |
|----------|-------------------|----------|
| ZPL response omits `labelFormat` | `label_type` falls back to requested type from ctx, not hardcoded `"PDF"` | ctx threading |
| ZPL response omits `encoding` entirely | Treated as raw text (same as `"none"`), encoded | non-`base64` → encode branch |
| Mixed-format printouts in one response (not observed) | First printout's `labelFormat` wins, as today | preserved existing behavior |
| Empty `data` on a printout | Skipped from label list, as today | existing filter retained |
| `payload.label_type = "ZPL_4x6"` (unified value) | Maps to carrier `ZPL` via `LabelType` | StrEnum alias mapping |
| PDF response with `encoding: "base64"` (today's path) | Byte-identical behavior | normalization is identity on base64 |

### Failure Modes

| What Can Go Wrong | Impact | Mitigation |
|-------------------|--------|------------|
| PostNord changes ZPL transport encoding to base64 | Double-encode risk | `encoding == "base64"` branch passes through — only an explicit `"none"`/absent value encodes |
| ZPL endpoint unavailable for a customer's product | Booking error message from carrier | Existing error parsing surfaces `compositeFault` unchanged |
| Bundled ZPL corrupt (bad join) | Unprintable label | Round-trip unit test decodes bundle and compares to joined source |

---

## Implementation Plan

### Phase 1: Parser encoding normalization

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Add `_printout_base64` normalization; use it in `label_data`; `label_type` fallback to ctx | `modules/connectors/postnord/karrio/providers/postnord/shipment/create.py` | Pending | S |
| Thread `label_type` into `Serializable` ctx | same file, `shipment_request()` | Pending | S |

### Phase 2: Proxy endpoint selection

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Resolve label type from ctx; select `/labels/zpl` vs `/labels/pdf` | `modules/connectors/postnord/karrio/mappers/postnord/proxy.py` | Pending | S |

### Phase 3: Tests

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| ZPL response fixture + parse test (base64-of-ZPL assertion) | `modules/connectors/postnord/tests/postnord/test_shipment.py` | Pending | M |
| ZPL proxy URL test (request-level and config-level) | same | Pending | S |
| Multi-printout ZPL bundling test | same | Pending | S |
| ZPL gateway fixture | `modules/connectors/postnord/tests/postnord/fixture.py` | Pending | S |

### Phase 4: Documentation

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| README: `label_type` row notes ZPL support | `modules/connectors/postnord/README.md` | Pending | S |
| Spec-gap note: `encoding: "none"` on ZPL endpoint, provenance and evidence | `docs/notes/postnord/zpl-label-encoding.md` | Pending | S |

**Dependencies:** Phase 2 consumes Phase 1's ctx; Phase 3 covers both; Phase 4 last.

---

## Testing Strategy

### Test Cases

#### Unit Tests (unittest, connector suite)

```python
def test_create_shipment_zpl_url(self):
    # Request-level label_type selects the ZPL endpoint.
    payload = {**ShipmentPayload, "label_type": "ZPL"}
    with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
        mock.return_value = "{}"
        karrio.Shipment.create(models.ShipmentRequest(**payload)).from_(gateway)
        self.assertEqual(
            mock.call_args[1]["url"],
            f"{gateway.settings.server_url}/rest/shipment/v3/edi/labels/zpl?apikey=TEST_API_KEY",
        )

def test_parse_shipment_response_zpl(self):
    # encoding "none" + raw ZPL -> base64-of-ZPL in docs.label, label_type ZPL.
    with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
        mock.return_value = ShipmentZPLResponse
        parsed = (
            karrio.Shipment.create(
                models.ShipmentRequest(**{**ShipmentPayload, "label_type": "ZPL"})
            ).from_(gateway).parse()
        )
        details, _ = parsed
        self.assertEqual(details.label_type, "ZPL")
        self.assertEqual(
            details.docs.label,
            lib.encode_base64(RawZPLData.encode("utf-8")),
        )
```

Bundling test asserts a decode round-trip:
`lib.to_buffer(details.docs.label)` (or `base64.b64decode`) equals
`zpl1 + "\n" + zpl2`, proving the normalize-then-bundle pipeline.

### Running Tests

```bash
source bin/activate-env
python -m unittest discover -v -f modules/connectors/postnord/tests
```

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| PDF path regression | High | Low | PDF fixtures assert identical output; normalization is identity on base64 |
| Wrong assumption about ZPL `labelFormat` presence | Low | Medium | ctx fallback; noted in edge cases |
| Bundling changes existing PDF multi-label output | Medium | Low | `bundle_pdfs` path untouched; normalization happens before it |
| Live ZPL behavior differs from capture (e.g. per-product) | Medium | Low | Spec-gap note records observation provenance for future diff |

---

## Migration & Rollback

### Backward Compatibility

- **Default label type is `PDF`**: connections without `label_type` config and requests without the field hit the same endpoint and parse identically.
- **No schema regeneration**: the generated `PrintoutType` already carries `encoding`; nothing in `schemas/*.json` changes.
- **No server/dashboard changes**: `Documents.label` remains base64 for all formats.

### Rollback Procedure

1. Revert the three commits (parser, proxy, tests) — no data migrations, no settings migrations involved.
2. Re-run connector suite to confirm green on the pre-change fixtures.

---

## Appendices

### Appendix A: Observed ZPL transport contract (2026-09-03, live capture)

```json
"labelPrintout": [{
  "printout": {
    "type": "LABEL",
    "encoding": "none",
    "data": "^XA\n^LL1520\n^FX utf-8^FS    ^CI28\n^PON\n^XA\n^CWW,E:ARI000.TTF\n…"
  }
}]
```

- `^CI28` declares UTF-8 (ZPL has no BOM concept; `^FX utf-8` is a comment).
- `^CWW,E:…TTF` lines are `^CW` font-designator assignments (printer-memory Arial fonts) — format payload, not transport metadata.
- `^LL1520` = 190 mm at 8 dpmm, matching the swagger's Labelary instruction "Set LabelSize to 105x190mm" (`booking.swagger.json:486`).
- Swagger `encoding` definition documents only `(base64)` with no enum (`booking.swagger.json:3947-3952`); `"none"` is observed-only.

### Appendix B: Carrier-Specific Reference

| Item | Value |
|------|-------|
| ZPL booking endpoint | `POST /rest/shipment/v3/edi/labels/zpl` (`createEDILabelZPL`) |
| PDF booking endpoint | `POST /rest/shipment/v3/edi/labels/pdf` |
| ZPL-specific param | `multiZPL` (query, default `false`) — out of scope, default kept |
| Spec viewer guidance | http://labelary.com/viewer.html, 105x190mm |
| Karrio ZPL bundler | `modules/sdk/karrio/core/utils/helpers.py:107` (`bundle_zpls`) |
| Reference connector | SmartKargo (`label_type` resolution + endpoint switch) |
