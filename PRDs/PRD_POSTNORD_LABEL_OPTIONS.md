# PostNord label format options (PDF/ZPL) and physical label size

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-07-28 |
| Status | Completed |
| Owner | Connectors |
| Type | Enhancement |
| Reference | [AGENTS.md](../AGENTS.md) |

---

## Executive Summary

The PostNord connector books a shipment and retrieves its label in a single call.
Before this change the call was hard-wired to the PDF endpoint and exposed a `label_type` config option that was accepted but never consulted, alongside a dead `label_format` (`A4`) option that PostNord's booking surface has no field for.
This enhancement makes the label file format selectable per request (`PDF` or `ZPL`) and adds a per-connection physical label size (`standard`/`small`/`ste`), threading both through the existing request context without changing any other behavior.

### Key architecture decisions

PostNord exposes the label file format only through the endpoint path — `/rest/shipment/v3/edi/labels/pdf` versus `/rest/shipment/v3/edi/labels/zpl` — not through a body or query field.
Both endpoints accept the identical `ediInstruction` body and return the identical `ediLabelResponse`, so the format resolution happens in the provider layer and is threaded to the proxy via `Serializable.ctx`, where the proxy picks the path.
The physical label size is an orthogonal `labelType` query parameter shared by both endpoints, so it is carried as a connection-config option and appended by the existing `_url` helper, which drops `None` values.

### Scope

In scope: a `LabelType` enum (`PDF`/`ZPL` with `PDF_4x6`/`ZPL_4x6` aliases), a `LabelSize` enum (`standard`/`small`/`ste`), retyping the `label_type` connection option, adding a `label_size` connection option, removing the dead `label_format` option, endpoint routing in the proxy, format resolution in `shipment/create.py`, and tests.
Out of scope: any change to `issuerCode` party stamping, the letter-service rate gating, the service catalog, tracking, rating, or pickup.

## Open questions & decisions

### Resolved decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| D12 | Label file format & physical size | Per-request `label_type` (`PDF`/`ZPL`) resolved payload → connection default → `PDF`, selected by endpoint path; connection-config `label_size` (`standard`/`small`/`ste`) sent as the `labelType` query param, unset → omitted | Format lives only in the endpoint path, so it is resolved in the provider and threaded via ctx to the proxy. Size is a shared query param handled by `_url`. The dead `label_format` (`A4`) option is removed. |

Both decisions are recorded canonically in `PRD_POSTNORD_INTEGRATION.md` (D12) with the integration decision log; this PRD is the design detail for that entry.

### Superseded direction

An earlier exploration bundled these label options with an origin-derived `issuerCode`: deriving the consignor `issuerCode` from the shipper's origin country and rejecting non-Nordic origins at request-build time.
That direction was rejected and is not part of this change.
`issuer_code` encodes the merchant's PostNord market agreement and is load-bearing for letter-service rate gating — it is read in `settings.shipping_services` and `is_service_available` to gate services `34` (tracked letter) and `UX` (export letter) — so it cannot be inferred from a single shipment's origin and remains a user-set connection setting.
The label options here were adopted independently, leaving the `issuerCode` party stamping untouched.
This rejection is recorded as D13 in `PRD_POSTNORD_INTEGRATION.md`.

## Problem statement

### Current state

The proxy always posted to the PDF endpoint, and the file format the caller asked for was ignored:

```python
# proxy.create_shipment (before)
response = lib.request(
    url=self._url("/rest/shipment/v3/edi/labels/pdf"),
    data=lib.to_json(request.serialize()),
    ...
)
```

`ConnectionConfig` declared two label options, one ignored and one meaningless:

```python
label_type = lib.OptionEnum("label_type", str, "PDF")   # accepted, never read
label_format = lib.OptionEnum("label_format", str, "A4")  # no PostNord field exists
```

### Desired state

A caller selects the file format per request via the unified `payload.label_type`, or sets a per-connection default, and optionally pins a physical size:

```python
# proxy.create_shipment (after) — path chosen from the threaded ctx
ctx = request.ctx or {}
label_path = lib.identity(
    "/rest/shipment/v3/edi/labels/zpl"
    if ctx.get("label_type") == "ZPL"
    else "/rest/shipment/v3/edi/labels/pdf"
)
response = lib.request(
    url=self._url(label_path, labelType=self.settings.connection_config.label_size.state),
    ...
)
```

## Technical design

### Existing code analysis

The resolution/threading pattern reuses the connector's established `Serializable.ctx` mechanism.
`shipment_request` already returns `lib.Serializable(request, lib.to_dict, dict(shipment_id=...))`, and `_extract_details` already reads `ctx.get("shipment_id")`; the label format joins that same ctx dict.
The `_url(path, **params)` helper already appends the apikey and drops `None`-valued params, so an unset `label_size` naturally omits the `labelType` query parameter.
Format resolution uses the carrier `Enum.map(...).value` idiom used throughout the connector's `units.py`.

### Architecture overview

```
                 payload.label_type ─┐
                                     │  resolve: payload → connection default → PDF
 shipment/create.py  ────────────────▶  label_type ∈ {PDF, ZPL}
        │                            │
        │  Serializable.ctx = {shipment_id, label_type}
        ▼                            ▼
 mappers/proxy.create_shipment ── ctx.get("label_type") == "ZPL" ?
        │                                    │
        │  path = /labels/zpl  ◀─── yes ─────┤
        │  path = /labels/pdf  ◀─── no  ─────┘
        │
        │  _url(path, labelType = connection_config.label_size.state)
        │            (None size → param dropped)
        ▼
   POST https://…/rest/shipment/v3/edi/labels/{pdf|zpl}?apikey=…[&labelType=small]
```

### Sequence diagram

```
Caller        SDK/create.py          Proxy                 PostNord
  │  ShipmentRequest  │                 │                      │
  │  (label_type?)    │                 │                      │
  ├──────────────────▶│                 │                      │
  │        resolve format               │                      │
  │        (payload → cfg → PDF)        │                      │
  │        ctx={shipment_id,            │                      │
  │             label_type}             │                      │
  │                   ├────────────────▶│                      │
  │                   │  pick path from ctx.label_type         │
  │                   │  append labelType=size (or omit)       │
  │                   ├─────────────────────────────────────▶ │
  │                   │              POST /labels/{pdf|zpl}    │
  │                   │◀─────────────────────────────────────┤
  │                   │              ediLabelResponse          │
```

### Data flow

The unified request field `payload.label_type` (already on `models.ShipmentRequest`) is the per-request override.
When unset, resolution falls through to the connection default `settings.connection_config.label_type.state`, and finally to `LabelType.PDF`.
The resolved value is a plain string (`"PDF"`/`"ZPL"`) so the proxy's `ctx.get("label_type") == "ZPL"` comparison is exact.
`label_size` never enters the request body; it is read directly from the connection config at proxy time.

### Data models

```python
class LabelType(lib.StrEnum):
    PDF = "PDF"
    ZPL = "ZPL"
    PDF_4x6 = PDF   # unified alias
    ZPL_4x6 = ZPL   # unified alias


class LabelSize(lib.StrEnum):
    standard = "standard"   # 190×105mm
    small = "small"         # 75×105mm
    ste = "ste"             # 190×105mm, PDF-only


class ConnectionConfig(lib.Enum):
    label_type = lib.OptionEnum("label_type", LabelType, "PDF")
    label_size = lib.OptionEnum("label_size", LabelSize)  # unset → None → omitted
```

### Field reference

| Field | Source | Type | Default | Effect |
|-------|--------|------|---------|--------|
| `label_type` | `payload.label_type` (per request) | `PDF`/`ZPL` | falls to connection default | Selects the endpoint path |
| `label_type` | connection config | `LabelType` | `PDF` | Per-connection default file format |
| `label_size` | connection config | `LabelSize` | unset | `labelType` query param; unset omits it |

## Edge cases & failure modes

An unset `label_size` omits the `labelType` parameter entirely, letting PostNord apply its own `standard` default; the connector never fabricates a size.
An unrecognized `payload.label_type` resolves through `LabelType.map(...).value or LabelType.PDF.value`, so it falls back to `PDF` rather than producing an invalid path.
The `ste` size is PDF-only; on the ZPL endpoint PostNord ignores/defaults it, which is acceptable and needs no client-side guard.

### Security considerations

No new credentials, headers, or tenant-scoped data are introduced.
The apikey continues to travel only via the existing `_url` helper.

## Implementation plan

The change is a single additive phase touching the provider units, the provider shipment builder, the proxy, and the tests.

| File | Change |
|------|--------|
| `karrio/providers/postnord/units.py` | Add `LabelType`/`LabelSize`; retype `label_type`; add `label_size`; remove `label_format` |
| `karrio/providers/postnord/shipment/create.py` | Resolve format; thread `label_type` into `Serializable.ctx` |
| `karrio/mappers/postnord/proxy.py` | Route `/labels/{pdf,zpl}` from ctx; append `labelType` size param |
| `tests/postnord/fixture.py` | Add `gateway_small_label`, `gateway_zpl_label` |
| `tests/postnord/test_shipment.py` | Add `TestPostNordLabel` cases |

## Testing strategy

Tests use `unittest` and mock `karrio.mappers.postnord.proxy.lib.request`, asserting on the outgoing URL — no live PostNord call.

| Test | Assertion |
|------|-----------|
| `test_create_shipment_zpl_routes_zpl_endpoint` | `payload.label_type="ZPL"` → URL contains `/labels/zpl` |
| `test_create_shipment_config_label_type_routes_zpl_endpoint` | Connection default `label_type="ZPL"`, payload unset → `/labels/zpl` |
| `test_create_shipment_defaults_pdf_endpoint` | Payload/connection unset → `/labels/pdf` |
| `test_create_shipment_label_size_query` | `label_size="small"` → URL contains `labelType=small` |
| `test_create_shipment_default_label_size_absent` | Unset `label_size` → no `labelType` in URL |

The existing `TestPostNordShipment.test_create_shipment` retains its exact-URL assertion against the default gateway, confirming the default path stays `/labels/pdf?apikey=…` with no size parameter.
Run from the repository root:

```bash
python -m unittest discover -v -f modules/connectors/postnord/tests
```

## Migration & rollback

The `label_type` default (`PDF`) preserves prior behavior for connections that set nothing, so the change is backward compatible at the request level.
The only removed surface is the dead `label_format` (`A4`) config option, which was never read; connections that set it see no behavioral change because it had none.
Rollback is a straight revert of the four source files plus the tests.
