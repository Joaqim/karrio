# DHL Freight Sweden receiver-phone print rule — live label probe evidence

Bounded sandbox probes on 2026-09-10 settling whether the connector must gate consignee-phone transmission by destination country, and how label section 16 "Customer information" is populated for PUDO shipments.
All calls ran against `https://test-api.freight-logistics.dhl.com` with the standard `client-key` header.
The key value is never reproduced here; every artifact in the scratch directory was byte-scanned for it at capture time and none contains it.
Scratch directory: `~/.local/state/agent-logs/karrio/phone-print-probe/` (manuals preserved under `manuals/`).

## Probe 1 — forbidden direction (109 SE→DE residential): receiver phone suppressed server-side

Booked product 109 SE→DE to a Berlin residential address (booking 2906724865) with marker consignee phone `+49 170 7000 777`.
The transportInstruction response echoed the marker verbatim in the Consignee party (`countryCode: DE`, routingCode 2LDE10115+70000000).
The printed label (`label_2906724865.pdf`, 78,199 B, %PDF-1.6, clean text layer) contains no trace of the marker in any digit-normalized variant searched (491707000777, 1707000777, 7000777, raw spaced string).
Exactly one `Phn.` line exists on the label and it prints the sender's phone (+46 8 123 456); the receiver block carries no phone line, consistent with the manual reserving the DE phone slot for the >10 kg weight icon.
Verdict: DHL's print pipeline suppresses the receiver phone for forbidden-list destination DE even though the number is present in the shipment.
The manual's forbidden list (label section 9, products 109/112: AT, BE, DE, ES, FR, GB, LU, NL, PT) is enforced by the renderer, so the connector's unconditional `_party` phone send is label-compliant.

## Probe 2 — mandatory direction (109 SE→DK parcelshop): consignee phone not printed; slot follows the delivery party

By-id reprint of the existing booking 2906723800 (109 SE→DK parcelshop; consignee Mette Hansen `+45 32 12 34 56` carried in the shipment; DK is on the mandatory-if-present list).
The label (`label_2906723800.pdf`, 80,728 B, %PDF-1.6, clean text layer) contains no trace of 4532123456 in full or partial normalized search, and again exactly one `Phn.` line (the sender's).
The receiver block on the PUDO form shows the consignee name plus AccessPoint details; the phone slot stayed empty because the AccessPoint party carried no phone.
Interpretation: for PUDO-addressed shipments the receiver-phone slot (label section 9) renders the delivery party's phone, not the residential consignee's, whose details render in section 16 instead.
So even for a mandatory-list country, DHL did not print the residential consignee's mobile on a PUDO label.
Residual (unprobed, out of call budget): a residential-addressed booking to a mandatory-list country (e.g. DK/FI/PL home address) — whether that variant prints the consignee phone remains open.

## Probe 3 — machine-readable rule: absent from every machine source

- Vendored se-api-farm specs (13 files): `Party.phone` is a bare string (maxLength 64); no schema combines print with country; the additional-service-api spec has zero phone or print mentions.
- Live product-109 catalog capture: `rulesForCountryAndDeliveryTypes` carries only weight, dimension, customs-flag, and deliveryType rules per country; `customUsageRules` gates only VOEC, insurance, and dangerous-goods-LQ.
- Fresh `GET /productapi/v1/products/112`: 16,139 B, account-trimmed view with no `rulesForCountryAndDeliveryTypes` at all; `customUsageRules` appear only on insurance (VALIDATE), preAdviceByDriver (COUNTRY=SE:NO,FI), dangerousGoodsLimitedQuantity (COUNTRY=SE:DK,NO,DE), and deliveryWithoutProofOfDelivery (COUNTRY=SE:NO,DK).

The forbidden and mandatory country lists exist only in the product manual's label-section-9 rows; no catalog field encodes them.
Given probe 1, client-side encoding is unnecessary for label compliance and would only matter to warn or refuse at booking time.

## Section 16 "Customer information" (109 PUDO): auto-composed from the Consignee party

The DK PUDO label's bottom block renders, with no free text or party references sent by the connector:

    Mette Hansen Vesterbrogade 1
    DK 1620 København V

Content matches the manual's 109 PUDO section-16 rule: residential name and address, ISO country code in front of the postal code ("DK 1620"; the receiver block by contrast prints "1620 KØBENHAVN V / DENMARK"), no plain country name.
Typography deviates from the manual's self-print spec: the block is flush left (word xMin ~19 on a 297.6 pt page) and spans two rows, not right-aligned one-row — the Print API applies the content rule but not the self-print alignment rules.
"Mette Hansen" appears exactly twice on the label (receiver block and section 16), confirming two distinct renderings of the consignee.
Consequence: no request change is needed to satisfy the manual's mandatory section-16 content for 109 PUDO, because DHL composes it from the Consignee party.

Mapping research conclusion for custom section-16 text: `parties[].references` (array of strings, maxItems 99, maxLength 35 each) is the shipper-controlled free-text channel.
The sibling-platform global manual (Appendix Q) states that party-level references "are only used for printing on your labels" and that only the consignor and consignee roles print; the SE manual never names the section's request field explicitly, so the mapping rests on documented label-print semantics plus elimination.
Related observations: `pieces[].marksAndNumbers` prints as its own "Shipping mark:" line in the shipment-information block on both labels and is not the section-16 feed; "Senders ref:" and "Receivers ref:" label lines exist and stayed empty because no shipment references were sent.

## Manual sources

- `manuals/se-product-manual-v5.23.txt` (PDF-extracted text, 245 pages, v5.23 valid from 2025-04-14): label appendix 9.4.2 pp.172-187 (19 sections; the 109-specific section-16 rule at p.181), Appendix D phone validation p.200, Appendix E shipment-level reference qualifiers p.201.
- Appendix D constraints: exactly one prefix (0046/+46/46 etc.; foreign country prefixes OK, never a doubled form like +0046), then digits, dash, and space only; letters, slash, and dot are forbidden.
- `manuals/api-farm-manual.txt` (global Freight APIs, Sprint 2025/R01) and `manuals/farm-manual-v1.17.txt` (global API Farm excluding Sweden): Appendix Q party-reference print semantics cited above.

## Scratch artifacts

All under `~/.local/state/agent-logs/karrio/phone-print-probe/`:

| Artifact | Contents |
|---|---|
| de-booking-request.json / de-booking-response.json | Probe 1 booking call (109 SE→DE, marker phone) |
| de-print-request.json / de-print-response.json | Probe 1 by-id print call |
| label_2906724865.pdf / label_2906724865.txt | Probe 1 label bytes and extracted text |
| dk-reprint-request.json / dk-reprint-response.json | Probe 2 by-id reprint call |
| label_2906723800.pdf / label_2906723800.txt / label_2906723800-bbox.html | Probe 2 label bytes, extracted text, and word-bbox rendering |
| product-112-response.json | Probe 3 fresh products/112 capture |
| live-product-109-catalog.json / live-productmatches-se-pl.json | Earlier catalog captures cited by probe 3 |
| de-probe-plan.json | Drafted probe plan (catalog-validated before key staging) |
| probe.py.recovered / live-109-dk-booking-request.json / live-601-de-booking-request.json | Recovered probe driver and working booking shapes |
| findings-keyfree.md / live-probe-results.md | Pre-probe research record and raw probe log |
