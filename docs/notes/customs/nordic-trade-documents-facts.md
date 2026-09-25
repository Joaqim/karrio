---
title: Nordic trade documents — collated facts for PostNord and DHL Freight Sweden
---

# Nordic trade documents — collated facts for PostNord and DHL Freight Sweden

Collated 2026-09-25 during an `/opsx:explore` session on whether the PostNord and DHL Freight Sweden connectors respect `customs.commercial_invoice`, and where karrio must take ownership of forwarding trade documents.
This note records facts with attribution; it makes no design decisions.

Source tags used throughout:
S is vendored spec or repository code (file:line or JSON path, relative to the repository root on `develop` at 2c83eed7b);
W is carrier, customs-authority, or UPU public documentation (URL, with retrieval or snapshot date where known);
I is inference by the session and should be verified before it is relied upon.

## Scope and stated preferences

The user prefers electronic submission of trade data over physical attachment to the parcel, and carrier-native options as long as they add no service cost.
Karrio already owns the data needed to render the required electronic trade documents.
Requirement narrowing by service, goods value, shipper country, and recipient address is intended to start as a non-blocking suggestion, with the API consumer owning compliance.
No own declaration forms exist yet; mirroring a carrier document or authoring a similar one is acceptable if permitted.

The gap is not a lack of customs guidance: carriers and customs authorities publish extensive guidance, notably for Norway as the main non-EU Nordic destination.
The gap is that none of it is yet cemented as it relates to karrio, meaning which karrio fields and options carry each requirement, what each connector transmits, and what remains the API or SDK consumer's responsibility (printing, attaching, forwarding, signing).
This note is the factual input for closing that gap.

## What `commercial_invoice` means in karrio

`commercial_invoice` is a boolean on the `Customs` model, not a shipping option (S `modules/sdk/karrio/core/models.py:118`).
The server serializer documents it only as "Indicates if the shipment is commercial" (S `modules/core/karrio/server/core/serializers.py:621-625`).
Connectors that read it map it to a commercial versus proforma invoice type, never to "produce a document":

| Connector | Reads `customs.commercial_invoice` | Maps to |
|---|---|---|
| dhl_express | yes (S `.../dhl_express/shipment.py:294`) | `DHLInvoiceType` CMI / PFI |
| dhl_freight_sweden | yes (S `.../dhl_freight_sweden/shipment/create.py:296`) | `CustomsDocument.type` CommercialInvoice / ProformaInvoice |
| postnord | no | would map to `customsInvoice.type` COMMERCIAL / PROFORMA |
| mydhl, dhl_parcel_de, dhl_poland | no | — |

Karrio's own invoice rendering is triggered by the server-only option `invoice_template`, not by `commercial_invoice` (S `modules/manager/karrio/server/manager/serializers/shipment.py:666-806`).
It is injected into the booking as `doc_files` only when the carrier has the `paperless` capability and `paperless_trade` is set; otherwise it is rendered after purchase into `shipment.invoice` (S same file :692-725, :797-803, :1049-1080).
The `paperless` capability is inferred from any proxy method whose name contains "document" (S `modules/sdk/karrio/core/units.py:229`); neither PostNord nor DHL Freight Sweden has it.

## Regulatory baseline (origin Sweden)

When the export declaration is lodged electronically, supporting documents such as invoices need not be attached; they are retained for five years and produced on request (W [Tullverket, styrkande handlingar vid export](https://www.tullverket.se/foretag/internationellhandel/exporteravaror/deklareravarorvidexport/styrkandehandlingarvidexport.4.78aa922815794d801e25e3.html)).
Postal consignments up to EUR 1000 without export duties or prohibitions are deemed declared for export on leaving the EU (W Delegated Regulation 2015/2446 Art. 140(1)(d), 141(4), 142; [Agencia Tributaria legal basis](https://sede.agenciatributaria.gob.es/Sede/en_gb/ayuda/manuales-videos-folletos/manuales-practicos/manual-importacion-exportacion-envios-escaso-valor/4-formalidades-exportacion-reexportacion/4_2-envios-postales/4_2_1-ambito-aplicacion-declaracion-exportacion/base-juridica.html)).
No Tullverket page stating the EUR 1000 postal rule was found (I: Sweden applies the EU rule).
Above EUR 1000, or for restricted goods, an electronic export declaration with MRN is required (W [Tulli](https://tulli.fi/en/businesses/export/how-to-make-an-export-declaration), same EU rules).
DHL Freight is not a postal operator, so the postal deemed-declaration route does not apply to it (I).

CN22 and CN23 are UPU postal instruments; CN22 applies to letter-post items up to 300 SDR, CN23 above that and to all parcel-post items (W [UPU Circular 100 (2022)](https://www.upu.int/UPU/media/upu/files/aboutUpu/acts/05-actsRegulationsConventionAndPostalPayment/actsCircular100-2022En.pdf), [UPU Circular 117 (2019)](https://www.upu.int/UPU/media/upu/files/UPU/aboutUpu/acts/nonPermanentActs/actNonPermanentRegulationsConventionFinalProtocol05-117En.pdf)).
The UPU Regulations require forms to "conform to the annexed specimens"; no permission for third-party reproduction was found (W [UPU Regulations to the Convention 2021](https://www.upu.int/UPU/media/upu/files/aboutUpu/acts/05-actsRegulationsConventionAndPostalPayment/actsRegulationsToTheConventionAndFinalProtocol.pdf)).
A CN22/CN23 lookalike has no standing on non-postal freight (I).
A form printed from electronically transmitted data must be signed by the sender (W [WCO–UPU Postal Customs Guide 2024](https://www.upu.int/UPU/media/upu/files/postalSolutions/programmesAndServices/postalSupplyChain/customs/guideWcoUPUCustomsEn.pdf)).

The commercial invoice has no fixed format; a proforma invoice is used for goods not sold and states "No charge. Value for customs purposes only" (W [Bring tulldokument](https://www.bring.se/tjanster/tull/tulldokument); W DHL Freight CIE p.5, cited below).

Special fiscal territories requiring customs formalities from Sweden (W [Tullverket, EU customs and fiscal territories](https://www.tullverket.se/en/startpage/private/travelling/bringinggoodswhentravelling/eucustomsandfiscalterritories.4.4776b304199f1ed58cc29614.html)):

| Status | Territories |
|---|---|
| Inside customs union, outside VAT area | Åland, Canary Islands, Mount Athos, French overseas departments, San Marino |
| Outside both | Büsingen, Heligoland, Livigno, Campione, Ceuta, Melilla, Faroe Islands, Greenland, Andorra, Vatican |
| Treated as EU | Monaco; Northern Ireland for goods (W [InterTradeIreland](https://crossbordertradehub.intertradeireland.com/trading-in-ni-and-windsor-framework)) |
| Third countries | Norway, Great Britain, Switzerland, Liechtenstein, Iceland; Channel Islands (I, not on the Tullverket page) |

## PostNord

### Booking API structure

`shipmentCustomsv2` carries `customsDeclarationCN22`, `customsDeclarationCN23`, `customsInvoice`, `customsTvinn`, and `customsTransit` as independent optional properties with no `oneOf` or exclusivity text (S `modules/connectors/postnord/vendor/booking.swagger.json:5942`, ~6027-6040).
`customsInvoice` "is used for packages classified as parcels" (S same file :5557), with `type` PROFORMA or COMMERCIAL and required buyer, seller, invoice, invoiceTotal, detailedDescription, totalGrossWeight (S :5461-5480).
The spec text: "There are two different types of customs invoices, commercial invoice (namely trade invoice) and proforma invoice (export invoice)."
`declarationType` values are invoiceExportDeclaration, invoiceImportDeclaration, invoiceImportDeclarationCeov, exportDeclaration, importDeclaration; export declarations "are sent to the export country customs system" (S :5235).
`definePrintout` includes `onlyCustomsDeclarations` (CN22/CN23/customsInvoice), `onlyCustomsInvoice`, and `labelsAndEmpty*` variants (S :670).
`customsTvinn` covers Norway shipments "declared by our customer or via its Agent/speditor" under Digitoll (S :5568).
No upload endpoint for self-produced document files exists in the spec (S).

### Current connector behaviour

The connector sends only `customsDeclarationCN22`, built from `customs.commodities`, for every product (S `modules/connectors/postnord/karrio/providers/postnord/shipment/create.py:281-342, 419-434, 546`).
It ignores `commercial_invoice`, `invoice`, `invoice_date`, `incoterm`, `signer`, and `certify`, and its option filter drops `paperless_trade`, `doc_files`, and `doc_references` (S `.../postnord/units.py:313-325`).
The generated schema already contains `customsInvoice` and `customsDeclarationCN23` (S `modules/connectors/postnord/karrio/schemas/postnord/shipment_request.py:363-364`).
Export Letter bookings fetch customs printouts into `docs.extra_documents` (S `.../postnord/shipment/create.py:192-224`; `.../mappers/postnord/proxy.py:154-252`).
The CN22 date and signature strip is stamped on request via `POST /v1/documents/stamp` using PostNord stamp seeds (S `.../postnord/stamping.py:14-30`).

### Requirements by product (shipper in Sweden)

Source: PostNord SE customs documents page (W [Wayback 2026-01-16](https://web.archive.org/web/20260116090151/https://www.postnord.se/en/business/import-export-customs/customs-documents-and-shipping-documents/)) unless noted.

| Product group | Value | Structured data | Physical documents |
|---|---|---|---|
| Letters (Varubrev, Export Letter, Tracked, Registered) | ≤ SEK 2 000, not commercial | CN22 | CN22 glued on the item |
| Letters | > SEK 2 000 or commercial | CN23 and invoice | CN23 and commercial invoice |
| Service Point, MyPack Home, Pallet, Parcel | any | invoice, not CN22/CN23 | shipping document and invoice "in triplicate" |
| Postpaket Utrikes, EMS, International Parcel | ≤ SEK 2 000 | CN23 | CN23 |
| Postpaket Utrikes, EMS, International Parcel | > SEK 2 000 or commercial | CN23 and invoice | CN23 and invoice ×2 (W [Postpaket Utrikes terms, valid 2025-05-02](https://api2.postnord.com/rest/customer/v2/ptm/file/download/5341.28764?disposition=inline)) |

PostNord's SEK 2 000 threshold is stricter than the UPU 300 SDR (about SEK 4 000, I).
Commercial items require an EORI, personal identity number, or VOEC number; Norway always requires VOEC (W same page).
Letters with goods leaving the EU require customs data sent electronically in advance from 2026-01-01 (W [Brev utrikes 2026](https://api2.postnord.com/rest/customer/v2/ptm/file/download/5191.29333?disposition=inline)).
Service Point special terms §4 (valid 2026-01-01): a commercial invoice "in at least two copies in English shall accompany the parcel", in a plastic pocket on parcel no. 1; "To Norway the commercial invoice and shipment list shall be sent digitally"; digital data prevails over paper on discrepancy (W [avropa.se PDF](https://www.avropa.se/globalassets/bilagor/1.-aktuella-rao/postformedlingstjanster-2021/paketformedlingstjanster--1-lev-postnord/sarskilda-villkor-service-point-2026.pdf)).
The copy count differs between sources ("triplicate" versus "at least two"); unresolved.

### Fees (PostNord SE credit-customer price list, valid 2026-05-04, pp. 20-22)

Source: W [price list PDF](https://api2.postnord.com/rest/customer/v2/ptm/file/download/5115.29793?disposition=inline); table extraction was garbled, so pairings are approximate.

| Item | Fee |
|---|---|
| Customs clearance (Förtullningsavgift), by Incoterm and destination | about SEK 295–350 (Norway, Åland, non-EU), SEK 600 (Switzerland), SEK 30 per parcel DDP VOEC |
| Missing digital customs invoice | SEK 75 |
| Customs invoice with missing EDI | SEK 250 |
| Incomplete or incorrect EDI | SEK 55 per line |
| Incomplete TVINN information | SEK 500/h, minimum SEK 2 000 |

No separate fee for PostNord producing the export declaration was found; transmitting `customsInvoice` data carries no fee, while omitting it can incur penalties (I).

### Requirements by shipper country

PostNord business units publish different rules for the same question, so the shipper country is a dimension of its own.
Most PostNord pages refuse automated fetches; the sources below were read on 2026-09-25 either live or via Wayback snapshots.

| Shipper | Invoice data via EDI | Physical invoice with the parcel | Separate channel | Copies | Signature | Threshold |
|---|---|---|---|---|---|---|
| SE | Booking API; required digitally to Norway | yes, except to Norway (digital only) | Norway only: Booking API, Skicka Direkt Business, foravisering.export@postnord.com, MyCustoms upload | English page 3, Swedish page 2 (conflict); 3 for Postpaket Utrikes | "usually signed by hand" | invoice above SEK 2 000 for letters and postal parcels; any value for Service Point, MyPack, Parcel, Pallet |
| FI | required; clearance "primarily based on" EDI | web page: optional ("attached to the shipment or submitted separately"); terms 2026-05-01: signed, triplicate | tullaus.fi@postnord.com | page: not stated; terms: 3 | page: "if necessary", not for authorized exporters; terms: signed | none stated; export clearance included up to 5 items |
| DK | required via ToldAPI for non-EU | yes, plastic pocket visible on the parcel; rest of world invoice "not required" but recommended | eksport@postnord.com (export declaration copy only) | Norway 2, Switzerland and Liechtenstein 3, UK 2, rest of world 1 CN23 and 2 invoices | not stated | export declaration above DKK 7 500 |
| NO | customs EDI required since 2021 (import context) | not found | fortolling.no@postnord.com (enquiries) | not found | not found | fees only (see below) |

PostNord SE sources: W Swedish customs documents page (Wayback 2026-02-08, `postnord.se/foretag/import-export-tull/tulldokument-och-frakthandlingar-for-foretag/`), which names the Norway channels and describes [MyCustoms](https://mycustoms.postnord.com/) as a place to "förse oss med tullinformation, eller ladda upp en tullfaktura"; W English page (Wayback 2026-01-16, cited above).
Neither 2026 SE web snapshot contains the plastic-pocket wording for invoices; that wording comes from the Service Point special terms cited above (I).
None of the SE separate channels is stated to apply to destinations other than Norway.

PostNord FI: W [postnord.fi customs information](https://www.postnord.fi/en/sending/online-tools/customs-information/) (quote and URL supplied by the user 2026-09-25; page shows only "published 2020-06-03"):
"electronic customs data (EDI) must be submitted to customs for shipments [...]. Customs clearance is primarily based on this electronic data. The commercial or proforma invoice serves as a supporting document for customs clearance [...]. If necessary, the invoice can be attached to the shipment or submitted separately to support customs clearance. A copy of the invoice can be sent by email to address tullaus.fi@postnord.com [...]. Original invoices must be prepared in English and signed by hand if necessary (a signature is not required if the company is an authorized exporter for customs)."
The same page states that for Norway EDI must arrive before the shipment, and that Åland is inside the EU customs territory but outside the VAT territory.
A Wayback snapshot of the same URL dated 2025-12-10 read "A copy [...] must be sent by e-mail [...] originals [...] attached in a plastic folder [...] at least three copies and signed by hand", and the FI special terms for parcels valid 2026-05-01 (Wayback 2026-06-10) still require "a signed commercial invoice in English in triplicate" for non-EU parcels and electronic invoices to Norway, with EDI prevailing over the shipping document on discrepancy.
The web page appears relaxed after December 2025 while the contract terms were not (I); the "submitted separately" option is web guidance only.

PostNord DK: W `postnord.dk/erhverv/eksport/` (Wayback 2026-03-10); Svalbard parcels need an invoice on each parcel or within 7 days.
PostNord NO: W `postnord.no/motta/toll-for-netthandlere` and `postnord.no/tjenester-bedrift/digitoll/` (read 2026-09-25) cover import; no export invoice rule was found.
PostNord NO price list valid 2025-07-01 (W, Wayback 2025-11-19): export clearance NOK 244, import clearance outside EU NOK 829, own-clearance administration NOK 333 per invoice, invoice error NOK 150.

The earlier live verification of an SE to PL export letter (`docs/notes/postnord/customs-declaration-live-verification.md`) is consistent with electronic CN22 submission and an EORI requirement, and says nothing about paper invoices.

### Product code for Postpaket Utrikes

Code 91 in karrio is the contract and EDI product: `units.py:146` `postnord_postpaket_utrikes = "91"` matches "91 Z91 Postpaket Utrikes" in `vendor/docs/general-descriptions.pdf` and "International Parcel(91)" in `vendor/delivery-options.swagger.json:5` (S).
Code 95 is the direct-payment customer product "Parcel Post International (Postpaket Utrikes)" (W PostNord terms valid 2025-05-02, PTM file 5341.28763), which requires two CN23 copies and "three copies of the commercial invoice [...] with the parcel" above SEK 2 000 or for commercial purposes.
No change to karrio's code is indicated (I).

## DHL Freight Sweden

Primary sources: W [Product manual v5.23, valid 2025-04-14](https://dhlpaket.se/dashboard/wp-content/uploads/sites/2/2025/04/DHL-FREIGHT-SWEDEN-PRODUCT-MANUAL-v5.23.pdf) (MAN); W [Customs information – Export from Sweden, 2025-02-03](https://www.dhl.com/content/dam/dhl/local/se/dhl-freight/documents/pdf/se-freight-customs-information-export-en.pdf) (CIE); W [Prislista tulltjänster, valid 2026-05-01](https://www.dhl.com/content/dam/dhl/local/se/dhl-freight/documents/pdf/se-freight-price-list-additional-services-sv.pdf) (PRL); W [Charge codes v1.8](https://dhlpaket.se/dashboard/wp-content/uploads/sites/2/2025/04/DHL-Freight-Sweden-CHARGE-CODES-in-INVOICE-files-v1.8.pdf) (CHG).
Vendored specs are under `modules/connectors/dhl_freight_sweden/vendor/se-api-farm/` and carry no descriptions on customs objects.

### API surface

The transport instruction carries `customsInformation{customsDocuments[], customsCommodities[]}` (S `transport-instruction-2.10.0.json` `CustomsInformation`, up to 999 documents).
`CustomsDocument` fields: `id` (the invoice number, AN..35 per MAN p.99), `type` (CommercialInvoice, ProformaInvoice, ExportLicence, T1Note, SAD), `transportMovement` (Export, Import), `invoiceDate`, `invoiceCurrency`, `invoiceAmount`, `eori` (S `components.schemas.CustomsDocument`).
The Print API `ReportOptions` returns label, shipmentList, waybill, guarantee, returnLabel, qrCode, and licensePlateBarCode only; no customs or invoice document (S `print-api-2.10.0.json`).
No attachment or upload endpoint exists (S).

### Current connector behaviour

The connector maps `customs.invoice`, `invoice_date`, `commercial_invoice`, currency, and declared value into `CustomsDocument`, with `transportMovement` Export for non-Swedish destinations (S `modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/shipment/create.py:139-156, 293-309`).
It does not map `eori`, `CustomsCommodity.certificateOfOrigin`, `customsClearanceInstruction`, `customsDeclarationNumberABT`, or any customs additional service.
MAN limits goods description to AN..26 and statistical number to AN..14, narrower than the spec's 35 and 38.

### Products and destinations (MAN)

| Product | Norway | Switzerland | Great Britain |
|---|---|---|---|
| 102 Paket, 210 Pall, 211 Stycke, 212 Parti, 103/104 Service Point | Sweden only | — | — |
| 109 Parcel Connect | yes | no | separate agreement |
| 112 Parcel Connect Plus | yes | no | separate agreement |
| 202 Euroconnect, 205 Euroline, 232 Euroconnect Plus, 233 Eurapid, 601, SPI | yes | yes | yes |

Customs handling (Standard or Full service) or own declaration must be selected for CH, GB, NO, Åland (FI 22) and other non-EU destinations (W MAN §7.6.1, §6.7).

### Customs modes and fees

| API key | Meaning (W MAN) | Products | Fee per shipment (W PRL) |
|---|---|---|---|
| `customsHandlingStandard` | customer supplies complete EDI data (EORI, invoice id/type/date, HS lines) plus an invoice copy | 109, 112 to NO and Åland | 75 kr (109), 200 kr (112) |
| `customsHandlingFullService` | DHL keys data from the invoice copy | 109, 112, road freight | 155 kr (109), 360 kr (112); road freight 315 kr plus 305 kr third-country forwarding (410 kr GB) |
| `customsCustomersOwnDeclaration` | customer or own agent declares; `customsId` (MRN) required; separate agreement | as Full service | road freight 575 kr (660 kr GB); no line for 109/112 though charge code TUD exists (W CHG) |
| `customsJointDeclaration` | joint declaration against summary invoice; pre-approved customers | 210 and international except 107 | by agreement |
| `voecSupplyVAT` | VOEC with Parcel Connect to Norway | 109 | not listed |

No fee-free customs mode exists for non-EU destinations (W PRL; I for 109/112 own declaration).
Price quote lists `customsHandling` as enum Full, Standard, Own, Joint (S `pricequote-api-2.10.0.json` `AdditionalService`).

### Physical and separate documents

"A copy of the invoice must still be sent" even with complete EDI data under Standard (W MAN §7.6.2).
The invoice copy is emailed to dhlfreight.int.se@dhl.com shortly after booking, or uploaded in myDHL Freight, one document per shipment with a clear reference (W CIE p.9).
For 109, "Two copies of customs documents must also be attached on the outside of the package" (W MAN p.66); unconfirmed for 112 and road freight.
Missing documents stop the shipment, with reminder fees of 390 kr (650 kr GB) (W CIE p.12; PRL).
Norway VOEC ID must be printed on the package or label (W MAN pp.97, 99).
The invoice is free-form but must follow Tullverket content guidelines: seller and buyer with VAT or organisation number (importer EORI for GB), date, invoice number, packages and gross weight, goods description and HS codes, quantity, price per HS code and currency, discounts, delivery terms matching the booking, net weight and origin per HS code (W CIE pp.5-6).
No DHL invoice template for Sweden exports was found (W).

## Other DHL connectors (for comparison)

| Connector | Invoice mechanism | Documents returned |
|---|---|---|
| dhl_express | carrier-generated (`UseDHLInvoice`) or own files inline via `DocImages` with special service WY when `dhl_paperless_trade` is set (S `.../dhl_express/shipment.py:292-295, 380-386, 535-544`) | `docs.invoice` from `CustomInvoiceImage` |
| mydhl | own files uploaded after booking via PATCH `/shipments/{awb}/upload-image` (S `.../mydhl/proxy.py:51-66, 150-170`) | label only |
| dhl_parcel_de | carrier-generated `customsDoc` (CN23 per spec) | `docs.invoice` (mislabelled, I) |
| dhl_poland | carrier-generated proforma (`fvProformaContent`) | `docs.invoice` |
| dhl_universal | tracking only | — |

## Advisory channel in karrio

`Message` has `message`, `level`, `code`, `details` (S `modules/sdk/karrio/core/models.py:325`); PostNord rating already emits `level="warning"` (S `modules/connectors/postnord/karrio/providers/postnord/rate.py:85-95`).
Messages persist on `Shipment.messages` and do not fail the purchase when a shipment is returned (S `modules/core/karrio/server/core/gateway.py:309-315, 424`).
`EUCountry` stores Greece as `EL` and neither `Country` nor `EUCountry` has `AX` or `XI`; no postcode-based territory detection exists (S `modules/sdk/karrio/core/units.py:1936, 2882-2894`).

## Open questions

- PostNord NO rules for Norwegian shippers exporting (no official source found).
- PostNord SE invoice copy count: English page "triplicate" versus Swedish page "två exemplar".
- Whether PostNord FI's relaxed web guidance or its 2026 contract terms govern.
- Whether DHL Freight Sweden 112 and road-freight products require copies attached to the outside of the package.
- Whether DHL Freight Sweden bills own declaration on 109/112.

## Out-of-scope follow-ups

- dhl_parcel_de places the carrier CN23 `customsDoc` in `docs.invoice` rather than `extra_documents` as a customs declaration.
- `EUCountry` Greece `EL` versus `GR`, missing `AX` and `XI`; DHL Express dutiable logic inherits the Greece misclassification (S `.../dhl_express/shipment.py:149-152`).
- Server `invoice_template` rendering overwrites a carrier-returned invoice (S `modules/manager/karrio/server/manager/serializers/shipment.py:748, 1049-1080`).
- `paperless` capability is inferred from proxy method names, so dhl_express reports it although its `upload_document` raises `MethodNotSupported` (S `.../dhl_express/proxy.py:53-54`).
- mydhl defines WY and PM value-added services that no provider code emits (S `.../mydhl/units.py:147, 198`).
