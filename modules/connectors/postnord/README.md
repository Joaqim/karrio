# karrio.postnord

This package is a PostNord extension of the [karrio](https://pypi.org/project/karrio) multi carrier shipping SDK.

## Requirements

`Python 3.11+`

## Installation

```bash
pip install karrio.postnord
```

## Usage

```python
import karrio.sdk as karrio
from karrio.mappers.postnord.settings import Settings


# Initialize a carrier gateway
postnord = karrio.gateway["postnord"].create(
    Settings(
        apikey="...",            # PostNord API key (single credential, sent as a query param)
        customer_number="...",   # PostNord customer number
        application_id="...",    # PostNord application id
        issuer_code="Z12",       # consignor issuer code (default "Z12")
        account_country_code="SE",
        test_mode=True,          # True -> sandbox (atapi2.postnord.com); False -> production (api2.postnord.com)
    )
)
```

Check the [Karrio Mutli-carrier SDK docs](https://docs.karrio.io) for Shipping API requests.

## Authentication

PostNord uses a single `apikey`, sent as a query parameter on every call (the Booking, Pickup, Service Points, and Tracking APIs are unsecured beyond the key).
Authorization is granted per API product: a key may be authorized for Booking but not for the Transit Time product, in which case that product returns `403 "Invalid API Key"`.
`test_mode` selects the host — `atapi2.postnord.com` (sandbox) when on, `api2.postnord.com` (production) when off — so a production key supplied to a test-mode connection is rejected by the sandbox rather than creating real shipments.

## Connection settings

| Setting | Required | Default | Description |
|---------|----------|---------|-------------|
| `apikey` | yes | — | PostNord API key (query-param credential) |
| `customer_number` | yes | — | PostNord customer number |
| `application_id` | yes | — | PostNord application id |
| `issuer_code` | no | `Z12` | Consignor issuer code |
| `account_country_code` | no | `SE` | Account country |
| `test_mode` | no | `false` | Route to sandbox vs production |

Connection config options (under the connection's config):

| Option | Default | Description |
|--------|---------|-------------|
| `label_type` | `PDF` | Per-connection default label file format (`PDF` or `ZPL`), overridden per request by the shipment `label_type`. PostNord selects the format by endpoint path (`/labels/pdf` vs `/labels/zpl`). |
| `label_size` | — (unset) | PostNord physical label size, sent as the `labelType` query parameter: `standard` (190×105mm), `small` (75×105mm), or `ste` (PDF-only). Unset omits the parameter and PostNord defaults to `standard`. |
| `enable_transit_times` | `false` | Opt-in: call the Transit Time API to enrich `transit_days`/estimated delivery and filter by serviceability. Requires the key to be subscribed to the Transit Time product. |
| `language` | — (unset) | Default booking locale when a shipment sets no `options.language`. |
| `locale_by_recipient` | `false` | Derive the booking locale from the recipient country (`SE`→`sv`, `DK`→`da`, `NO`→`no`, `FI`→`fi`) when neither `options.language` nor `language` is set. The server also persists the derived locale on the shipment and its tracker. |
| `offer_tracked_letter` | `false` | Offer Tracked Letter (34) in rates. |
| `offer_export_letter` | `false` | Offer Export Letter (UX) in rates; requires issuer `Z12`. |

## Shipment options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `entry_code` | string | — | PostNord entry code (door code) for the recipient's building, e.g. an apartment entrance code. Sent as a shipment `freeText` with usage code `ZDC`; PostNord prints it as "Ref 2" on the label and maps it to the consignee reference. Max 50 characters: a longer value rejects the booking with an `ENTRY_CODE_LENGTH` message before any call to PostNord. PostNord does not document which services accept it — the value is passed through unverified and is ignored by services without door-code support. |
| `language` | string | `en` | Booking/notification locale (lowercase ISO 639-1), sent as the query `locale` (SMS/Email language) and uppercased as the body `language` element (label/document text). Resolved per request, then from connection config, then (with `locale_by_recipient` enabled) from the recipient's country code. |
| `sms_notification` | bool | — | Opt in to PostNord notifying the consignee by SMS (`additionalServiceCode` `A3`, consignee `smsNo`). Least intrusive channel; notification language follows the booking locale. |
| `email_notification` | bool | — | Opt in to e-mail notification (`A4`, consignee `emailAddress`). |
| `postnord_notify_by_letter` | bool | — | Opt in to letter notification (`A2`, consignee address). |
| `postnord_notify_by_phone` | bool | — | Opt in to voice-call notification (`A9`, consignee `phoneNo`). |
| `postnord_driver_notification` | bool | — | Opt in to driver notification (`B8`, consignee `phoneNo`). |

PostNord has no notification-suppress flag: the consignee is notified only when a notification additional service is booked, and channels combine freely — setting only `sms_notification` books SMS and nothing else. `false` or omitted books nothing. Per-service rules apply (documented, not enforced here): PostNord documents Parcel (18) as requiring one of A2/A3/A4 and MyPack Home (17) as requiring consignee SMS-or-email contact data; PostNord validates these at booking.

## Labels

The resolved `label_type` selects the booking endpoint: `/rest/shipment/v3/edi/labels/pdf` or `/rest/shipment/v3/edi/labels/zpl`.
Both return the label inline in `labelPrintout[].printout`.

The Booking API swagger documents `printout.encoding` as base64 only, but the ZPL endpoint returns raw UTF-8 ZPL text with `encoding: "none"` (observed live), sometimes without `labelFormat`.
The connector passes base64 printouts (or printouts without `encoding`) through and base64-encodes any other encoding, so `docs.label` is always base64; a missing `labelFormat` falls back to the requested label type.
The live ZPL body starts with persistent host commands (`^LL1520`, i.e. 190 mm at 8 dots/mm, and `^CI28` for UTF-8) followed by `^CW` font aliases for printer-memory fonts, all preserved verbatim.

## Service points

Service-point lookup (Service Points v5) is connector-local: Karrio has no unified service-point operation, so it is reached through the gateway proxy.

```python
import karrio.providers.postnord.service_points as service_points

request = service_points.service_points_request(
    dict(country_code="SE", postal_code="11528", number_of_points=3),
    postnord.settings,
)
points, messages = service_points.parse_service_points_response(
    postnord.proxy.find_service_points(request), postnord.settings
)
```

Passing `northing` and `easting` instead of an address selects the coordinate lookup.
Each point is a dict with `id`, `name`, `type`, `address`, `coordinates`, `opening_hours`, and `distance`.

## Customs declarations

### At booking

When a shipment carries `customs` with at least one commodity, the booking embeds one customs structure selected by the service.
Letter services (`LETTER_SERVICES` in `units.py`) and International Parcel (91) send a CN22 declaration (`customsDeclarationCN22`); every other service is a parcel product and sends a customs invoice (`customsInvoice`).

CN22 mapping:

| Unified input | CN22 field |
|---------------|------------|
| `customs.content_type` | `categoryOfItem.categoryType` (see below) |
| `customs.commodities[]` | `detailedDescription[]`: `title` (or `description`) as `content`, `quantity`, `grossWeight` in KGM, `value`, `hs_code` as `hsTariffNumber`, `origin_country` as `countryCode`, 1-based `rowNo` |
| package weights | `totalGrossWeight` in KGM |
| commodity values | `totalValue`: sum of `value_amount`, currency of the first commodity that sets one |
| `shipper.country_code` | `countryOfOrigin` |
| `customs.options.eori_number` / `voec_number` / `ioss_number` | `EORIorPersonalIdNumber` / `voec` / `ioss` |

`content_type` accepts Karrio's values or PostNord's own, ignoring case and extra whitespace: `documents`→`DOCUMENT`, `gift`→`GIFT`, `sample`→`COMMERCIAL SAMPLE`, `merchandise`→`SALE OF GOODS`, `return_merchandise`→`RETURNED GOODS`, `other`→`OTHER`.
Other values are sent verbatim, and an absent `content_type` sends no `categoryOfItem`.

A CN22 without any of EORI, VOEC, or IOSS under `customs.options` is rejected with a field error before any call, matching PostNord's rejection `SACUS-BR-24062502`.
A CN22 accepts at most 13 commodity lines; more are rejected before any call to PostNord.

Customs invoice mapping:

| Unified input | Customs invoice field |
|---------------|-----------------------|
| `customs.commercial_invoice` | `type`: `COMMERCIAL` when true, `PROFORMA` when false or omitted |
| (fixed) | `declarationType` `invoiceExportDeclaration`, `invoice.reasonForExportation` `1000` (permanent export) |
| shipper | `seller`: `company_name` (or `person_name`), address, `federal_tax_id` as `vatNo`, connection `customer_number` as `partyIdentification`, `customs.options.eori_number` as `eoriNo` |
| recipient | `buyer`: same address mapping, tax id as `vatNo` when present |
| party `person_name` (or `company_name`), `phone_number`, `email` | `contacts` |
| `customs.options.voec_number` / `ioss_number` | `voec` / `ioss` |
| `customs.invoice` (or the shipment `reference`), `customs.invoice_date` | `invoice.invoiceNo`, `invoice.shippingDate` |
| `customs.commodities[]` | `detailedDescription[]`: `quantity`, `hs_code`, `title` (or `description`), `origin_country`, weight in KGM as `netWeight` and `grossWeight`, `itemValue` |
| commodity weights and values | `totalGrossWeight`, `invoiceTotal` (currency of the first commodity that sets one) |

A customs invoice is rejected with a field error before any call when the shipper has no tax id, when neither `customs.invoice` nor `reference` is set, when the shipper or recipient lacks a contact name or phone number, or when a commodity lacks `hs_code` or `origin_country`.
Registration numbers are optional on the customs invoice.

Registration-number keys under shipment `options` are rejected with a field error, because unknown shipment options would otherwise be dropped silently.

For Export Letter (UX) and parcel-product bookings with customs data, the connector also fetches the standalone customs document (`POST /rest/shipment/v3/labels/ids/{pdf,zpl}` with `definePrintout=onlyCustomsDeclarations`), keyed by the booking's `printId`, and attaches it to `docs.extra_documents`.
The document category is the kind PostNord reports in `printoutComposition` (`cn22`, `customsInvoice`, …), falling back to `customs_declaration`.
A failed fetch never fails the booking; it surfaces as a message.

### After booking

`create_customs_declaration` (`POST /rest/shipment/v3/customs/declaration`) and `create_customs_declaration_pdf` (`.../declaration/pdf`) declare customs for an item whose booking was already sent.
The caller builds the declaration with the generated `karrio.schemas.postnord.customs_declaration_request` types and owns its content: exactly one id, exactly one of `customsDeclarationCN22`, `customsDeclarationCN23`, or `customsInvoice`, and `updateIndicator` (`Original`, `Update`, `Deletion`; Update and Deletion are not supported for issuers Z11, Z13, and Z14).
Karrio builds the envelope, enforces the id, branch, and 13-line constraints, submits, and reports; it does not reconcile or retract earlier declarations.

```python
import karrio.schemas.postnord.customs_declaration_request as postnord_customs
from karrio.providers.postnord import customs

declaration = postnord_customs.CustomsDeclarationRequestType(
    updateIndicator="Original",
    ids=[postnord_customs.IDType(id="00373500454541020957", idType="ITEMID")],
    customsDeclarationCN22=postnord_customs.CustomsDeclarationCN22Type(
        countryOfOrigin="SE",
        EORIorPersonalIdNumber="SE5561234711",
        categoryOfItem=postnord_customs.CategoryOfItemType(categoryType=["GIFT"]),
        detailedDescription=[
            postnord_customs.CustomsDeclarationCN22DetailedDescriptionType(
                content="Paperback novels",
                quantity=postnord_customs.TotalNumberOfPackagesType(value=2),
                grossWeight=postnord_customs.WeightType(value=0.5, unit="KGM"),
                value=postnord_customs.PostalChargesType(amount=250.0, currency="SEK"),
                hsTariffNumber="07019010",
                countryCode="SE",
                rowNo=1,
            )
        ],
        totalGrossWeight=postnord_customs.WeightType(value=0.5, unit="KGM"),
        totalValue=postnord_customs.PostalChargesType(amount=250.0, currency="SEK"),
    ),
)

request = customs.customs_declaration_request(declaration, postnord.settings)
result, messages = customs.parse_customs_declaration_response(
    postnord.proxy.create_customs_declaration(request), postnord.settings
)
```

For the PDF variant, pass `paper_size` (A4/A5/A6/LETTER/LABEL), `rotate` (0/90/180/270), `multi_pdf`, `page_horizontal_align`, or `page_vertical_align` to `customs_declaration_request`, call `create_customs_declaration_pdf`, and parse with `parse_customs_declaration_pdf_response`.
The result holds `booking_id` and one `id_information` entry per id with its `OK`/`FAIL` status; the PDF variant adds `documents` as `ShippingDocument` entries.
Rejections, including PostNord's "EDI must have been sent earlier", return `None` with messages.

The schema generator annotates digit-only string fields (`partyIdType`, invoice `postalCode`, `reasonForExportation`, `transportModeBorder`, `basicServiceCode`) as `int`; pass them as strings so leading zeros survive.
`BuyerType` is one class covering the invoice seller, buyer, and ship-to parties; populate only the fields each party needs, as none are validated client-side.
Live checks found the digital endpoint's success response to be the bare `bookingResponseCN` object and intra-EU declarations (SE→PL) accepted.

## Supported operations

| Operation | Notes |
|-----------|-------|
| Rating | Static rates from the connection's service levels / server-side RateSheet (no carrier call by default). Optionally enriched with live transit times when `enable_transit_times` is on. |
| Shipment | Booking + label retrieval in one call (`/rest/shipment/v3/edi/labels/pdf`, or `/labels/zpl` when the resolved label type is ZPL). |
| Pickup | Courier collection booking (`Pickup.schedule`). |
| Tracking | Event-based via Track & Trace v7 (`findByIdentifier`); degrades to link-only (tracking URL + generic status) when the key isn't authorized for the T&T product. |
| Returns | Booked via the shipment create flow with a return service code. |
| Service points | Connector-local lookup (`gateway.proxy.find_service_points`). |

## Limitations

Tracking uses PostNord Track & Trace v7 (`findByIdentifier`) for full event history and normalized statuses. Per-product authorization applies (as with Transit Time): if the key is not subscribed to the Track & Trace product, tracking degrades gracefully to link-only — a tracking URL plus a single generic status, no events.

Cancellation is not available over the REST API: PostNord's REST `/v3/edi` ignores `updateIndicator: "Deletion"` and re-books a duplicate, and the id-based delete endpoint is absent from the published spec. The connector therefore never cancels and never reports a false success — cancel returns an explicit failure message pending PostNord's v3 REST reference manual.

Manifest is not supported: PostNord has no scan-form/end-of-day manifest endpoint. Use `Pickup.schedule` for courier collection.

Transit-time enrichment is opt-in (`enable_transit_times`, default off) because it requires a key subscribed to the Transit Time product. When enabled but unavailable, rating degrades gracefully to static transit days with a warning rather than failing.
