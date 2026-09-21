# PostNord post-booking customs declaration via proxy tooling

Instruction guide for submitting a customs declaration for an already-booked
PostNord item, after the fact, through the connector's declaration proxy.

The intended implementer is external workflow tooling — a Python driver running
where the `postnord` connector is importable (the repository environment or the
deployed API container).
No dashboard UI is involved; the unified karrio API surface has no
customs-declaration operation, so this capability is connector-local, reached
via `gateway.proxy.create_customs_declaration` and
`gateway.proxy.create_customs_declaration_pdf` (the `find_service_points`
precedent).

Two flows produce customs documents in this connector.
Booking-time declaration (unified `customs` payload mapped to the CN22 branch)
and the implicit standalone customs document for export-letter bookings are
handled by `karrio.Shipment.create` itself and are not this guide's subject.
This guide covers the third flow: the caller owns the declaration object —
branch, ids, update semantics — and karrio builds the wire envelope, submits,
and reports.

Correctness of the declaration content is the caller's responsibility.
Karrio does not reconcile, replace, verify, or retract previously submitted
declarations; there is no post-booking maintenance of customs documents.
PostNord's rule that the item's EDI booking must have been sent earlier is
enforced upstream and surfaces as an error message, not as a client-side check.

## Workflow overview

```
  workflow driver (Python, connector-local)
        │
        │ 1. booked item id (from ShipmentDetails.tracking_number or the
        │    booking response's itemId) + declaration content
        ▼
  customs.customs_declaration_request(declaration, gateway.settings)
        │   validates: ids[] exactly 1, exactly one branch, 13-line limit
        │   → Serializable([declaration]); PDF params ride ctx as query entries
        │
        │ 2a. digital                 2b. PDF variant (+ paperSize/rotate/
        ▼                                multiPDF/alignment params)
  gateway.proxy.create_customs_declaration(request)      — or _pdf(request)
        │   POST /rest/shipment/v3/customs/declaration[/pdf]?apikey=…
        ▼
  customs.parse_customs_declaration_response(...)  — or _pdf_response(...)
        → result dict: booking_id, id_information[].status (OK|FAIL)
        → PDF variant adds documents[] (ShippingDocument, category cn22/cn23/
          customsInvoice from printoutComposition)
        → rejections (e.g. "EDI must have been sent earlier") → Messages
```

## Prerequisites

- Python 3.11+ with the connector importable (`source bin/activate-env` in the
  repo, or the deployment container).
- Connection settings: the PostNord `apikey`, `issuer_code`, `customer_number`,
  and `test_mode` selecting the sandbox host.
- An item whose EDI booking was already sent to PostNord: book first with
  `karrio.Shipment.create`, keep the assigned item id (the parsed
  `tracking_number`), then declare.

```python
import karrio.sdk as karrio

gateway = karrio.gateway["postnord"].create(
    dict(
        carrier_id="postnord",
        apikey=API_KEY,
        issuer_code="Z12",
        customer_number="00000000",
        test_mode=True,
    )
)
```

## Step 1 — build the typed declaration object

The request envelope is a generated schema class,
`karrio.schemas.postnord.customs_declaration_request.CustomsDeclarationRequestType`.
The caller chooses everything PostNord's swagger leaves open; the builder in
step 2 only enforces the envelope constraints.

Three declaration branches exist, exactly one per request:

- `customsDeclarationCN22` — the postal CN22; the branch booking uses
  automatically for unified customs data.
- `customsDeclarationCN23` — the CN23; additionally carries `postalCharges` and
  per-item `itemIds`.
- `customsInvoice` — commercial or proforma invoice; additionally carries the
  `seller`/`buyer`/`shipTo` parties and the `invoice` block.

`ids` carries exactly one entry — the booked item id — with an `idType`
(`ITEMID` for a booked parcel id; see the swagger for SHIPMENTID,
CUSTOMSREFERENCE, and siblings).
`updateIndicator` selects `Original`, `Update`, or `Deletion` for
re-declaration; omit it and PostNord treats the message as an Original.
A `Deletion` or `Update` requires an existing Original, and Update/Deletion are
not supported for Denmark (Z11), Norway (Z13), or Finland (Z14) issuers.

```python
import karrio.schemas.postnord.customs_declaration_request as postnord_customs

declaration = postnord_customs.CustomsDeclarationRequestType(
    updateIndicator="Original",
    testIndicator=True,  # sandbox payload marker; the gateway host follows test_mode
    ids=[postnord_customs.IDType(id="00373500454541020957", idType="ITEMID")],
    customsDeclarationCN22=postnord_customs.CustomsDeclarationCN22Type(
        countryOfOrigin="SE",
        EORIorPersonalIdNumber="SE5561234711",
        categoryOfItem=postnord_customs.CategoryOfItemType(
            categoryType=["GIFT"]
        ),
        detailedDescription=[
            postnord_customs.CustomsDeclarationCN22DetailedDescriptionType(
                content="Paperback novels",
                quantity=postnord_customs.TotalNumberOfPackagesType(value=2),
                grossWeight=postnord_customs.WeightType(value=0.5, unit="KGM"),
                value=postnord_customs.PostalChargesType(
                    amount=250.0, currency="SEK"
                ),
                hsTariffNumber="07019010",
                countryCode="SE",
                rowNo=1,
            )
        ],
        totalGrossWeight=postnord_customs.WeightType(value=0.5, unit="KGM"),
        totalValue=postnord_customs.PostalChargesType(
            amount=250.0, currency="SEK"
        ),
    ),
)
```

Declarations accept at most 13 `detailedDescription` lines per item id
(PostNord Booking Customs Information documentation).
The builder rejects more with a field error before any HTTP call; split a
longer declaration across multiple declaration objects — one per item id — or
consolidate lines.

## Step 2 — submit and parse

Digital declaration (status reported, no rendered document):

```python
from karrio.providers.postnord import customs

request = customs.customs_declaration_request(declaration, gateway.settings)
response = gateway.proxy.create_customs_declaration(request)
result, messages = customs.parse_customs_declaration_response(
    response, gateway.settings
)
```

PDF variant, with rendering params passed to the builder
(`paper_size` one of A4/A5/A6/LETTER/LABEL, `rotate` one of 0/90/180/270,
`multi_pdf` boolean, `page_horizontal_align`/`page_vertical_align`):

```python
request = customs.customs_declaration_request(
    declaration,
    gateway.settings,
    paper_size="A4",
    rotate="90",
    multi_pdf=False,
    page_horizontal_align="CENTER",
    page_vertical_align="CENTER",
)
response = gateway.proxy.create_customs_declaration_pdf(request)
result, messages = customs.parse_customs_declaration_pdf_response(
    response, gateway.settings
)
```

On success `result` is a dict with `booking_id` and one `id_information` entry
carrying the per-id `status` (`OK` or `FAIL`) and the assigned ids.
The PDF variant adds `documents`: a list of `ShippingDocument` with
`category` from PostNord's `printoutComposition` (`cn22`, `cn23`,
`customsInvoice`, …), `format` PDF, and `base64` data.
On rejection `result` is `None` and `messages` carries the unified error —
including PostNord's refusal when the item's EDI was never sent
("EDI must have been sent earlier").

## Conventions the caller must know

### Pass digit-only strings through as strings

The schema generator coerces digit-only swagger string fields to `int`
annotations — `partyIdType`, `postalCode` in the invoice parties,
`reasonForExportation`, `transportModeBorder`, `basicServiceCode`.
These travel to PostNord as strings regardless of the annotation: pass the
string form and never `int()`-coerce.
Leading zeros and alphanumeric values must survive intact — `partyIdType`
`"160"`, `reasonForExportation` `"1000"`, `hsTariffNumber` `"07019010"`, and
`postalCode` `"02100"` are all correct as strings; coercing them drops leading
zeros or changes meaning.
The connector itself follows this convention (the booking path sends
`partyIdType="160"` as a string), and the declaration proxy asserts it in its
unit tests.

### BuyerType is a party union, not a validated variant

The generated `BuyerType` is the pipeline's union of the seller, buyer, and
shipTo parties of the customs-invoice branch — one class with every field of
all three.
PostNord requires different fields per party (the seller carries `vatNo` and
`eoriNo`; the shipTo carries `refItemIds`), but the union validates none of
that client-side.
When constructing `customsInvoice.seller`, `buyer`, or `shipTo`, populate the
fields the specific party needs and leave the others unset; field correctness
is caller-owned, same as the declaration content.

## Live findings (2026-09-21)

Live verification on a production booking recorded three behaviors the caller
should expect beyond what the swagger states.
The declaration endpoint requires a registration number (EORI, VOEC, or IOSS)
on the CN22 — `SACUS-BR-24062502`, the same rejection as booking-time
carriage, so `customsDeclarationCN22` should carry
`EORIorPersonalIdNumber` (or `voec`/`ioss`) on every Original.
Intra-EU declarations are accepted on the tested account — an SE→PL item was
not rejected as not-applicable.
The digital endpoint's success response is the bare `bookingResponseCN`
(`bookingId` plus per-id `status` and assigned ids), not a wrapped envelope.
Full evidence: `docs/notes/postnord/customs-declaration-live-verification.md`.

## Open questions

- Handling when the declared value exceeds the CN22 ceiling (300 SDR): field
  error versus escalating to CN23 — deferred until sandbox evidence exists.
- `emailTo` and non-default `definePrintout` on the digital endpoint: add as
  pass-through params only when a consumer asks.
