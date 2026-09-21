"""PostNord customs declaration proxy tests (connector-local capability)."""

import json
import unittest
from unittest.mock import patch

import karrio.lib as lib
import karrio.schemas.postnord.customs_declaration_request as postnord_req
import karrio.providers.postnord.customs as customs

from .fixture import gateway


ItemId = "00373500454541020957"


def _declaration(lines: int = 1) -> postnord_req.CustomsDeclarationRequestType:
    """A minimal CN22 declaration for one booked item id, at ``lines`` rows."""
    return postnord_req.CustomsDeclarationRequestType(
        messageDate="2026-06-24T10:00:00",
        messageFunction="Customsdeclaration",
        language="EN",
        updateIndicator="Original",
        testIndicator=True,
        ids=[postnord_req.IDType(id=ItemId, idType="ITEMID")],
        customsDeclarationCN22=postnord_req.CustomsDeclarationCN22Type(
            countryOfOrigin="SE",
            EORIorPersonalIdNumber="SE5561234711",
            categoryOfItem=postnord_req.CategoryOfItemType(categoryType=["GIFT"]),
            detailedDescription=[
                postnord_req.CustomsDeclarationCN22DetailedDescriptionType(
                    content=f"Item {index}",
                    quantity=postnord_req.TotalNumberOfPackagesType(value=1),
                    grossWeight=postnord_req.WeightType(value=0.5, unit="KGM"),
                    value=postnord_req.PostalChargesType(amount=10.0, currency="SEK"),
                    hsTariffNumber="07019010",
                    countryCode="SE",
                    rowNo=index,
                )
                for index in range(1, lines + 1)
            ],
            totalGrossWeight=postnord_req.WeightType(value=0.5, unit="KGM"),
            totalValue=postnord_req.PostalChargesType(amount=10.0, currency="SEK"),
        ),
    )


class TestPostNordCustomsDeclaration(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_create_customs_declaration_request(self):
        # The wire body is the [declaration] array envelope; digit-only
        # string fields (hsTariffNumber "07019010") pass through as
        # strings, never int-coerced.
        request = customs.customs_declaration_request(
            _declaration(), gateway.settings
        )
        self.assertEqual(lib.to_dict(request.serialize()), DeclarationWireBody)
        self.assertEqual(request.ctx, {})

    def test_create_customs_declaration_request_pdf_params(self):
        # Rendering params ride the ctx as query-string entries, not the body.
        request = customs.customs_declaration_request(
            _declaration(),
            gateway.settings,
            paper_size="A4",
            rotate="90",
            multi_pdf=True,
            page_horizontal_align="CENTER",
            page_vertical_align="CENTER",
        )
        self.assertEqual(lib.to_dict(request.serialize()), DeclarationWireBody)
        self.assertEqual(
            request.ctx,
            {
                "paperSize": "A4",
                "rotate": "90",
                "multiPDF": "true",
                "pageHorizontalAlign": "CENTER",
                "pageVerticalAlign": "CENTER",
            },
        )

    def test_create_customs_declaration_request_requires_an_id(self):
        declaration = _declaration()
        declaration.ids = []
        with self.assertRaises(lib.exceptions.FieldError) as raised:
            customs.customs_declaration_request(declaration, gateway.settings)
        self.assertIn("ids requires exactly 1", raised.exception.details["ids"])

    def test_create_customs_declaration_request_rejects_multiple_ids(self):
        declaration = _declaration()
        declaration.ids = [
            postnord_req.IDType(id=ItemId, idType="ITEMID"),
            postnord_req.IDType(id="00373500454541020958", idType="ITEMID"),
        ]
        with self.assertRaises(lib.exceptions.FieldError) as raised:
            customs.customs_declaration_request(declaration, gateway.settings)
        self.assertIn("at most 1", raised.exception.details["ids"])

    def test_create_customs_declaration_request_requires_one_branch(self):
        declaration = _declaration()
        declaration.customsDeclarationCN22 = None
        with self.assertRaises(lib.exceptions.FieldError) as raised:
            customs.customs_declaration_request(declaration, gateway.settings)
        self.assertIn(
            "exactly one of", raised.exception.details["declaration"]
        )

    def test_create_customs_declaration_request_rejects_multiple_branches(self):
        declaration = _declaration()
        declaration.customsDeclarationCN23 = postnord_req.CustomsDeclarationCN23Type(
            detailedDescription=[
                postnord_req.CustomsDeclarationCN22DetailedDescriptionType(
                    content="Item 1", rowNo=1
                )
            ]
        )
        with self.assertRaises(lib.exceptions.FieldError) as raised:
            customs.customs_declaration_request(declaration, gateway.settings)
        self.assertIn(
            "exactly one of", raised.exception.details["declaration"]
        )

    def test_create_customs_declaration_lines_at_limit(self):
        # 13 rows is the inclusive boundary and is sent in full.
        request = customs.customs_declaration_request(
            _declaration(lines=13), gateway.settings
        )
        body = lib.to_dict(request.serialize())
        self.assertEqual(
            len(body[0]["customsDeclarationCN22"]["detailedDescription"]), 13
        )

    def test_create_customs_declaration_lines_over_limit(self):
        # The shared 13-line guard (same helper as the booking path) fires
        # at build time — no HTTP call — and names the caller-supplied id.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            with self.assertRaises(lib.exceptions.FieldError) as raised:
                customs.customs_declaration_request(
                    _declaration(lines=14), gateway.settings
                )
            mock.assert_not_called()
        self.assertEqual(
            raised.exception.details["customsDeclarationCN22.detailedDescription"],
            "customsDeclarationCN22.detailedDescription exceeds the 13-line "
            f"customs declaration limit for item {ItemId}",
        )

    def test_create_customs_declaration(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = DeclarationResponse
            request = customs.customs_declaration_request(
                _declaration(), gateway.settings
            )
            result, messages = customs.parse_customs_declaration_response(
                gateway.proxy.create_customs_declaration(request),
                gateway.settings,
            )
            self.assertEqual(
                mock.call_args.kwargs["url"],
                f"{gateway.settings.server_url}"
                "/rest/shipment/v3/customs/declaration?apikey=TEST_API_KEY",
            )
            self.assertEqual(mock.call_args.kwargs["method"], "POST")
            self.assertEqual(
                json.loads(mock.call_args.kwargs["data"]), DeclarationWireBody
            )
        self.assertEqual(messages, [])
        self.assertEqual(result, ParsedDeclaration)

    def test_parse_customs_declaration_accepts_wrapped_envelope(self):
        # The PDF variant's wrapped envelope fed through the digital parse
        # path yields the same acceptance — the parser is shape-tolerant.
        result, messages = customs.parse_customs_declaration_response(
            lib.Deserializable(DeclarationWrappedResponse, lib.to_dict),
            gateway.settings,
        )
        self.assertEqual(messages, [])
        self.assertEqual(result, ParsedDeclaration)

    def test_create_customs_declaration_pdf(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = DeclarationPdfResponse
            request = customs.customs_declaration_request(
                _declaration(),
                gateway.settings,
                paper_size="A4",
                rotate="90",
                multi_pdf=True,
            )
            result, messages = customs.parse_customs_declaration_pdf_response(
                gateway.proxy.create_customs_declaration_pdf(request),
                gateway.settings,
            )
            self.assertEqual(
                mock.call_args.kwargs["url"],
                f"{gateway.settings.server_url}"
                "/rest/shipment/v3/customs/declaration/pdf"
                "?apikey=TEST_API_KEY&paperSize=A4&rotate=90&multiPDF=true",
            )
            self.assertEqual(mock.call_args.kwargs["method"], "POST")
            self.assertEqual(
                json.loads(mock.call_args.kwargs["data"]), DeclarationWireBody
            )
        self.assertEqual(messages, [])
        self.assertEqual(lib.to_dict(result), ParsedPdfDeclaration)

    def test_parse_customs_declaration_rejection(self):
        # An upstream rejection (no prior EDI for the id) surfaces as
        # unified messages; no partial result is reported.
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = DeclarationRejectedResponse
            request = customs.customs_declaration_request(
                _declaration(), gateway.settings
            )
            result, messages = customs.parse_customs_declaration_response(
                gateway.proxy.create_customs_declaration(request),
                gateway.settings,
            )
        self.assertIsNone(result)
        self.assertEqual(lib.to_dict(messages), ParsedRejection)

    def test_parse_customs_declaration_pdf_rejection(self):
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = DeclarationRejectedResponse
            request = customs.customs_declaration_request(
                _declaration(), gateway.settings
            )
            result, messages = customs.parse_customs_declaration_pdf_response(
                gateway.proxy.create_customs_declaration_pdf(request),
                gateway.settings,
            )
        self.assertIsNone(result)
        self.assertEqual(lib.to_dict(messages), ParsedRejection)


if __name__ == "__main__":
    unittest.main()


DeclarationWireBody = [
    {
        "messageDate": "2026-06-24T10:00:00",
        "messageFunction": "Customsdeclaration",
        "language": "EN",
        "updateIndicator": "Original",
        "testIndicator": True,
        "ids": [{"id": ItemId, "idType": "ITEMID"}],
        "customsDeclarationCN22": {
            "countryOfOrigin": "SE",
            "EORIorPersonalIdNumber": "SE5561234711",
            "categoryOfItem": {"categoryType": ["GIFT"]},
            "detailedDescription": [
                {
                    "content": "Item 1",
                    "quantity": {"value": 1},
                    "grossWeight": {"value": 0.5, "unit": "KGM"},
                    "value": {"amount": 10.0, "currency": "SEK"},
                    "hsTariffNumber": "07019010",
                    "countryCode": "SE",
                    "rowNo": 1,
                }
            ],
            "totalGrossWeight": {"value": 0.5, "unit": "KGM"},
            "totalValue": {"amount": 10.0, "currency": "SEK"},
        },
    }
]

# The digital endpoint returns the bare bookingResponseCN (swagger:
# POST /rest/shipment/v3/customs/declaration 200 -> bookingResponseCN).
DeclarationResponse = """{
  "bookingId": "3YSFH8NG0LNREZO38UIN68B3RRWL4X",
  "idInformation": [{
    "status": "OK",
    "references": {
      "shipment": [
        {"referenceNo": "ORDER-7788", "referenceType": "CU", "referenceDesc": "Customer order number"}
      ],
      "item": [
        {"referenceNo": "ITEM-1", "referenceType": "ON", "referenceDesc": "Item reference"}
      ]
    },
    "ids": [
      {"idType": "itemId", "value": "00373500454541020957", "printId": "31eed2dad84b48a2ba92a26590a0a69f"}
    ]
  }]
}"""

# The PDF variant's wrapped envelope; fed to the digital parse path it
# must yield the same acceptance (parser shape tolerance).
DeclarationWrappedResponse = """{
  "bookingResponse": {
    "bookingId": "3YSFH8NG0LNREZO38UIN68B3RRWL4X",
    "idInformation": [{
      "status": "OK",
      "references": {
        "shipment": [
          {"referenceNo": "ORDER-7788", "referenceType": "CU", "referenceDesc": "Customer order number"}
        ],
        "item": [
          {"referenceNo": "ITEM-1", "referenceType": "ON", "referenceDesc": "Item reference"}
        ]
      },
      "ids": [
        {"idType": "itemId", "value": "00373500454541020957", "printId": "31eed2dad84b48a2ba92a26590a0a69f"}
      ]
    }]
  }
}"""

ParsedDeclaration = {
    "booking_id": "3YSFH8NG0LNREZO38UIN68B3RRWL4X",
    "id_information": [
        {
            "status": "OK",
            "ids": [{"id_type": "itemId", "value": "00373500454541020957"}],
            "references": {
                "shipment": [
                    {
                        "reference_no": "ORDER-7788",
                        "reference_type": "CU",
                        "reference_desc": "Customer order number",
                    }
                ],
                "item": [
                    {
                        "reference_no": "ITEM-1",
                        "reference_type": "ON",
                        "reference_desc": "Item reference",
                    }
                ],
            },
        }
    ],
}

DeclarationPdfResponse = """{
  "bookingResponse": {
    "bookingId": "3YSFH8NG0LNREZO38UIN68B3RRWL4X",
    "idInformation": [{
      "status": "OK",
      "ids": [
        {"idType": "itemId", "value": "00373500454541020957", "printId": "31eed2dad84b48a2ba92a26590a0a69f"}
      ]
    }]
  },
  "labelPrintout": [{
    "itemIds": ["00373500454541020957"],
    "printout": {"type": "LABEL", "labelFormat": "PDF", "encoding": "base64", "data": "JVBERi0xLjQK"},
    "printoutComposition": {"label": 0, "cn22": 2, "cn23": 0, "customsInvoice": 0}
  }]
}"""

ParsedPdfDeclaration = {
    "booking_id": "3YSFH8NG0LNREZO38UIN68B3RRWL4X",
    "id_information": [
        {
            "status": "OK",
            "ids": [{"id_type": "itemId", "value": "00373500454541020957"}],
        }
    ],
    "documents": [{"category": "cn22", "format": "PDF", "base64": "JVBERi0xLjQK"}],
}

DeclarationRejectedResponse = """{
  "message": "The request could not be processed",
  "compositeFault": {
    "faults": [
      {"faultCode": "CNC-001", "explanationText": "EDI must have been sent earlier"}
    ]
  }
}"""

ParsedRejection = [
    {
        "carrier_id": "postnord",
        "carrier_name": "postnord",
        "code": "CNC-001",
        "message": "EDI must have been sent earlier",
        "details": {},
    }
]
