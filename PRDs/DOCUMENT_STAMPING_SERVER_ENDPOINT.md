# Document Stamping Server Endpoint

| Field | Value |
|-------|-------|
| Project | Karrio |
| Version | 1.0 |
| Date | 2026-09-22 |
| Status | Planning — decision record for OpenSpec change `add-document-stamping`, task 5.2 |
| Owner | Joaqim Planstedt |
| Type | Enhancement / Architecture |
| Reference | [AGENTS.md](../AGENTS.md), [DOCUMENT_STAMPING_UTILITY.md](./DOCUMENT_STAMPING_UTILITY.md) |

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Open Questions & Decisions](#open-questions--decisions)
3. [Problem Statement](#problem-statement)
4. [Goals & Success Criteria](#goals--success-criteria)
5. [Alternatives Considered](#alternatives-considered)
6. [Technical Design](#technical-design)
7. [Edge Cases & Failure Modes](#edge-cases--failure-modes)
8. [Implementation Plan](#implementation-plan)
9. [Testing Strategy](#testing-strategy)
10. [Risk Assessment](#risk-assessment)
11. [Migration & Rollback](#migration--rollback)
12. [Appendices](#appendices)

---

## Executive Summary

The SDK stamping utility `lib.stamp_document` (cemented by
[DOCUMENT_STAMPING_UTILITY.md](./DOCUMENT_STAMPING_UTILITY.md) and shipped at
`modules/sdk/karrio/core/utils/stamping.py`) composites a base64 signature or
letterhead onto a returned carrier document (PDF or ZPL) and returns a document
of the same format. SDK consumers can call it directly; API consumers cannot.
This PRD designs the server surface that closes that gap: a REST endpoint on the
documents module that mirrors `POST /documents/generate` — validating a
base64-in request through a DRF serializer, invoking `lib.stamp_document`, and
returning the composited document as base64 — so an API consumer gets the same
format-blind stamping SDK consumers already have.

The server phase was gated on question Q7 of the OpenSpec change (does a
generalized server surface over an SDK utility already exist in karrio?). The
group-5.1 precedent survey (`docs/notes/documents/stamping-server-precedent-survey.md`)
answered yes and unblocked the phase. This PRD converts that go verdict into a
concrete endpoint design and hands it to task 5.2. No new SDK behavior is in
scope: the utility already exists and is unchanged; this is a thin, tenant-aware
HTTP wrapper over it.

### Key Architecture Decisions

1. **REST endpoint mirroring `POST /documents/generate`**: the closest in-tree
   precedent (`DocumentGenerator.post`, `templates.py:167`) is REST, and its
   base64-in / base64-out serializer idiom maps onto stamping with almost no
   adaptation; GraphQL exposure is deferred, not rejected (Q1).
2. **Synchronous request handling, no Huey**: stamping is in-process, pixel-only
   (pypdf + Pillow), and involves no network; it matches the synchronous
   `DocumentGenerator` precedent rather than the batch/tracking Huey path (D3).
3. **Stateless base64-in surface at launch**: the document to stamp arrives as
   base64 in the request body, exactly as the SDK utility takes it; there is no
   stored resource to fetch, so no org-scoped queryset is needed and
   authentication is the whole tenancy story (D4). A stored-document / org-keyed
   variant is deliberately out of scope (Q2).
4. **`carrier`/`doc_type` drive a server-resolved registry, not a client
   callable**: the SDK `registry` parameter is a Python `RegistryLookup`
   callable and cannot cross an HTTP boundary; the endpoint accepts only the
   `carrier`/`doc_type` scalars and lets the server resolve the built-in seed
   registry (D5).
5. **API-log skip carried over**: like `DocumentGenerator`, the view subclasses
   `api.BaseAPIView` and skips the logging mixin because base64 document
   responses bloat `APILogIndex` (D6).
6. **Utility errors map to 400, not 500**: `lib.stamp_document` raises
   `ValueError` on PNG documents, registry misses, ZPL underlays, and unbacked
   formats; these are client-input faults and translate to the module's
   `ErrorResponse` 400 shape, mirroring the `TemplateRenderingError` → 400
   handling (D7).

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| REST endpoint wrapping `lib.stamp_document` on the documents module | Any change to `lib.stamp_document` or the SDK stamping backends |
| Request/response DRF serializers (document base64 in, placement/rotation/date/layer/carrier/doc_type/graphic_name; stamped base64 out) | GraphQL mutation surface (deferred, Q1) |
| Synchronous handling, `ErrorResponse` mapping, API-log skip | Batch/bulk stamping via Huey (future, D3) |
| Authentication-gated, stateless base64-in path | Stored-document / org-scoped stamping of a persisted shipment doc (Q2) |
| Django (`karrio test`) endpoint tests and fixtures | Storing or verifying stamped documents server-side (inherited D8 from the utility PRD) |

---

## Open Questions & Decisions

### Pending Questions

| # | Question | Context | Options | Status |
|---|----------|---------|---------|--------|
| Q1 | Should the stamping surface be REST-only at launch, or also a GraphQL mutation? | The documents module supports both; template CRUD has a GraphQL analogue, but document *generation* (the nearest precedent) is REST-only. The 5.1 survey explicitly left this unresolved (`stamping-server-precedent-survey.md:65`). | A) REST-only at launch (recommended, mirrors generate), B) REST + GraphQL, C) GraphQL-only | ✅ Resolved 2026-09-22 (human): A — REST-only at launch (see D1) |
| Q2 | Is a stored-document / org-keyed variant in scope — stamping a document already persisted against an org's shipment, rather than one passed as base64? | The stateless base64-in path needs no org scoping; a stored-document path would need `access_by` / `validate_resource_token` like the printers (`printers.py:78`). The survey flagged "raw base64 vs stored reference" as an open design question (`stamping-server-precedent-survey.md:64`). | A) Base64-in only at launch (recommended), B) Add a stored-shipment-document reference path now | ✅ Resolved 2026-09-22 (human): A — base64-in only, no storage at launch (see D4) |
| Q3 | What is the exact request payload limit, and does the module's default DRF/body-size configuration accommodate a base64 document plus a base64 image? | The request carries two base64 blobs (document + PNG); the survey noted payload limits "should be confirmed" (`stamping-server-precedent-survey.md:62`). | A) Confirm existing limits suffice, B) Set an explicit ceiling with a 413 response | ⏳ Design phase |
| Q4 | On a utility `ValueError`, is 400 correct for every case, or should a registry miss be 409 (conflict / not-found-seed) instead of 400? | `DocumentGenerator` uses 400 for render errors and 404 for a missing template id; the survey suggested 400/409 (`stamping-server-precedent-survey.md:63`). | A) All utility ValueErrors → 400, B) Registry miss → 409, others → 400 | ⏳ Design phase |

### Resolved Decisions

| # | Decision | Choice | Rationale | Date |
|---|----------|--------|-----------|------|
| D1 | Protocol | REST endpoint mirroring `POST /documents/generate` | `DocumentGenerator.post` (`templates.py:167`) is the co-located precedent Q7's survey identified; it is REST, and its `DocumentData`/`GeneratedDocument` idiom maps directly onto stamping I/O | 2026-09-22 |
| D2 | URL and method | `POST v1/documents/stamp`, a new view alongside `DocumentGenerator` | `documents/generate` is registered under the `v1/` include (`urls.py:10`, `templates.py:254`); a sibling `documents/stamp` path keeps the surface discoverable and versioned identically | 2026-09-22 |
| D3 | Sync vs async | Synchronous, no Huey | Stamping is in-process (pypdf/Pillow), no network, single-document; it matches the synchronous `DocumentGenerator` rather than the batch/tracking Huey path. `django-patterns.md` lists "document generation" under Huey for *batch* work, but the single-document generate endpoint is itself synchronous — the same reasoning applies here | 2026-09-22 |
| D4 | Tenancy model | Authentication-gated, stateless; no org-scoped queryset at launch | The document to stamp is request-carried base64, so there is no stored resource to filter by org. `DocumentGenerator` likewise operates on request-body data and applies no `access_by`; auth-required is the complete tenancy story for a pixel-only surface | 2026-09-22 |
| D5 | Registry exposure | Accept `carrier`/`doc_type` scalars only; resolve the built-in registry server-side | The SDK `registry` argument is a `RegistryLookup` callable (`stamping.py:22`, `lib.py` `stamp_document`) and is not serializable; the HTTP surface can only forward the scalar seed key segments and let the server-side registry resolve them, matching the utility's own placement-precedence rule (consumer placement primary; seeds only when placement omitted, D11 of the utility PRD) | 2026-09-22 |
| D6 | API logging | Skip the logging mixin, subclass `api.BaseAPIView` | Base64 document responses bloat `APILogIndex`; `DocumentGenerator` already documents and applies this skip (`templates.py:151-153`); stamping responses are the same shape | 2026-09-22 |
| D7 | Error mapping | Utility `ValueError` → `ErrorResponse` 400; unexpected → 500 | PNG rejection, registry miss, ZPL underlay, and unbacked format are all client-input faults the utility raises as `ValueError`; they map to 400 the way `TemplateRenderingError` does (`templates.py:207`), never surfacing as 500. (Registry-miss-as-409 remains Q4) | 2026-09-22 |
| D8 | Responsibility boundary | Server composites and returns pixels; stores and verifies nothing | Inherits D8 of the utility PRD; the endpoint is a stateless wrapper and asserts nothing about signature validity | 2026-09-22 |

### Edge Cases Requiring Input

| Edge Case | Impact | Proposed Handling | Needs Input? |
|-----------|--------|-------------------|--------------|
| Request carries a stored-document reference instead of base64 | Would require org-scoped fetch and `validate_resource_token` | Out of scope at launch (Q2); base64-in only | ✅ Yes (Q2) |
| Registry miss when `placement` omitted and no seed matches `carrier/doc_type` | Utility raises `ValueError`; is that 400 or 409? | 400 by default (D7); 409 under consideration (Q4) | ✅ Yes (Q4) |
| Oversized combined base64 payload (document + image) | Body-size limit or memory pressure | Confirm limits or set an explicit ceiling (Q3) | ✅ Yes (Q3) |

---

## Problem Statement

### Current State

`lib.stamp_document` is SDK-only. An API consumer holding a base64 duty document
and a signature PNG has no HTTP surface to composite them; they must either pull
the SDK into their own runtime or reimplement the format-multiplexed compositing
the utility already solves. Meanwhile the documents module already wraps the
adjacent problem — turning template + data into a base64 PDF — behind a clean
REST endpoint:

```python
# Shipped today: documents module wraps the weasyprint pipeline over REST.
# modules/documents/karrio/server/documents/views/templates.py:167
class DocumentGenerator(api.BaseAPIView):
    # Skip LoggingMixin: base64-encoded PDFs bloat the APILogIndex table.
    def post(self, request: Request):
        data = serializers.DocumentData.map(data=request.data).data
        doc_file = generator.Documents.generate(...)          # SDK/render utility
        document = serializers.GeneratedDocument.map(
            data={**data, "doc_file": base64.b64encode(doc_file.getvalue()).decode("utf-8")}
        )
        return Response(document.data, status=status.HTTP_201_CREATED)

# There is no equivalent for stamping. lib.stamp_document is reachable only
# from Python, not over the API.
```

### Desired State

```python
# Proposed: a sibling REST view wrapping lib.stamp_document, same idiom.
# modules/documents/karrio/server/documents/views/stamping.py
class DocumentStamper(api.BaseAPIView):
    # Skip LoggingMixin: base64 document responses bloat the APILogIndex table.
    def post(self, request: Request):
        data = serializers.StampData.map(data=request.data).data
        document = models.ShippingDocument(
            category=data.get("doc_type") or "other",
            format=data.get("format"),          # optional; the utility sniffs bytes
            base64=data["document"],
        )
        stamped = lib.stamp_document(
            document,
            image=data.get("image"),
            placement=_to_placement(data.get("placement")),
            layer=data.get("layer", "overlay"),
            carrier=data.get("carrier"),
            doc_type=data.get("doc_type"),
            date=data.get("date"),
        )
        return Response(
            serializers.StampedDocument.map(
                data={"doc_file": stamped.base64, "format": stamped.format}
            ).data,
            status=status.HTTP_201_CREATED,
        )
```

```json
// POST v1/documents/stamp  →  201
{
  "doc_file": "<stamped base64>",
  "format": "PDF"
}
```

The API consumer states the same intent an SDK consumer states — a document, an
image, and a placement — and receives the composited document as base64 in the
same format it sent, never branching on document format.

### Problems

1. **No API parity**: the stamping capability is trapped in the SDK; API-only
   integrations cannot reach it despite the module having every primitive (a
   REST base64 wrapper precedent, the SDK call pattern, the auth scaffolding)
   already in place.
2. **Reinvention risk**: without a first-party endpoint, API consumers rebuild
   the format multiplexer, coordinate conversion, and dithering the utility PRD
   catalogues as duplication hazards.
3. **Inconsistent surface**: `POST /documents/generate` exposes one document
   utility over REST but `stamp_document` — a structurally identical base64-in /
   base64-out utility — has no matching surface.

---

## Goals & Success Criteria

### Goals

1. One REST endpoint that accepts a base64 duty document, a base64 image, and a
   placement (or `carrier`/`doc_type` seed key), invokes `lib.stamp_document`,
   and returns the stamped document as base64 of the same format.
2. Zero new SDK behavior and zero new server dependencies — the utility and the
   `weasyprint`/`pypdf` stack are already present.
3. Reuse of the module's shipped patterns verbatim: the `BaseAPIView` +
   skip-logging shape, the `DocumentData`/`GeneratedDocument` serializer idiom,
   the `v1/` URL registration, and the `ErrorResponse` error shape.
4. Error semantics that never leak a utility `ValueError` as a 500.

### Success Criteria

| Metric | Target | Priority |
|--------|--------|----------|
| API consumer format branching | Zero branches in consumer code | Must-have |
| New server dependencies | Zero | Must-have |
| Utility `ValueError` surfacing as 500 | Never (all mapped to 400/409) | Must-have |
| API-log rows carrying base64 documents | Zero (logging mixin skipped) | Must-have |
| GraphQL parity | Deferred pending Q1 | Nice-to-have |
| Stored-document / org-keyed variant | Deferred pending Q2 | Nice-to-have |

### Launch Criteria

**Must-have (P0):**

- [ ] `POST v1/documents/stamp` returns a stamped PDF for a valid base64 document + placement
- [ ] PNG document, registry miss, ZPL underlay, and unbacked format each return 400 (or 409 per Q4), never 500
- [ ] Endpoint requires authentication; unauthenticated requests are rejected
- [ ] The view skips the logging mixin (no base64 in `APILogIndex`)

**Nice-to-have (P1):**

- [ ] ZPL document stamping over the same endpoint
- [ ] `carrier`/`doc_type` seed-resolution path exercised end to end
- [ ] GraphQL mutation (gated on Q1)

---

## Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| A. REST endpoint mirroring `POST /documents/generate` | Co-located precedent; base64 idiom transfers directly; auth/log patterns reused | Single-protocol at launch | **Selected** |
| B. GraphQL mutation only | Matches template-CRUD GraphQL analogue | The nearest precedent (generation) is REST, not GraphQL; more plumbing for no consumer-proven need | Rejected (deferred, Q1) |
| C. Huey background task returning a job id | Decouples heavy work | Stamping is fast and in-process; async adds polling and a result store for no latency benefit | Rejected (D3) |
| D. SDK-only (no server surface) | Zero server cost | Leaves API consumers without parity; the whole point of task 5.2 | Rejected (Q7 unblocked this) |
| E. Stored-document / org-scoped reference path | Serves "stamp my stored shipment doc" directly | Adds `access_by`/token plumbing for an unproven flow; base64-in already covers the utility's contract | Deferred (Q2) |

### Trade-off Analysis

A is chosen because the survey established that the endpoint is a near-copy of an
existing one: swap `generator.Documents.generate` for `lib.stamp_document`, keep
the serializer-in / base64-out shape, keep the `BaseAPIView` skip-logging
posture, and inherit the `ErrorResponse` mapping. B is not wrong, only premature:
the module supports GraphQL, but the document-mutation precedent is REST and the
launch specs defer protocol breadth (Q1). C misreads the workload — stamping has
none of the network latency or fan-out that justifies Huey for tracking and batch
rating. E is the one genuinely open product question (Q2); the base64-in path
satisfies the utility's own contract (it already takes base64) without any
tenancy surface, so a stored-reference path is an additive future, not a launch
requirement.

---

## Technical Design

> Studied before design: the shipped documents module (`views/templates.py`,
> `views/printers.py`, `serializers/base.py`, `urls.py`, `tests/test_generator.py`),
> the SDK utility (`core/utils/stamping.py`, `lib.py` `stamp_document`,
> `core/models.py` `ShippingDocument`), and the 5.1 precedent survey. Citations
> below are file:line against the branch `stamping-server-endpoint`.

### Existing Code Analysis

| Component | Location | Reuse Strategy |
|-----------|----------|----------------|
| `DocumentGenerator.post` (REST base64 wrapper over a document utility) | `modules/documents/karrio/server/documents/views/templates.py:167` | Template for the new `DocumentStamper.post`; copy the `serializer.map → utility → base64 out → 201` shape |
| Skip-logging comment on `BaseAPIView` | `modules/documents/karrio/server/documents/views/templates.py:151-153` | Carried verbatim (D6); base64 stamping responses bloat `APILogIndex` the same way |
| `TemplateRenderingError` → 400, `DoesNotExist` → 404, generic → 500 handling | `modules/documents/karrio/server/documents/views/templates.py:207-239` | Error-mapping template; utility `ValueError` slots into the 400 branch (D7) |
| `DocumentData` / `GeneratedDocument` serializers (`doc_file` = "A base64 file content") | `modules/documents/karrio/server/documents/serializers/base.py:45,73` | Idiom for the new `StampData` (request) and `StampedDocument` (response); `doc_file` field name reused for the base64 output |
| `serializers.Serializer` / `PlainDictField` / `ChoiceField` base classes | `modules/documents/karrio/server/documents/serializers/base.py:13-70` | Field vocabulary for the stamping serializers |
| URL registration under `v1/` include | `modules/documents/karrio/server/documents/urls.py:10`, `views/templates.py:254` | Add `documents/stamp` to the same `urlpatterns` (or a new `views/stamping.py` included identically) (D2) |
| `lib.stamp_document` entry point | `modules/sdk/karrio/lib.py` `stamp_document` (re-export) | Called unchanged; signature `(document, image, placement, layer, carrier, doc_type, registry, date)` |
| `StampPlacement` / `StampRequest` / `RegistryLookup` | `modules/sdk/karrio/core/utils/stamping.py:22,47,69` | `StampPlacement` fields (page, x, y, width, height, rotation, dpi) mirrored as the nested request serializer; `RegistryLookup` is a callable and is **not** exposed (D5) |
| `ShippingDocument` model (category, format, print_format, base64, url) | `modules/sdk/karrio/core/models.py:431` | Constructed from request data to feed `stamp_document`; the utility sniffs `base64` bytes so `format` is an optional hint |
| `printers.py` `access_by` / `AccessMixin` / `validate_resource_token` tenancy | `modules/documents/karrio/server/documents/views/printers.py:20,78,102` | The tenancy pattern a **stored-document** variant would adopt; not needed for the stateless base64-in launch path (D4, Q2) |
| Django endpoint test idiom (`APITestCase`, `reverse`, base64 assertions) | `modules/documents/karrio/server/documents/tests/test_generator.py:13-61` | Template for the stamping endpoint tests |

### Architecture Overview

```
                       ┌──────────────────────────────────────────────┐
                       │              documents module                │
                       │                                              │
  base64 document ─────┼─▶┌────────────┐   ┌──────────────────────┐   │
  base64 image         │  │ StampData  │──▶│  DocumentStamper.post │   │
  placement / seed key │  │ serializer │   │  (BaseAPIView,        │   │
                       │  │ (validate) │   │   skip logging)       │   │
                       │  └────────────┘   └──────────┬───────────┘   │
                       │                              │               │
                       │                   ┌──────────▼────────────┐  │
                       │                   │ lib.stamp_document()   │  │
                       │                   │  (SDK; sniff+dispatch) │  │
                       │                   └──────────┬────────────┘  │
                       │                              │               │
                       │                   ┌──────────▼────────────┐  │
                       │                   │ StampedDocument        │  │
                       │                   │ serializer (base64 out)│  │
                       │                   └──────────┬────────────┘  │
                       └──────────────────────────────┼───────────────┘
                                                      ▼
                                     201  { doc_file: <base64>, format }

  errors: utility ValueError ─▶ ErrorResponse 400 (409 per Q4); unexpected ─▶ 500
```

### Sequence Diagram

```
┌────────┐        ┌──────────────────┐      ┌──────────────────┐     ┌──────────────┐
│ API    │        │ DocumentStamper  │      │ StampData /      │     │ lib.         │
│consumer│        │ (BaseAPIView)    │      │ StampedDocument  │     │ stamp_document│
└───┬────┘        └────────┬─────────┘      └────────┬─────────┘     └──────┬───────┘
    │ POST v1/documents/stamp                        │                      │
    │ (auth token; document b64, image b64, placement)│                     │
    │───────────────────────>│                       │                      │
    │                        │ 1. StampData.map(...)  │                      │
    │                        │──────────────────────>│                      │
    │                        │ validated data         │                      │
    │                        │<──────────────────────│                      │
    │                        │ 2. build ShippingDocument, call utility       │
    │                        │──────────────────────────────────────────────>│
    │                        │        sniff → backend → composite            │
    │                        │ 3. ShippingDocument (same format, stamped b64)│
    │                        │<──────────────────────────────────────────────│
    │                        │ 4. StampedDocument.map(doc_file, format)       │
    │                        │──────────────────────>│                      │
    │ 201 { doc_file, format}│                       │                      │
    │<───────────────────────│                       │                      │
    │                        │  (on ValueError → ErrorResponse 400/409)      │
```

### Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                          REQUEST FLOW                            │
├──────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐   ┌────────────┐   ┌──────────────┐   ┌───────┐│
│  │ JSON body:   │──>│ StampData  │──>│ ShippingDoc  │──>│ lib.  ││
│  │ document b64 │   │ (DRF map)  │   │ (category,   │   │ stamp_││
│  │ image b64    │   │            │   │  format,     │   │ docu- ││
│  │ placement{}  │   │            │   │  base64)     │   │ ment  ││
│  │ layer/date…  │   │            │   │              │   │       ││
│  └──────────────┘   └────────────┘   └──────────────┘   └───────┘│
├──────────────────────────────────────────────────────────────────┤
│                          RESPONSE FLOW                           │
├──────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐   ┌────────────────┐   ┌──────────────────────┐│
│  │ 201 JSON:    │<──│ StampedDocument │<──│ ShippingDocument     ││
│  │ doc_file b64 │   │ (doc_file,      │   │ (format unchanged,   ││
│  │ format       │   │  format)        │   │  base64 composited)  ││
│  └──────────────┘   └────────────────┘   └──────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
```

### Data Models

Illustrative; final field names belong to the OpenSpec design phase. The
serializers follow the `DocumentData`/`GeneratedDocument` idiom
(`serializers/base.py:45,73`).

```python
class StampPlacementData(serializers.Serializer):
    """Anchor rectangle mirroring the SDK StampPlacement (stamping.py:47)."""

    page = serializers.IntegerField(required=False, default=1)
    x = serializers.FloatField(help_text="Millimetres from page top-left")
    y = serializers.FloatField(help_text="Millimetres from page top-left")
    width = serializers.FloatField(required=False)
    height = serializers.FloatField(required=False)
    rotation = serializers.FloatField(required=False, default=0)
    dpi = serializers.IntegerField(required=False, default=203)  # ZPL only


class StampData(serializers.Serializer):
    """One stamping operation over the API."""

    document = serializers.CharField(help_text="base64 carrier document (PDF or ZPL)")
    image = serializers.CharField(required=False, help_text="base64 PNG to composite")
    placement = StampPlacementData(required=False)   # primary path
    layer = serializers.ChoiceField(                 # overlay | underlay
        choices=["overlay", "underlay"], required=False, default="overlay"
    )
    carrier = serializers.CharField(required=False)  # registry seed key segment
    doc_type = serializers.CharField(required=False) # ShippingDocumentCategory name
    format = serializers.CharField(required=False)   # optional hint; bytes are sniffed
    date = serializers.CharField(required=False)     # pre-formatted date string
    graphic_name = serializers.CharField(required=False)  # ZPL ~DY/^XG cache opt-in


class StampedDocument(serializers.Serializer):
    """base64-out response, mirroring GeneratedDocument (serializers/base.py:73)."""

    doc_file = serializers.CharField(required=True, help_text="A base64 file content")
    format = serializers.CharField(required=False, help_text="Format of the stamped document")
```

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `document` | string | Yes | base64 carrier document; format sniffed from bytes |
| `image` | string | No | base64 PNG to composite (signature or letterhead) |
| `placement` | object | Primary path | Consumer anchor; omitted only when a `carrier`/`doc_type` seed exists |
| `placement.page` | int | No (default 1) | 1-based page index |
| `placement.x` / `.y` | float | With placement | Millimetres from page top-left |
| `placement.width` / `.height` | float | No | Draw size before rotation |
| `placement.rotation` | float | No (default 0) | Degrees clockwise about the rectangle centre |
| `placement.dpi` | int | No (default 203) | ZPL target density; ignored by PDF |
| `layer` | string | No (default overlay) | `overlay` (signature) or `underlay` (letterhead, PDF only) |
| `carrier` | string | Seed path only | Registry key segment; ignored when `placement` supplied (D5) |
| `doc_type` | string | Seed path only | `ShippingDocumentCategory` name (e.g. `cn22`, `commercial_invoice`) |
| `format` | string | No | Optional hint; the utility sniffs the document bytes regardless |
| `date` | string | No | Pre-formatted date string composited preceding the signature |
| `graphic_name` | string | No | ZPL `~DY`/`^XG` send-once cache opt-in; ignored by PDF |
| `doc_file` (response) | string | Yes | base64 stamped document |
| `format` (response) | string | No | Echoes the (unchanged) document format |

### API Changes

**Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `v1/documents/stamp` | Composite an image onto a base64 document; return the stamped base64 |

**Request/Response:**

```json
// Request
{
  "document": "<base64 PDF or ZPL>",
  "image": "<base64 PNG>",
  "placement": { "x": 150.0, "y": 250.0, "width": 45.0, "height": 18.0 },
  "layer": "overlay"
}

// Response 201
{
  "doc_file": "<base64 stamped document>",
  "format": "PDF"
}

// Error 400 (PNG document, registry miss, ZPL underlay, unbacked format)
{
  "errors": [{ "message": "<utility ValueError message>" }]
}
```

### Multi-Tenancy Analysis

The utility is stateless and pixel-only: the document to stamp is supplied as
base64 in the request body, so there is no persisted resource whose rows must be
filtered by org. `DocumentGenerator` establishes exactly this posture — it reads
template content or a template id from the request and applies no `access_by`
scoping to the generation itself. The stamping endpoint inherits that model
(D4): authentication is required (via `api.BaseAPIView`), and that is the
complete tenancy story for a request-carried document. There is no cross-tenant
read surface because nothing tenant-owned is read.

A stored-document variant — "stamp the invoice already persisted against
shipment X in my org" — would be different: it would resolve a queryset and must
therefore apply `models.<Model>.access_by(request)` and/or
`validate_resource_token`, exactly as the batch printers do
(`printers.py:78,102`). That variant is deferred (Q2); if the human brings it in
scope, the tenancy rule in `.claude/rules/django-patterns.md` (always filter by
org context) applies to the stored path and this section must gain an
`access_by`-scoped design.

---

## Edge Cases & Failure Modes

### Edge Cases

| Scenario | Expected Behavior | Handling |
|----------|-------------------|----------|
| PNG document submitted | Explicit rejection, not silent pass-through | Utility raises `ValueError` (no PNG backend) → 400 (D7) |
| `placement` omitted and no seed matches `carrier`/`doc_type` | No silent wrong-anchor stamp | Utility raises `ValueError` naming the missing key → 400 (or 409 per Q4) |
| `layer: underlay` on a ZPL document | Rejected (ZPL has no z-order) | Utility raises `ValueError` → 400 |
| Document base64 that is neither PDF nor ZPL | Rejected | Utility raises `ValueError` (unbacked format) → 400 |
| Neither `document` nor a valid base64 body | Serializer validation fails | DRF `ValidationError` → 400 (mirrors `templates.py:228`) |
| Valid ZPL document + overlay | Stamped ZPL returned, same format | Utility ZPL backend; `format` echoed unchanged |
| Unauthenticated request | Rejected | `BaseAPIView` authentication |
| Very large combined payload | Bounded or explicit error | Q3 — confirm limits or set a ceiling |

### Failure Modes

| What Can Go Wrong | Impact | Mitigation |
|-------------------|--------|------------|
| Utility `ValueError` surfaces as 500 | Consumer sees a server fault for their own bad input | Catch `ValueError` explicitly and map to `ErrorResponse` 400/409 (D7); test each raising path |
| Base64 responses logged into `APILogIndex` | Table bloat, storage pressure | Skip the logging mixin via `BaseAPIView` (D6); assert no log row carries the base64 |
| Unbounded request body | Memory pressure / DoS | Q3 payload ceiling |
| Cross-tenant read through a future stored path | Data leak | Base64-in path reads nothing tenant-owned (D4); stored path (Q2) must use `access_by`/token before it ships |

### Security Considerations

- [ ] Endpoint requires authentication (`api.BaseAPIView`)
- [ ] No org-owned resource is read on the base64-in path (nothing to leak; D4)
- [ ] Base64 documents excluded from API logs (D6)
- [ ] Utility `ValueError` never surfaced as 500 (no stack-trace leakage; D7)
- [ ] Request payload bound (Q3)

---

## Implementation Plan

All tasks Pending; this primes `openspec/changes/add-document-stamping/tasks.md`
group 5.2, it does not execute it.

### Phase 1: Serializers

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| `StampData`, `StampPlacementData`, `StampedDocument` serializers | `modules/documents/karrio/server/documents/serializers/base.py` | Pending | S |

### Phase 2: View and URL

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| `DocumentStamper(api.BaseAPIView)` with skip-logging comment, utility call, `ValueError` → 400/409 mapping | `modules/documents/karrio/server/documents/views/templates.py` (or new `views/stamping.py`) | Pending | M |
| Register `documents/stamp` under the `v1/` include | `views/templates.py` urlpatterns (or `urls.py` if a new module) | Pending | S |
| Wire `openapi.extend_schema` (tags, operation id, request/response, 400/404/500) | same view | Pending | S |

### Phase 3: Tests

| Task | Files | Status | Effort |
|------|-------|--------|--------|
| Django endpoint tests (success PDF, PNG-reject, registry-miss, ZPL-underlay, auth-required, log-skip) | `modules/documents/karrio/server/documents/tests/test_stamping.py` | Pending | M |
| Base64 PDF/ZPL and PNG fixtures (PII-verified per the utility PRD policy) | `tests/test_stamping.py` module constants | Pending | S |

**Dependencies:** Phase 2 depends on Phase 1; Phase 3 depends on Phase 2. GraphQL
(Q1) and a stored-document path (Q2) are additive phases only if the human
selects them.

---

## Testing Strategy

> Django server tests via `karrio test` (not pytest). Create objects via API
> requests where a stored resource is involved; use `reverse(...)` for the URL;
> assert with `assertResponseNoErrors` then a comprehensive body assertion, and
> `mock.ANY` for dynamic fields. Follow `tests/test_generator.py` (`:13-61`).

### Test Categories

| Category | Location | Coverage Target |
|----------|----------|-----------------|
| Endpoint success | `modules/documents/.../tests/test_stamping.py` | PDF stamp round-trip; format echoed |
| Error mapping | same | PNG/registry-miss/ZPL-underlay/unbacked each → 400 (or 409, Q4), never 500 |
| Auth | same | Unauthenticated request rejected |
| Logging skip | same | No `APILogIndex` row carries the base64 response |
| Seed path (P1) | same | `carrier`/`doc_type` resolves a built-in seed |

### Test Cases

```python
import base64
from unittest.mock import ANY
from django.urls import reverse
from rest_framework import status
from karrio.server.core.tests import APITestCase


class TestDocumentStamper(APITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.maxDiff = None

    def test_stamp_pdf_returns_base64_same_format(self):
        """A valid PDF + placement returns a stamped base64 PDF."""
        url = reverse("karrio.server.documents:document-stamper")
        response = self.client.post(url, {
            "document": CN22_PDF_BASE64,
            "image": SIGNATURE_PNG_BASE64,
            "placement": {"x": 150.0, "y": 250.0, "width": 45.0, "height": 18.0},
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertResponseNoErrors(response)
        self.assertDictEqual(response.data, {"doc_file": ANY, "format": "PDF"})
        self.assertTrue(base64.b64decode(response.data["doc_file"]).startswith(b"%PDF"))

    def test_stamp_rejects_png_document(self):
        """A PNG document is a client fault: 400, not 500."""
        url = reverse("karrio.server.documents:document-stamper")
        response = self.client.post(url, {
            "document": PNG_DOCUMENT_BASE64,
            "image": SIGNATURE_PNG_BASE64,
            "placement": {"x": 10.0, "y": 10.0},
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
```

### Fixture Approach

Module-level base64 constants (`CN22_PDF_BASE64`, `SIGNATURE_PNG_BASE64`,
`PNG_DOCUMENT_BASE64`, a small ZPL sample), following the `SAMPLE_PDF_BASE64`
convention in `test_generator.py:446`. Any real carrier document vendored as a
fixture must be human-verified free of address and personal data before
inclusion, per the fixture-vendoring policy in the utility PRD
([DOCUMENT_STAMPING_UTILITY.md](./DOCUMENT_STAMPING_UTILITY.md), Testing
Strategy); the existing `postnord_cn22.pdf` (customs-only, dummy org number) is
the reference.

### Running Tests

```bash
# From repository root
source bin/activate-env
karrio test --failfast karrio.server.documents.tests
```

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Utility `ValueError` leaks as 500 | Medium | Medium | Explicit `ValueError` → 400/409 branch; a test per raising path (D7) |
| Base64 responses bloat `APILogIndex` | Medium | Low | Skip logging mixin (D6); assert no logged base64 |
| Payload size unbounded | Medium | Low | Q3 ceiling / limit confirmation |
| Scope creep into a stored-document/org path without tenancy | High | Low | Q2 keeps it out of launch; stored path must use `access_by`/token before shipping (D4) |
| Protocol churn if GraphQL demanded later | Low | Medium | REST-only is additive; a GraphQL mutation can wrap the same utility later (Q1) |

---

## Migration & Rollback

### Backward Compatibility

- **API compatibility**: purely additive — one new endpoint; no existing route,
  serializer, or payload changes.
- **Data compatibility**: no models, no migrations; stamping is stateless.
- **Feature flags**: unnecessary; the endpoint is opt-in by being called.

### Rollback Procedure

1. **Identify issue**: failing stamping endpoint tests or consumer-reported bad
   output.
2. **Revert**: remove the view, serializers, URL entry, and tests; no data to
   unwind.
3. **Verify**: `karrio test --failfast karrio.server.documents.tests` green.

---

## Appendices

### Appendix A: Provenance and Handoff

This PRD is the task-5.2 decision record for the OpenSpec change
`add-document-stamping`. It builds on three artifacts:
[DOCUMENT_STAMPING_UTILITY.md](./DOCUMENT_STAMPING_UTILITY.md) (the SDK-utility
decision record D1-D13, which deferred server exposure to a precedent survey,
its D12/Q7), the 5.1 survey
`docs/notes/documents/stamping-server-precedent-survey.md` (verdict: precedent
holds; recommendation: go, decision reserved to the human), and the shipped
documents module. The design phase (`design.md`) owns the final serializer field
names and the resolution of Q1-Q4; `tasks.md` group 5.2 derives from the
Implementation Plan above; the change's spec owns the SHALL-level endpoint
behavior (format preservation, base64 I/O, `ValueError` → 400/409, auth
required).

### Appendix B: SDK Contract the Endpoint Wraps

`lib.stamp_document(document, image=None, placement=None, layer="overlay",
carrier=None, doc_type=None, registry=None, date=None) -> ShippingDocument`
(`modules/sdk/karrio/lib.py` `stamp_document`, implemented at
`modules/sdk/karrio/core/utils/stamping.py`). It takes a `ShippingDocument`
(`core/models.py:431`; `category`, `format`, `base64`, `url`) plus an optional
base64 PNG and a placement or seed key, sniffs the document bytes, dispatches to
the PDF or ZPL backend, and returns a `ShippingDocument` of the same format whose
`base64` carries the composite. The `registry` parameter is a `RegistryLookup`
callable (`stamping.py:22`) and is **not** exposed over HTTP; the endpoint
forwards only `carrier`/`doc_type` and lets the server resolve the built-in seed
registry (D5). PNG documents, registry misses (when `placement` is omitted), ZPL
underlays, and unbacked formats each raise `ValueError`.

### Appendix C: Precedent Endpoints Reused

| Surface | Location | What is borrowed |
|---------|----------|------------------|
| `POST /documents/generate` | `views/templates.py:167` | View shape, base64 idiom, skip-logging, error mapping |
| `GeneratedDocument.doc_file` | `serializers/base.py:73` | base64 response field name and help text |
| Batch printers `access_by` / token | `views/printers.py:78,102` | Tenancy pattern a future stored-document path would adopt (Q2) |
