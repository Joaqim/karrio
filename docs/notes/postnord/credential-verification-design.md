---
title: PostNord per-product credential verification design
---

# PostNord per-product credential verification design

Provenance: extracted from `PRDs/PRD_POSTNORD_CREDENTIAL_VERIFICATION.md` on branch `backup-develop-2026-09-24` (last commit `884cdf58a`, PRD dated 2026-06-25, status Planning).

This is design history and is not implemented.
As of `develop` at `ecb449c43` (2026-09-28) the connector has no `validate_credentials` method, and the upstream-bound `PRDs/PRD_POSTNORD_INTEGRATION.md` carries only a short "Per-product credential verification" stub under Future Work.

## Live finding

PostNord authorizes each API product (Booking, Transit Time, Service Points, Tracking) separately per API key, and an unauthorized product returns `403 "Invalid API Key"` even when the same key works for other products.
The PRD records this as verified live: the configured key returned 403 on Booking and Transit Time, while a different developer key generated sandbox labels.
The runtime side of this was handled separately: `develop` turns the gateway 403 into an explicit authorization message (`modules/connectors/postnord/karrio/providers/postnord/error.py:94-108,161`).
What remained unaddressed is proactive verification, since a merchant otherwise discovers a missing product authorization as a failed label purchase.

## Proposed design

The PRD proposed a connector-local, duck-typed `validate_credentials` proxy method, following the `validate_address` and `find_service_points` proxy-method pattern, that probes each product and returns a per-product status rather than a single boolean (decisions CV1 and CV2).
Classification would reuse the gateway error parsing in `error.py`: a 403 gateway envelope maps to `unauthorized`, a 200 to `authorized`, and anything else, including network errors and 5xx responses, to `unknown`.
Only a 403 counts as `unauthorized`, so a transient failure never reports a key as unauthorized.
A key authorized for no product still saves as a connection; the result only surfaces the status.

| Product | Probe (side-effect free) | authorized | unauthorized | unknown |
|---|---|---|---|---|
| Transit Time | `GET /rest/transport/v2/transittime/addresstoaddress` | 200 | 403 | network or 5xx |
| Service Points | `GET /rest/businesslocation/v5/servicepoints/nearest/byaddress` | 200 | 403 | network or 5xx |
| Tracking | `GET /rest/links/v1/tracking/{cc}/{id}` | 200 | 403 | network or 5xx |
| Booking | `GET /v3/edi/labels/manage/health` (pending Q1) | 200, if apikey-gated | 403 | health endpoint bypasses auth |

## Probe safety (CV3)

Every probe must be side-effect free.
A probe must never create a shipment, in production or sandbox, to test Booking authorization, and the PRD's test plan asserted that no probe issues a `POST` to `/rest/shipment/v3/edi/labels`.

## Open questions

Q1 asked whether any side-effect-free, apikey-authorized call exercises the same authorization scope as `POST /v3/edi/labels/pdf`.
The candidate `GET /v3/edi/labels/manage/health` exists in the vendored booking specification (`modules/connectors/postnord/vendor/booking.swagger.json:2254-2260`, "Returns the health of the API"), but health endpoints often bypass authentication, so it needs a live test to confirm it is apikey-gated and product-scoped.
The alternatives the PRD listed were to accept that Booking can only be validated on the first real booking, or to send a deliberately invalid minimal booking and distinguish 403 from 400.
If the probe cannot distinguish, Booking is reported as `unknown`.
Q2 asked whether Phase 1 should expose only the proxy method or also a thin REST or GraphQL pass-through.
Neither question was resolved.

## Phase 2: server test connection

The PRD deferred a server-side "test connection" feature to an optional Phase 2: a `POST /v1/connections/{id}/check` endpoint or GraphQL mutation that calls `validate_credentials` when the connector provides it, plus a dashboard "Test connection" button showing per-product status.
It noted that karrio has no configuration-time validation hook (`server/providers/serializers/base.py` and the graph mutations), so Phase 2 needs a new endpoint.
Validating automatically on connection create or update was rejected because it couples persistence to carrier latency and failure, and because one save-time probe cannot cover PostNord's per-product model.
A first-class karrio `validate_credentials` SDK contract reusable across carriers was named as the right long-term home but deferred as a cross-cutting core change.
The PRD also noted a pre-existing concern: PostNord takes the API key in the query string, and SDK tracing persists it.
