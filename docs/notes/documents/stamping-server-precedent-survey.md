---
title: Stamping server-precedent survey (add-document-stamping Q7)
---

# Stamping server-precedent survey

## Purpose

This note answers Q7 of the `add-document-stamping` OpenSpec change (`openspec/changes/add-document-stamping/design.md:117`): does precedent exist in karrio for a generalized server-side surface over an SDK utility?
Q7 gates the deferred group-5 server phase (task 5.2, a documents-module pipeline).
This is a read-only survey producing a go/no-go recommendation; the final decision is the human's.
Nothing was built and no code, spec, or task file was modified.

## Findings

Karrio already has a Django server module whose entire purpose is to wrap SDK-level rendering utilities behind an authenticated, tenant-scoped, base64-in/base64-out HTTP surface.
That module is `modules/documents/` (Django app `karrio.server.documents`), and it is the same module task 5.2 names as the home for the stamping pipeline.
Its `pyproject.toml` (`modules/documents/pyproject.toml`) already declares `weasyprint` and `pyzint` as dependencies, and depends on `karrio_server_core`, `karrio_server_graph`, and `karrio_server_manager`.
The task's stated pipeline shape — "weasyprint HTML overlay to PDF to pypdf merge" — is already half-resident here: weasyprint HTML-to-PDF lives in `generator.py`, and the pypdf merge half lives in the SDK (`lib.bundle_pdfs`/`lib.bundle_base64`) which the server already calls.

The clearest single precedent is the document-generation endpoint.
`DocumentGenerator.post` (`modules/documents/karrio/server/documents/views/templates.py:167`) is a `POST /documents/generate` view that validates the request body through a DRF serializer (`DocumentData`, `serializers/base.py:45`), invokes the rendering pipeline (`generator.Documents.generate`, `generator.py:54`), base64-encodes the resulting PDF buffer, and returns it through an output serializer (`GeneratedDocument`, `serializers/base.py:73`, whose sole required payload field is `doc_file`, "A base64 file content").
This is precisely the shape a `stamp_document` surface would take: a base64 (and small-JSON) request in, an SDK utility in the middle, a base64 document out.
Notably `DocumentGenerator` subclasses `api.BaseAPIView` and carries a deliberate comment (`templates.py:151-153`) that it skips the logging mixin because base64-encoded PDFs bloat the `APILogIndex` table — a directly transferable lesson for a stamping endpoint, whose responses are likewise base64 PDFs.

A second precedent wraps an SDK utility even more literally.
`ShipmentDocsPrinter.get_file` (`modules/documents/karrio/server/documents/views/printers.py:104`) calls `lib.bundle_base64(...)` — an SDK `karrio.lib` helper (`modules/sdk/karrio/lib.py:1038`, backed by `modules/sdk/karrio/core/utils/helpers.py:115`) — from inside a Django view to assemble a downloadable bundle.
The order and manifest printers in the same file do the same (`printers.py:157`, `printers.py:196`).
So the pattern "a server view calls a `karrio.lib` document utility and streams the result" is not hypothetical; it is shipped and in use.

Tenancy and auth for these surfaces are established, not net-new.
The REST template views resolve querysets through `models.DocumentTemplate.access_by(request)` (`templates.py:46`, `:99`, `:119`, `:144`), where `access_by` is the org/user access filter on the core base model (`modules/core/karrio/server/core/models/base.py:26`).
Writes go through `owned_model_serializer` (`modules/core/karrio/server/serializers/abstract.py:177`) via `DocumentTemplateModelSerializer` (`serializers/documents.py:5`).
The download printers gate on `AccessMixin` (`modules/core/karrio/server/core/authentication.py:294`) plus `validate_resource_token` (`modules/core/karrio/server/core/utils.py:666`).
The GraphQL surface mirrors this: `modules/documents/karrio/server/graph/schemas/documents/mutations.py` uses `@utils.authentication_required` and `access_by` on the same models.
The multi-tenancy rule in `.claude/rules/django-patterns.md` (always filter by org context) is therefore satisfied by reusing these existing primitives.

The nearest non-precedents are worth stating so the boundary is clear.
The SDK addons `modules/sdk/karrio/addons/label.py` and `modules/sdk/karrio/addons/renderer.py` are not imported anywhere under `modules/core`, `modules/manager`, or `apps/api` (a py-only search returned nothing); the server documents module reimplements its own weasyprint pipeline in `generator.py` rather than surfacing those addons.
The FedEx ETD flow is entirely connector/SDK-level: it builds `etdDetail` during shipment creation (`modules/connectors/fedex/karrio/providers/fedex/shipment/create.py:388`) and uploads via `modules/connectors/fedex/karrio/providers/fedex/document.py`, driven by enums in `units.py`.
ETD is a carrier-specific upload during rating/shipping, not a generalized server surface over a document-mutation utility, so it is not the precedent — the documents module is.
Finally, `stamp_document` itself is confirmed net-new server-side: a py-only search for `stamp_document`, `StampPlacement`, and `RegistryLookup` across `modules/core`, `modules/documents`, `modules/manager`, and `apps/api` returned zero hits.

For completeness, the SDK utility the server phase would wrap is `lib.stamp_document` (`modules/sdk/karrio/lib.py:1052`, implemented at `modules/sdk/karrio/core/utils/stamping.py:364`).
It takes a `ShippingDocument` model (`modules/sdk/karrio/core/models.py:431`; fields `category`, `format`, `base64`, `url`) plus an optional base64 PNG `image`, a `placement`/`registry`, `carrier`/`doc_type`, and an optional pre-formatted `date`, and returns a `ShippingDocument` of the same format whose `base64` carries the composited image.
Its inputs and outputs are already base64 strings and small scalars, which maps cleanly onto the `DocumentData`/`GeneratedDocument` serializer idiom above.

## Precedent verdict

Yes.
A generalized server surface over an SDK document utility already exists in this codebase, in the exact module the deferred task targets.
`POST /documents/generate` wrapping the weasyprint pipeline (`templates.py:167`) and the printers calling `lib.bundle_base64` (`printers.py:104`) together establish the full pattern: serializer-validated request, SDK/rendering utility in the middle, base64 document response, org tenancy through `access_by`/`AccessMixin`, and an existing GraphQL analogue.
The verdict is an unqualified yes rather than "partial" because both halves of the claim hold independently — a REST utility-wrapping endpoint and a literal `karrio.lib` call from a view — and the auth/tenancy scaffolding is reused rather than invented.

## Go / no-go recommendation

Recommendation: go, with the decision reserved to the human.
The precedent Q7 asks for is not merely present but co-located: a stamping endpoint would be a near-copy of `DocumentGenerator.post`, swapping `generator.Documents.generate` for `lib.stamp_document`, reusing `access_by`/`AccessMixin` for tenancy and the `doc_file` base64 serializer idiom for I/O, and inheriting the already-documented decision to skip API logging for base64 PDF responses.
The design's own gating language (`design.md:117`) says that absent precedent the change stays SDK-scoped; precedent is present, so that constraint is lifted and the server phase is architecturally unblocked.

Because the recommendation is go, the residual work is the human's scoping call, not a blocker, and the main risks and unknowns are these.
The stamping input carries a base64 PNG and an optional base64 carrier document, so request-size and log-bloat handling need the same `skip-logging` treatment `DocumentGenerator` already applies, and payload limits should be confirmed.
`lib.stamp_document` raises explicit errors on a registry miss and rejects formats with no backend (including PNG); the endpoint must translate those into the module's existing DRF error-response shape (`ErrorResponse`, 400/409) rather than 500s, mirroring the `TemplateRenderingError` handling in `templates.py:207`.
The serializer/model surface is net-new (no `DocumentData` equivalent exists for stamping), so field names, the placement/registry input shape, and whether stamping accepts a raw base64 document versus a stored shipment/document reference are open design questions the human should settle before a build.
Whether the surface should be REST-only, GraphQL-only, or both is also unresolved; the module supports both patterns, and the launch specs currently defer all of it.
None of these are precedent gaps; they are ordinary endpoint-design decisions that the existing patterns already show how to make.

The final decision to proceed with task 5.2 remains the human's; this note recommends go on the strength of an in-module precedent.
