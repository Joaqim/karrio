# Changelog entry (draft for the next release)

CHANGELOG.md is compiled by release commits from the git log, so this draft
stages the entry here for the release step rather than inserting an unreleased
section into a file whose sections are all releases.

## Feat

- feat(postnord): carry customs data in the booking request — unified `customs`
  is no longer silently dropped; commodities map onto the EDI booking's CN22
  declaration branch, and declarations over PostNord's 13-lines-per-item limit
  fail fast with a field error before any request is sent.
- feat(postnord): attach a standalone customs document to export letter
  (`postnord_export_letter` / `UX`) bookings with customs data, fetched by item
  id from PostNord's labels endpoint restricted to customs printouts, in the
  booking's label format family (PDF or ZPL), surfaced under the response's
  shipping documents (`docs.extra_documents`); retrieval failure does not fail
  the booking.
- feat(postnord): expose post-booking customs declaration as consumer-owned
  proxy methods (`create_customs_declaration`, `create_customs_declaration_pdf`)
  against PostNord's customs declaration API, returning per-id acceptance status
  and, on the PDF variant, the rendered documents.
