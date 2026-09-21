# Document stamping — SDK consumer guide

How a karrio caller composites a signature or letterhead onto a carrier duty
document that karrio returned, using the format-multiplexing stamp utility.
The utility takes a base64 PNG and an anchor, sniffs the document format,
composites via the matching backend, and returns the document in the same
format and shape it arrived in, so the consumer never branches on document
format.

Utility: `modules/sdk/karrio/core/utils/stamping.py`, re-exported as
`lib.stamp_document`, `lib.StampPlacement`, and `lib.StampRequest`.
This guide covers the launch scope: the PDF backend with a consumer-supplied
placement.
The ZPL backend and karrio-supplied registry seeds are follow-ups
(`openspec/changes/add-document-stamping/tasks.md`, groups 3 and 4).

## The entry point

`lib.stamp_document` is the single call a consumer makes.

```python
def stamp_document(
    document,            # models.ShippingDocument returned by karrio
    image=None,          # base64-encoded PNG
    placement=None,      # lib.StampPlacement — the primary path
    layer="overlay",     # "overlay" for signatures, "underlay" for letterheads
    carrier=None,        # registry seed key segment (omitted-placement path only)
    doc_type=None,       # registry seed key segment (omitted-placement path only)
    registry=None,       # optional RegistryLookup override
) -> models.ShippingDocument
```

The consumer passes the returned document, the image, and a placement.
The utility detects the format from the document bytes, dispatches to the
backend for that format, and returns a copy of the document whose `base64` now
carries the composited image; the `format` field is unchanged.
`lib.StampRequest` is the internal per-operation record the utility assembles
from these arguments; a consumer does not construct it for the primary path.

`lib.StampPlacement` is the anchor rectangle.
Coordinates are millimetres measured from the top-left of a one-based `page`
index, matching how a person measures a printed form with a ruler.

```python
@attr.s(auto_attribs=True)
class StampPlacement:
    page: int = 1        # 1-based page index
    x: float = None      # millimetres from the page's top-left corner
    y: float = None
    width: float = None
    height: float = None
    dpi: int = 203       # ZPL target density; ignored by the PDF backend
```

The PDF backend flips the top-anchored millimetre `y` against the page height
and converts to PDF points internally, so the consumer works only in
top-left millimetres and never sees the PDF bottom-left point system.
`dpi` is a ZPL concern and is ignored by the PDF backend.

## Primary path: signing a PostNord CN22

The launch target is a PostNord CN22 fetched as a PDF regardless of the
booking's label format, via the explicit `/v3/customs/declaration/pdf`
endpoint (`POST /rest/shipment/v3/customs/declaration/pdf`; see
`docs/notes/guides/postnord-customs-declaration-proxy.md` for how to obtain
that document).
The consumer supplies a signature PNG and an anchor over the CN22's blank
signature block, then composites with the overlay layer.

```python
import karrio.lib as lib

# doc is the ShippingDocument for the CN22 PDF the consumer already fetched.
doc = shipment.docs.extra_documents[0]

stamped = lib.stamp_document(
    doc,
    image=SIGNATURE_PNG,            # base64 PNG, supplied by the consumer
    placement=lib.StampPlacement(   # millimetres from the page top-left
        page=1,
        x=150.0,
        y=250.0,
        width=45.0,
        height=18.0,
    ),
    layer="overlay",                # signature draws over the CN22 content
)

assert stamped.format == doc.format   # "PDF" — format is invariant
assert stamped.base64 != doc.base64   # only the encoded content changed
```

The returned document is an ordinary `ShippingDocument`.
Its `format` still reads `PDF`, its page count is unchanged, and any fillable
form fields the carrier PDF carried remain fillable; only the `base64` content
is replaced.
The carrier's selectable text layer is preserved rather than rasterized.

## Overlay versus underlay

The `layer` argument selects the compositing order.
An `overlay` draws the image over the carrier content and is the layer for a
signature that must sit on top of the document.
An `underlay` draws the image beneath the carrier content so the content stays
legible above it, and is the layer for a letterhead; it is a PDF-only
capability, since ZPL has no z-order.

| Layer | Draw order | Use |
|---|---|---|
| `overlay` (default) | image over carrier content | signatures |
| `underlay` | carrier content over image | letterheads (PDF only) |

## Transparency: place signatures in blank blocks

The PDF backend white-flattens the PNG before compositing.
Pillow's PDF writer emits no soft mask for an RGBA image, so PNG alpha is
dropped when the image is saved as a PDF (design question Q6 in
`openspec/changes/add-document-stamping/design.md`).
To keep a semi-transparent stroke reading as its intended tone rather than
rendering fully opaque, the backend composites the image onto an opaque white
background: the mark keeps its tone and the transparent surround renders white.

The practical consequence is that a signature anchor should target a blank
signature block, where a white surround is invisible against the block.
A letterhead underlay is unaffected, because carrier content draws over it
regardless.
The image is auto-trimmed to its non-transparent bounding box before the
white-flatten, so surrounding transparent padding in the source PNG does not
enlarge the white rectangle.

## Format preservation and PNG rejection

Two behaviours are guarantees rather than incidental.

The utility detects the document format from its bytes by magic-byte
inspection, not from a declared format field alone, and the returned document
always declares the same format as the input.
Format never leaks into consumer code: the document-list shape is stable
across a stamp.

A document whose format has no active backend is rejected with an explicit
error rather than passed through unchanged.
Only the PDF backend is active at launch, so a PNG document — or any other
non-PDF format, including ZPL until its backend lands — raises a `ValueError`
naming the unsupported format, and no document is returned.
A raster image is never stamped onto a raster image silently.

## Registry omission and the launch reality

`placement` is the complete primary path today.
When a consumer omits `placement`, the utility consults a registry keyed by the
`carrier`, `doc_type`, and detected format, intended to supply a karrio-measured
anchor for a known document.
No seeds ship at launch: the registry hook resolves nothing for every key
(`_empty_registry` in the utility), so omitting `placement` currently raises an
explicit `ValueError` naming the missing key rather than guessing an anchor.

Until measured seeds land (tasks.md group 4), a consumer-supplied `placement`
is required for every stamp.
A consumer that wants to preview the future seeded path can pass its own
`registry` callable — a `RegistryLookup` mapping a key string to a
`StampPlacement` — but the shipped default supplies none.

## Responsibility boundary

The utility composites pixels only.
It stores nothing, and it makes no assertion about the legal validity,
authority, or signature semantics of the stamped content (decision D8 in
`PRDs/DOCUMENT_STAMPING_UTILITY.md`).
Karrio places the image where the consumer asked; the consumer owns whether
that image constitutes a valid signature, whether the signer had authority,
and what the stamped paper means in a customs or carrier workflow.

## The FedEx ETD precedent

The FedEx electronic trade documents (ETD) flow already resolves, for
electronic documents, the forces this utility faces for paper documents.
The utility mimics the ETD outcome — a signed, letterheaded document —
carrier-agnostically, without modifying the FedEx flow.
The comparison below (adapted from `PRDs/DOCUMENT_STAMPING_UTILITY.md`) is the
expectation set the workflow builds on.

| Dimension | FedEx ETD precedent | Generalized stamping analog |
|---|---|---|
| Document typing | `UploadDocumentType` closed vocabulary (`COMMERCIAL_INVOICE`, `PRO_FORMA_INVOICE`, `CERTIFICATE_OF_ORIGIN`, USMCA variants) | `ShippingDocumentCategory` names as optional registry seed keys |
| Consumer-generated bytes | `DocumentFile` base64 passes through karrio untouched | Path 1: the stamp happens upstream of karrio; the utility is not involved |
| Workflow timing | `ETDPreshipment` versus `ETDPostshipment` | stamp upstream of the carrier versus stamp the returned bytes |
| Render intent | `requestedDocumentTypes=["COMMERCIAL_INVOICE"]` asks the carrier to render | request PDF duty documents regardless of label format (PostNord explicit endpoint) |
| Return surface | `shipmentDocuments` routed to `docs.invoice` or `extra_documents` | stamped output replaces `base64` in place; `format` unchanged |
| Responsibility boundary | FedEx owns document validity; karrio transports bytes | karrio composites pixels; consumer owns legal semantics |

The two FedEx paths distinguish when stamping happens.

Path 1 is stamp-before-upload.
The consumer generates its own commercial invoice, stamps the signature onto
that PDF itself, uploads it through the existing FedEx ETD flow
(`POST /documents/v1/etds/upload`), and references the returned document id at
booking.
The stamp is applied upstream of karrio and this utility is not involved.

Path 2 is stamp-after.
The consumer asks FedEx to render the commercial invoice at booking
(`requestedDocumentTypes=["COMMERCIAL_INVOICE"]`), receives the carrier-rendered
invoice as `docs.invoice`, and then passes that document to `lib.stamp_document`
exactly as in the PostNord CN22 example above.
Path 2 is the utility's target: it stamps carrier-rendered documents that the
consumer did not generate.

## Related material

- Utility source: `modules/sdk/karrio/core/utils/stamping.py`
- Behaviour contract: `openspec/changes/add-document-stamping/specs/documents/stamping/spec.md`
- Decision record: `PRDs/DOCUMENT_STAMPING_UTILITY.md`
- PostNord CN22 supply guide: `docs/notes/postnord/customs-declaration-sdk-guide.md`
- PostNord customs declaration proxy: `docs/notes/guides/postnord-customs-declaration-proxy.md`
