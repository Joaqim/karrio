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
    POSTNORD_SUBMIT        set to 1 to additionally POST the digital
                           declaration (mutating: attaches a 2-line CN22 to
                           the item — only run against a sacrificial booking)

Probes:
    1  by-id PDF fetch, unrestricted — read-only render; captures the
       authoritative labelPrintout success envelope for a real booking
    2  by-id PDF fetch restricted to customs declarations — read-only;
       shows whether a standalone customs printout exists for the item
    3  opt-in digital declaration POST — captures the declaration success
       envelope (bare bookingResponseCN vs wrapped), settling the envelope
       question left open by the sandbox runs

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


def main():
    if "POSTNORD_LIVE_APIKEY" not in os.environ:
        print("POSTNORD_LIVE_APIKEY is required (production key; api2 host is used)")
        return 2
    key = os.environ["POSTNORD_LIVE_APIKEY"]

    print(f"=== Probe 1: by-id PDF fetch, unrestricted (item {ITEM_ID}) ===")
    print(_summarize(_post(key, "/rest/shipment/v3/labels/ids/pdf", [{"id": ITEM_ID}])))

    print("\n=== Probe 2: by-id PDF fetch, onlyCustomsDeclarations ===")
    print(
        _summarize(
            _post(
                key,
                "/rest/shipment/v3/labels/ids/pdf",
                [{"id": ITEM_ID}],
                extra_query="&definePrintout=onlyCustomsDeclarations",
            )
        )
    )

    print_id = os.environ.get("POSTNORD_PRINT_ID")
    if print_id:
        print("\n=== Probe 1b: by-id PDF fetch, unrestricted, printId key ===")
        print(_summarize(_post(key, "/rest/shipment/v3/labels/ids/pdf", [{"id": print_id}])))
        print("\n=== Probe 2b: by-id PDF fetch, onlyCustomsDeclarations, printId key ===")
        print(
            _summarize(
                _post(
                    key,
                    "/rest/shipment/v3/labels/ids/pdf",
                    [{"id": print_id}],
                    extra_query="&definePrintout=onlyCustomsDeclarations",
                )
            )
        )
    else:
        print("\n[probe 1b/2b skipped] set POSTNORD_PRINT_ID to also probe the printId key")

    if os.environ.get("POSTNORD_SUBMIT") != "1":
        print("\n[probe 3 skipped] set POSTNORD_SUBMIT=1 to POST the declaration")
        return 0

    declaration = {
        "ids": [
            {
                "id": ITEM_ID,
                "idType": os.environ.get("POSTNORD_ID_TYPE", "itemId"),
            }
        ],
        "customsDeclarationCN22": {
            "countryOfOrigin": "SE",
            "categoryOfItem": {"categoryType": ["merchandise"]},
            "detailedDescription": [
                {
                    "content": "Wool socks",
                    "quantity": {"value": 2},
                    "grossWeight": {"value": 0.4, "unit": "KGM"},
                    "value": {"amount": 2.5, "currency": "USD"},
                    "countryCode": "SE",
                    "rowNo": 1,
                },
                {
                    "content": "Postcard",
                    "quantity": {"value": 1},
                    "grossWeight": {"value": 0.1, "unit": "KGM"},
                    "value": {"amount": 1.0, "currency": "USD"},
                    "countryCode": "SE",
                    "rowNo": 2,
                },
            ],
            "totalValue": {"amount": 3.5, "currency": "USD"},
            **(
                {"EORIorPersonalIdNumber": os.environ["POSTNORD_EORI"]}
                if os.environ.get("POSTNORD_EORI")
                else {}
            ),
        },
    }

    print("\n=== Probe 3: digital declaration POST (mutating) ===")
    print(_post(key, "/rest/shipment/v3/customs/declaration", [declaration])[:800])

    print("\nDone. Paste this output back into the session for recording.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
