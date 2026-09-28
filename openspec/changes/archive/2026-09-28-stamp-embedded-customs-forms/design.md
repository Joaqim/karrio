# Design

## Context

See proposal.md for motivation and specs/ for the requirements.

The stamping utility (`feat-document-stamping`, `modules/sdk/karrio/core/utils/stamping.py`) resolves anchors from a registry keyed `doc_type/FORMAT/paper`, seeded per carrier through `PluginMetadata.stamp_seeds` and reached by `_carrier_seeds` via `karrio.references.collect_providers_data()`.
It never inspects a document to decide its `doc_type`; the caller supplies it.
PostNord registers `cn22/PDF/A4` and `cn22/ZPL/*` from `providers/postnord/stamping.py` (`feat-postnord-cn22-stamping`); the ZPL seed resolves by the keyword `Date and Sender's signature`.

The PostNord booking (`feat-postnord-customs-invoice`) calls `/rest/shipment/v3/edi/labels/{pdf|zpl}` without `definePrintout`, bundles every printout into `docs.label`, and records non-zero composition kinds as `meta.printout_composition` (a sorted list such as `["cn22", "label"]`).
The proxy then fetches a standalone customs document by printId with `definePrintout=onlyCustomsDeclarations` when customs was declared and the service is `postnord_export_letter` or a customs-invoice product (`proxy.py:152-166`).
Service 91 maps to `CustomsStructure.cn22` through `customs_structure()`, as do the letter services.
Non-fatal findings are already surfaced as `models.Message(level="warning", code=...)`, precedent `_customs_omitted_message`.

The earlier convention that PDF labels and declarations are separate while ZPL combines them was karrio's, not PostNord's: the booking endpoint's default `definePrintout=ALL` composes label and CN22 in both formats.

The live captures `~/Documents/postnord_cn22_and_shipment_label.zpl` and `$XDG_STATE_HOME/agent-logs/karrio/postnord-customs-probe/` (by-id unrestricted and customs-only, PDF and ZPL, export letter) show the combined ZPL: one format with a single `^XZ`, the CN22 section (marker `^FX CUSTOMS_CN22_ROTATED^FS`, keyword occurring once) followed by the label section (marker `^FX SE_INTERNATIONAL_LETTER_LABEL^FS`).
Its CN22 section matches the lone fixture line for line apart from field values.

## Goals / Non-Goals

**Goals:**
- PDF and ZPL bookings follow one flow and yield the same document set, differing only in format.
- One definition of PostNord's declared sections, shared by the SDK classifier and the booking-time verification.
- Classification that is pure and carrier-generic, driven by carrier-declared metadata.
- The combined document stamps at the lone CN22's placement (ZPL by keyword, PDF on the CN22 page), touching nothing in the label.

**Non-Goals:**
- Splitting a combined ZPL into separate documents.
- Requesting a different `definePrintout` on the booking call; the booking keeps PostNord's default.
- Changing customs-invoice parcel products; they keep today's printout and standalone fetch.
- Any post-booking declaration call (`declarationOnly`) or CN23 for service 91.

## Decisions

### D1. Carrier-declared document sections as plugin metadata

A new `PluginMetadata.document_sections` field declares, per carrier and format, how a composed printout is recognized.
For ZPL it lists section markers keyed by composed kind (PostNord: `cn22` → `^FX CUSTOMS_CN22_ROTATED^FS`, `label` → `^FX SE_INTERNATIONAL_LETTER_LABEL^FS`).
For PDF it lists page-text markers keyed by composed kind (PostNord, from the live `probe1b`/`probe2b` captures: `cn22` → `CUSTOMS DECLARATION` with `CN22`, `label` → the letter label's text such as `Brev utrikes`).
The constants live in `providers/postnord/stamping.py` beside the seeds, and the SDK reads them through a helper modelled on `_carrier_seeds`.
Alternative: hardcode PostNord values in the SDK. Rejected because the SDK must stay carrier-agnostic and the booking check would then import SDK-private constants.
Alternative for ZPL: count `^XZ` or detect barcode commands. Rejected because the combined form has one `^XZ` like the lone form, and barcode presence is not a stable carrier contract, whereas the `^FX` comments are PostNord's own section labels.

### D2. Classification result and combined doc_type

The classifier returns a small frozen result: the composition (`none`, `declaration`, `label_with_declaration`), the composed kinds present, the registry `doc_type` to stamp under (`cn22` for a lone declaration, `label_cn22` for the combined form, absent for `none`), and for PDF the one-based index of the page carrying the CN22 section.
`label_cn22` is chosen over `label+cn22` so the registry key stays a plain token and matches the snake_case category convention.
The result is a value, not an exception: only unsupported formats raise, because that is a caller error rather than a composition outcome.

### D3. PDF classification from page text

The live captures show PostNord composes label and CN22 onto a single A4 page in PDF, just as ZPL composes them into a single format; a lone customs-only PDF is also a single A4 page.
Page count therefore cannot distinguish the two, so the classifier extracts each page's text with pypdf (already an SDK dependency on `chore-sdk-pypdf`) and matches the carrier's declared PDF markers per page.
Alternative: trust the reported `meta.printout_composition` and page count. Rejected after the captures showed both forms are one page, which would reduce PDF verification to echoing PostNord's own report.

### D4. Combined seeds reuse the lone CN22 anchors

PostNord registers `label_cn22/ZPL/*` with the same keyword and offset as `cn22/ZPL/*`; because the CN22 section is positionally identical and the keyword occurs once, keyword resolution yields the same placement.
PostNord registers `label_cn22/PDF/A4` with a coordinate placement measured on the combined `probe1b` page, since the CN22 section's position on the combined page is not assumed to match the customs-only page; the page index comes from classification through the placement's existing one-based page field.
The `cn22` seeds are untouched and their revision is not bumped.
Alternative: have the `cn22` seeds silently serve combined documents. Rejected because the classifier must name a distinct type for the consumer, and a distinct key lets the combined form diverge later without disturbing the lone seeds.

### D5. Booking-time verification is a warning in the parser, in both formats

In the shipment response parser, when customs was declared and `customs_structure(service) == cn22`, the decoded label is classified: ZPL by field-comment markers, PDF by page-text markers.
A result other than `label_with_declaration` appends `Message(level="warning", code=POSTNORD_UNEXPECTED_LABEL_COMPOSITION)` naming expected and classified compositions; the shipment is returned unchanged.
The parser calls the SDK classifier rather than re-deriving the rules, keeping one implementation.
In both formats this checks the returned bytes against what PostNord reported composing.

### D6. Standalone customs documents are opt-in, identically for both formats

The opt-in is `postnord_standalone_customs_documents` (bool, default False), read from `payload.options` like `entry_code`, falling back to a `ConnectionConfig` entry of the same name.
It is not added to `ShippingOption`, because every truthy member there is sent to PostNord as an `additionalServiceCode`.
When true, the proxy's by-id `onlyCustomsDeclarations` fetch runs in the label's format; the gate widens from `postnord_export_letter` to every service with `customs_structure(service) == cn22`, including 91.
The booking call is unchanged and keeps PostNord's default `definePrintout`, so `docs.label` is the composed printout in both formats.
Alternative: request `definePrintout=onlyLabels` for PDF. Rejected because it would make the formats non-interchangeable and rests on the karrio convention this change removes.

### D7. PDF keyword anchoring and alternative marker sets (added after live verification)

A sandbox booking of the export letter with a PDF label (`~/Documents/postnord_cn22_and_label_two_pages.pdf`, 2026-09-28) returned two A4 pages: page 1 a "PostNord Tracked Letter" label without the `Brev utrikes`/`Parcel ID` text, page 2 an upright CN22 whose form sits at a different offset and height than the rotated single-page layout.
Two consequences follow.
First, one registry key (`label_cn22/PDF/A4`) cannot carry coordinates for both layouts, so the combined PDF seed resolves by the CN22 keyword located in the classified page's text via pypdf's text-position visitor, with position and rotation taken from the matched text; this extends the ZPL keyword mechanism to PDF and replaces the measured coordinate seed of D4 for the combined type.
The lone `cn22/PDF/A4` seed keeps its coordinate placement, so lone-CN22 behavior is unchanged.
Alternative considered: a layout discriminator in the registry key with one measured seed per layout. Rejected because each new PostNord template would need a new key and measurement, whereas the signature keyword is stable across all captured layouts.
Second, label templates vary, so a section kind may declare alternative marker sets, present when any set fully matches; PostNord declares the letter template and the tracked letter template.
Alternative considered: treating any non-declaration page as the label. Rejected because an unrelated extra page would then count as a label.

### D8. International Parcel (91) and orientation-aware ZPL anchoring (added after live verification)

A live International Parcel (`91`) ZPL booking (`~/Documents/postnord_postpaket_utrikes_label_and_cn22.zpl`, 2026-09-28) returned two `^XA`...`^XZ` formats: a parcel label marked `^FX NORDIC_SHIPPING_LABEL^FS`, then an upright (`^FWN`) CN22 marked `^FX CUSTOMS_CN22_V2^FS` with the keyword at `^FO25,785`; `printoutComposition` was `cn22` + `label`, so PostNord composes a CN22 (not a CN23) for 91 with the current connector.
91 is a parcel product, not a letter; it is in scope because `customs_structure()` maps it to the CN22 branch.
The ZPL section markers gain `AnyOf` alternatives for both kinds.
ZPL keyword anchoring previously applied the seed offset along page axes and ignored field orientation, and inserted the stamp before the stream's last `^XZ`; on the upright V2 CN22 the stamp landed at `^FO12,1053`, beyond the format's `^LL840`.
ZPL keyword geometry therefore becomes relative to the matched field's reading frame (effective `^FW`/`^A` orientation), mirroring D7 for PDF, and the stamp is inserted into the format containing the keyword.
The International Parcel PDF (`~/Documents/postnord_postpaket_utrikes.pdf`, 2026-09-28) is two A4 pages: a parcel label ("International Parcel", "Shipment Item-ID") and a CN22 page; it adds a third PDF label marker alternative, and the keyword-anchored PDF seed of D7 is verified against its CN22 page (PDF stamping remains consumer-side per user decision).

## Risks / Trade-offs

- [The captures are export letter (UX) by-id printouts, not booking-call printouts, and service 91 is uncaptured] → a live booking capture for UX and 91 in both formats is a task; the UX by-id captures serve as fixtures until then. Bookings are not cancellable but unshipped test bookings are not billed.
- [Sandbox and live templates may differ; the two-page PDF was captured in sandbox and the combined ZPL in live] → both layouts are fixtures; further templates are added as alternative marker sets and verified by keyword anchoring rather than new coordinates.
- [PDF text extraction depends on PostNord embedding real text] → the captures carry extractable text; a PDF yielding no marker text classifies as `none`, which surfaces as a booking warning rather than a failure.
- [PostNord could rename its `^FX` section comments or PDF label wording] → classification returns `none` or `declaration`, which surfaces as a warning at booking rather than a failure, and the markers are one constant to update.
- [Export letter consumers lose the default standalone CN22] → called out in the changelog; consumers restore it by setting the opt-in on the connection.
- [Keyword stamping anchors on the first match of the keyword] → resolution fails explicitly when the keyword is absent; the PostNord captures carry the signature keyword once per document (ZPL) or per page (PDF), asserted by fixture tests, so a first-match rule is unambiguous for them. PDF anchoring uses the start of the text run containing the keyword, which equals the keyword in all captures.

## Migration Plan

Land the SDK classifier and metadata field on `feat-document-stamping`, then the PostNord seed, markers and live fixture on `feat-postnord-cn22-stamping`, then the booking changes on `feat-postnord-customs-invoice`, and regenerate `develop` with `assemble-develop.sh`.
Rollback is per branch: removing the booking changes restores today's documents, and the classifier and seed are additive.

## Open Questions

- Exact warning message wording and whether the code constant joins the shared warning codes on `refactor-shared-warning-codes`; this does not change behavior or tasks.

## Follow-ups outside this change

A compliance check on 2026-09-28 compared what the PostNord connector transmits for service 91 and letters with PostNord's published requirements (`docs/notes/customs/nordic-trade-documents-facts.md`) and with the `nordic_conventions` advisory plugin.
Post-booking duties such as printing, attaching, and signing documents are the consumer's and are relayed by that plugin; the items below are neither transmitted by the connector nor advised by the plugin, and are recorded here rather than addressed.

- Service 91 with non-commercial content (gift, sample, documents, returned goods) requires a CN23 at any value; the connector sends CN22 data and the plugin warns only for commercial goods. CN23 selection stays deferred per the customs-declaration spec; switching 91 to CN23 will need a new printout capture, markers, and seed, because the D8 markers recognise only `CUSTOMS_CN22_V2`.
- Non-commercial 91 above SEK 2 000 requires a commercial or proforma invoice; no value threshold or SEK conversion exists in the connector or the plugin.
- Letters above SEK 2 000 outside Norway require a commercial invoice (and a CN23 per the English PostNord page, which conflicts with the Swedish page); not transmitted and not advised.
- Letters above the 300 SDR CN22 ceiling are not checked (`PRD_POSTNORD_INTEGRATION.md` Q2).
- The connector drops `customs.commercial_invoice`, `invoice`, and `invoice_date` for 91 and letters without a warning, unlike the drop-with-warning convention for unneeded customs input.

The plugin-side gaps (non-commercial 91 CN23, proforma-only-for-gift-or-sample on 91, 91 and letters for Finnish and Danish shippers) are recorded in the plugin's own openspec.
