# PostNord Letter-Service Rate Gating

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-07-07 |
| Status | Planning |
| Type | Enhancement |
| Reference | [AGENTS.md](../AGENTS.md), [docs/notes/postnord/swagger-ingestion-findings.md](../docs/notes/postnord/swagger-ingestion-findings.md) |

## Executive summary

PostNord letter products — `basicServiceCode` `34` (Tracked Letter) and `UX` (Export Letter Sweden) — are defined in the `ShippingService` enum but were deliberately kept out of the rate catalog (`DEFAULT_SERVICES`), so they can never surface as rates. Merchants who ship these products see only the two internationally-flagged parcel/freight services. This enhancement makes letter products rateable, but gates their availability behind an issuer-code constraint and per-service opt-in toggles so the default behavior is unchanged and the mechanism generalizes to any future gated service.

## Problem statement

For an international rate request the universal rating engine offers only services whose `international is True` with a matching zone. Today exactly two `DEFAULT_SERVICES` entries qualify (`postnord_postpaket_utrikes` / 91, `postnord_road_freight_europe` / 84). Codes `34` and `UX` are absent from `DEFAULT_SERVICES` entirely (they live in the enum-only "letters & registered mail" group), so no toggle or rate sheet can surface them. The requirement is to expose `34`/`UX` as rateable while keeping them off by default and correctly scoped to the merchant's market.

## Existing code analysis

| Component | Location | Relevant behavior |
|---|---|---|
| Rate catalog | `providers/postnord/units.py::DEFAULT_SERVICES` | 20 `ServiceLevel` entries; `34`/`UX` absent |
| Service enum | `providers/postnord/units.py::ShippingService` | `postnord_tracked_letter = "34"`, `postnord_export_letter = "UX"` already defined |
| Config toggles | `providers/postnord/units.py::ConnectionConfig` | `lib.OptionEnum(name, bool, False)` pattern (`enable_transit_times`) |
| Toggle read | `mappers/postnord/proxy.py` | `self.settings.connection_config.<flag>.state` |
| Issuer code | `providers/postnord/utils.py::IssuerCode`, `mappers/postnord/settings.py` | `issuer_code` on settings, default `"Z12"`; Z11–Z14 enum |
| Service list hook | `mappers/postnord/settings.py::shipping_services` | returns `self.services` or `DEFAULT_SERVICES`; single choke point read by the rating engine |
| Rating engine | `universal/mappers/rating_proxy.py::get_available_rates` | filters by `active`, `domicile`/`international`, zone, weight/dims — no metadata gating hook |
| UI form | `sdk/karrio/references.py` | schema-driven; new `ConnectionConfig` members auto-render as toggles, no dashboard code |

Key consequence: because `get_available_rates` reads `settings.shipping_services`, gating can be applied purely by filtering that list — the universal engine needs no change, and the dashboard picks up the new toggles automatically.

## Technical design

A declarative availability layer keyed by `service_code`. Services absent from the registry are unconditionally offered (preserving today's catalog). A gated service is offered only when the connection's `issuer_code` is permitted and its required opt-in toggle is enabled.

```
                 shipping_services (mapper settings.py)
                              |
        services = self.services or DEFAULT_SERVICES
                              |
          filter: is_service_available(code, issuer, config)
             |                                   |
   code not in SERVICE_AVAILABILITY      code in SERVICE_AVAILABILITY
             |                                   |
          keep (default)              issuer allowed?  AND  required toggle on?
                                          |    \                |      \
                                        yes    no             on      off
                                          |     \              |        \
                                        keep    drop         keep       drop
                              |
                get_available_rates (universal, unchanged)
```

Gating rules:

| service_code | carrier code | allowed issuer | required toggle |
|---|---|---|---|
| `postnord_tracked_letter` | 34 | any | `offer_tracked_letter` |
| `postnord_export_letter` | UX | Z12 (Sweden) | `offer_export_letter` |

Both toggles default `False` (opt-in). `34` surfaces on international routes once its toggle is on; `UX` additionally requires the Sweden issuer, matching the "Export Letter Sweden" product scope.

New `DEFAULT_SERVICES` entries mirror `postnord_postpaket_utrikes`: `international=True`, `domicile=False`, unrestricted `International` zone, `rate=0.0` placeholder (overridden by the merchant rate sheet).

## Edge cases

- `issuer_code` may arrive as the `IssuerCode` enum member or the raw `"Z12"` string; normalize to the member name before comparison.
- Registry `required_config` names must reference real `ConnectionConfig` members; a missing option is treated as "not enabled" (fail closed).
- Merchant rate sheets that already list letter services still pass through the same filter, so gating holds regardless of catalog source.

## Implementation plan

| # | File | Change |
|---|---|---|
| 1 | `providers/postnord/units.py` | Add `postnord_tracked_letter` (34) and `postnord_export_letter` (UX) to `DEFAULT_SERVICES` |
| 2 | `providers/postnord/units.py` | Add `offer_tracked_letter` / `offer_export_letter` to `ConnectionConfig` |
| 3 | `providers/postnord/units.py` | Add `ServiceAvailabilityRule`, `SERVICE_AVAILABILITY`, `is_service_available(...)` |
| 4 | `mappers/postnord/settings.py` | Filter `shipping_services` through `is_service_available` using `issuer_code` + `connection_config` |
| 5 | `tests/postnord/fixture.py` | Add letter-service fixtures + gateways (toggles off / on / Z11) |
| 6 | `tests/postnord/test_rate.py` | Assert letters hidden by default, offered when enabled, `UX` requires Z12 |

## Testing strategy

`unittest` via `python -m unittest discover -v -f modules/connectors/postnord/tests`. New assertions on the offered `rate.service` set for an international payload:

- Toggles off → `{postnord_postpaket_utrikes}` only.
- Both toggles on (Z12) → includes `postnord_tracked_letter` and `postnord_export_letter`.
- Both toggles on (Z11) → includes `postnord_tracked_letter`, excludes `postnord_export_letter`.

The existing 8 `TestPostNordRating` methods must remain green (fixture services are ungated, so unchanged).

## Risk assessment

Low. The change is additive and gated closed by default; the universal engine and dashboard are untouched. The only behavioral change for an existing connection is the two new catalog entries, which stay hidden until a merchant opts in.
