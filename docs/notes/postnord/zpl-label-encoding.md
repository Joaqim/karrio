# PostNord ZPL label transport encoding (spec gap)

2026-09-03

The Booking API swagger documents `labelPrintout[].printout.encoding` as
base64 only:

```json
"encoding": {
  "type": "string",
  "description": "Encoding of the data (base64)",
  "example": "base64"
}
```

(vendor/booking.swagger.json, definitions.encoding, ~line 3947; no enum.)

A live capture from `POST /rest/shipment/v3/edi/labels/zpl` contradicts
this: the printout carries `encoding: "none"` with raw UTF-8 ZPL text in
`data` (base64 never contains `^` or literal newlines, so the distinction
is unambiguous):

```json
"labelPrintout": [{
  "printout": {
    "type": "LABEL",
    "encoding": "none",
    "data": "^LL1520\n^FX utf-8^FS    ^CI28\n^PON\n^XA\n^CWW,E:ARI000.TTF\n..."
  }
}]
```

## Observations on the ZPL body

`^LL1520` sets label length 1520 dots = 190 mm at 8 dots/mm, matching the
swagger's own Labelary instruction ("Set LabelSize to 105x190mm" on the
`createEDILabelZPL` operation). `^CI28` declares UTF-8 (ZPL has no BOM
concept; the preceding `^FX utf-8` is a comment). The `^CWW,E:…TTF` lines
are `^CW` font-designator assignments aliasing printer-memory fonts — part
of the label payload, preserved verbatim by the connector.

The captured fragment opened with a bare `XA` (no caret) before the first
`^XA`; treated as a paste truncation, but worth re-checking on the next
live capture.

## Connector handling

`shipment/create.py` normalizes per printout: `encoding == "base64"`
passes through; anything else (including `"none"` and absent) is treated
as raw UTF-8 text and base64-encoded, because karrio's label pipeline
(`bundle_zpls`, server document serving) expects base64 inputs. The
request-level `label_type` (or connection config `label_type`) selects
`/labels/zpl` vs `/labels/pdf` in the proxy.

If PostNord later documents `encoding` as an enum (`none` | `base64`…),
this note and the parser branch should be reconciled against it.
