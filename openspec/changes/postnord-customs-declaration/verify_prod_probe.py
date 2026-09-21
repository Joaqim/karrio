"""Production probe for the PostNord customs-declaration change (task 5.2).

Run from the repository root with the production key supplied via env
(never paste keys into the session):

    source bin/activate-env
    POSTNORD_LIVE_APIKEY=... python openspec/changes/postnord-customs-declaration/verify_prod_probe.py

Environment:
    POSTNORD_LIVE_APIKEY   required; PRODUCTION apikey (api2.postnord.com)
    POSTNORD_ITEM_ID       optional; real booked item id (default UX478114854SE)
    POSTNORD_EORI          optional; production EORI threaded onto the CN22
    POSTNORD_PRINT_ID      optional; the booking's printId (hex) — when set,
                           additionally probes the by-id fetch with it, since
                           the swagger's assignedIds.printId description names
                           /v3/labels/ids/{pdf,zpl} as the printId consumer
                           while the request examples are item-id shaped
    POSTNORD_ID_TYPE       optional; idType for the declaration ids entry
                           (default itemId; the swagger prose lists ITEMID
                           uppercase — retry with ITEMID if production
                           rejects the camelCase form)
    POSTNORD_SUBMIT        set to 1 to additionally POST the declaration
                           update (mutating: probe 3 digital, probe 4
                           PDF-variant — only run against a sacrificial
                           booking)

Probes:
    1  by-id PDF fetch, unrestricted — read-only render; captures the
       authoritative labelPrintout success envelope for a real booking
    2  by-id PDF fetch restricted to customs declarations — read-only;
       shows whether a standalone customs printout exists for the item
    1b/2b  the same pair keyed by printId, the live-verified key
    2c  by-id ZPL fetch restricted to customs declarations, printId key —
        read-only; answers whether a thermal-printer customs printout is
        offered for the declared item
    3  opt-in digital declaration POST — re-declares the item with a
       one-line merchandise CN22 (updateIndicator=Update over the existing
       Original) and captures the success envelope
    4  opt-in PDF-variant declaration POST — same declaration against
       /customs/declaration/pdf with A4 rendering params; saves the
       rendered, pre-filled CN22 for eye verification
    5  post-update by-id ZPL fetch — read-only after probes 3-4; saves
       the updated CN22 as ZPL for thermal-printer verification

Note: an intra-EU item may be rejected by the customs rules engine as not
applicable — a rejection is itself recorded evidence.

The apikey is never printed. Paste the output back into the session for
recording under docs/notes/.
"""

import base64
import json
import os
import sys

import karrio.lib as lib

HOST = "https://api2.postnord.com"
ITEM_ID = os.environ.get("POSTNORD_ITEM_ID", "UX478114854SE")


def _summarize(body):
    """Per-entry summary of a by-id labelPrintout response.

    The raw body interleaves a large base64 printout.data BEFORE
    printoutComposition, so any fixed-length slice hides the composition;
    print the decision-relevant fields instead of the payload.
    """
    try:
        entries = json.loads(body)
    except (TypeError, ValueError):
        return str(body)[:300]
    if not isinstance(entries, list):
        return str(body)[:600]
    return _summarize_entries(entries)


def _summarize_entries(entries):
    lines = []
    for entry in entries:
        if not isinstance(entry, dict):
            lines.append(repr(entry)[:200])
            continue
        for member in entry.get("itemIds") or []:
            if not isinstance(member, dict):
                lines.append(f"  id-member: {member!r}")
                continue
            line = (
                f"  id={member.get('itemIds')} status={member.get('status')}"
                f" printId={member.get('printId')}"
            )
            error = (member.get("errorResponse") or {}).get("message")
            if error:
                line += f" error={error!r}"
            lines.append(line)
        printout = entry.get("printout") or {}
        data = printout.get("data")
        if data:
            magic = base64.b64decode(data)[:5]
            lines.append(
                f"  printout: type={printout.get('type')}"
                f" format={printout.get('labelFormat')}"
                f" data_len={len(data)} magic={magic!r}"
            )
        else:
            lines.append(f"  printout: {printout or 'absent (no data)'}")
        composition = entry.get("printoutComposition") or {}
        nonzero = {k: v for k, v in composition.items() if v}
        lines.append(f"  composition (nonzero): {nonzero or 'ALL ZERO'}")
    return "\n".join(lines)


def _post(key, path, body, extra_query=""):
    response = lib.request(
        url=f"{HOST}{path}?apikey={key}{extra_query}",
        data=json.dumps(body),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    return str(response)


PDF_DIR = os.environ.get(
    "POSTNORD_PDF_DIR",
    os.path.join(
        os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")),
        "agent-logs",
        "karrio",
        "postnord-customs-probe",
    ),
)


def _save_entries(entries, name, ext="pdf"):
    """Write the first data-bearing printout to a file for eye verification."""
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        data = (entry.get("printout") or {}).get("data")
        if not data:
            continue
        os.makedirs(PDF_DIR, exist_ok=True)
        path = os.path.join(PDF_DIR, f"{name}.{ext}")
        with open(path, "wb") as handle:
            handle.write(base64.b64decode(data))
        return path
    return None


def _save_printout(body, name, ext="pdf"):
    try:
        entries = json.loads(body)
    except (TypeError, ValueError):
        return None
    return _save_entries(entries, name, ext=ext)


def _run_probe(key, ids, name, extra_query="", endpoint="pdf", ext="pdf"):
    body = _post(key, f"/rest/shipment/v3/labels/ids/{endpoint}", ids, extra_query=extra_query)
    print(_summarize(body))
    saved = _save_printout(body, name, ext=ext)
    if saved:
        print(f"  saved {ext}: {saved}")


def main():
    if "POSTNORD_LIVE_APIKEY" not in os.environ:
        print("POSTNORD_LIVE_APIKEY is required (production key; api2 host is used)")
        return 2
    key = os.environ["POSTNORD_LIVE_APIKEY"]

    print(f"=== Probe 1: by-id PDF fetch, unrestricted (item {ITEM_ID}) ===")
    _run_probe(key, [{"id": ITEM_ID}], "probe1_itemid_unrestricted")

    print("\n=== Probe 2: by-id PDF fetch, onlyCustomsDeclarations ===")
    _run_probe(
        key,
        [{"id": ITEM_ID}],
        "probe2_itemid_onlyCustomsDeclarations",
        extra_query="&definePrintout=onlyCustomsDeclarations",
    )

    print_id = os.environ.get("POSTNORD_PRINT_ID")
    if print_id:
        print("\n=== Probe 1b: by-id PDF fetch, unrestricted, printId key ===")
        _run_probe(key, [{"id": print_id}], "probe1b_printid_unrestricted")
        print("\n=== Probe 2b: by-id PDF fetch, onlyCustomsDeclarations, printId key ===")
        _run_probe(
            key,
            [{"id": print_id}],
            "probe2b_printid_onlyCustomsDeclarations",
            extra_query="&definePrintout=onlyCustomsDeclarations",
        )
        print("\n=== Probe 2c: by-id ZPL fetch, onlyCustomsDeclarations, printId key ===")
        _run_probe(
            key,
            [{"id": print_id}],
            "probe2c_printid_onlyCustomsDeclarations_zpl",
            extra_query="&definePrintout=onlyCustomsDeclarations",
            endpoint="zpl",
            ext="zpl",
        )
    else:
        print("\n[probe 1b/2b skipped] set POSTNORD_PRINT_ID to also probe the printId key")

    if os.environ.get("POSTNORD_SUBMIT") != "1":
        print("\n[probes 3-5 skipped] set POSTNORD_SUBMIT=1 to POST the declaration update")
        return 0

    declaration = {
        "updateIndicator": "Update",
        "ids": [
            {
                "id": ITEM_ID,
                "idType": os.environ.get("POSTNORD_ID_TYPE", "itemId"),
            }
        ],
        "customsDeclarationCN22": {
            "countryOfOrigin": "SE",
            "categoryOfItem": {"categoryType": ["SALE OF GOODS"]},
            "detailedDescription": [
                {
                    "content": "Candy",
                    "quantity": {"value": 1},
                    "grossWeight": {"value": 0.38, "unit": "KGM"},
                    "value": {"amount": 30.0, "currency": "EUR"},
                    "hsTariffNumber": "1704906500",
                    "countryCode": "SE",
                    "rowNo": 1,
                }
            ],
            "totalGrossWeight": {"value": 0.51, "unit": "KGM"},
            "totalValue": {"amount": 30.0, "currency": "EUR"},
            **(
                {"EORIorPersonalIdNumber": os.environ["POSTNORD_EORI"]}
                if os.environ.get("POSTNORD_EORI")
                else {}
            ),
        },
    }

    print("\n=== Probe 3: digital declaration POST, candy-order Update (mutating) ===")
    print(_post(key, "/rest/shipment/v3/customs/declaration", [declaration])[:800])

    print("\n=== Probe 4: PDF-variant declaration POST, rendered CN22 (mutating) ===")
    pdf_body = _post(
        key,
        "/rest/shipment/v3/customs/declaration/pdf",
        [declaration],
        extra_query=(
            "&paperSize=A4&rotate=0&multiPDF=false&labelsPerPage=100&page=1"
            "&processOffline=false&storeLabel=false"
            "&pageHorizontalAlign=JUSTIFY&pageVerticalAlign=JUSTIFY"
        ),
    )
    try:
        parsed = json.loads(pdf_body)
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, dict):
        statuses = parsed.get("bookingResponseCN") or parsed
        print(f"  bookingResponseCN: {str(statuses)[:400]}")
        printouts = parsed.get("labelPrintout") or []
        print(_summarize_entries(printouts))
        saved = _save_entries(printouts, "probe4_declaration_pdf_rendered")
        if saved:
            print(f"  saved pdf: {saved}")
    else:
        print(pdf_body[:800])

    if print_id:
        print("\n=== Probe 5: post-update by-id ZPL fetch, onlyCustomsDeclarations ===")
        _run_probe(
            key,
            [{"id": print_id}],
            "probe5_postupdate_onlyCustomsDeclarations_zpl",
            extra_query="&definePrintout=onlyCustomsDeclarations",
            endpoint="zpl",
            ext="zpl",
        )

    print("\nDone. Paste this output back into the session for recording.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
