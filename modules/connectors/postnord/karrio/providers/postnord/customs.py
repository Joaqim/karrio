"""Karrio PostNord customs declaration (connector-local capability).

PostNord's Booking v3 customs API declares customs for an item whose EDI
booking was already sent: ``POST /rest/shipment/v3/customs/declaration``
(digital) and ``POST /v3/customs/declaration/pdf`` (PDF variant with
rendering query parameters and a ``labelPrintout`` response). Karrio has
no unified customs-declaration contract, so the capability is
connector-local like the service-points lookup: the caller builds the
typed declaration object (branch, ids, ``updateIndicator``) and invokes
``gateway.proxy.create_customs_declaration`` /
``create_customs_declaration_pdf``.

Karrio builds the wire envelope, parses the response, and reports — it
does not reconcile, replace, or verify previously submitted declarations;
declaration content is the caller's responsibility.
"""

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.schemas.postnord.customs_declaration_request as postnord_req
import karrio.schemas.postnord.customs_declaration_response as postnord_res
import karrio.providers.postnord.error as error
import karrio.providers.postnord.units as provider_units
import karrio.providers.postnord.utils as provider_utils
import karrio.providers.postnord.shipment.create as provider_shipment


# PostNord's one-branch constraint (swagger ``customsDeclaration``):
# exactly one of these per declaration object, and every branch carries
# its declaration lines under ``detailedDescription``.
_DECLARATION_BRANCHES = (
    "customsDeclarationCN22",
    "customsDeclarationCN23",
    "customsInvoice",
)


def customs_declaration_request(
    request: postnord_req.CustomsDeclarationRequestType,
    settings: provider_utils.Settings,
    paper_size: typing.Optional[str] = None,
    rotate: typing.Optional[str] = None,
    multi_pdf: typing.Optional[bool] = None,
    page_horizontal_align: typing.Optional[str] = None,
    page_vertical_align: typing.Optional[str] = None,
) -> lib.Serializable:
    """Wrap a caller-built declaration in the customs API wire envelope.

    Both endpoints take an array of declaration objects (swagger
    ``customsDeclarations``), each carrying exactly one id (``ids``
    maxItems 1) and one declaration branch; the builder enforces those
    envelope constraints plus the 13-line limit, then carries the PDF
    variant's rendering params as query-string entries on the ctx for
    ``proxy.create_customs_declaration_pdf``; submitting the same request
    through the digital ``create_customs_declaration`` leaves the ctx
    unused, as that endpoint takes no rendering params. Everything
    else — branch content, ``updateIndicator``, envelope header fields —
    passes through exactly as the caller built it.
    """
    ids = request.ids or []
    if len(ids) > 1:
        raise lib.exceptions.FieldError(
            {"ids": "ids accepts at most 1 item id per declaration object"}
        )
    if not ids:
        raise lib.exceptions.FieldError(
            {"ids": "ids requires exactly 1 item id per declaration object"}
        )

    branches = [
        name for name in _DECLARATION_BRANCHES if getattr(request, name)
    ]
    if len(branches) != 1:
        raise lib.exceptions.FieldError(
            {
                "declaration": (
                    "exactly one of "
                    + ", ".join(_DECLARATION_BRANCHES)
                    + " is required per declaration object"
                )
            }
        )

    branch = getattr(request, branches[0])
    provider_units.enforce_customs_declaration_lines(
        len(branch.detailedDescription or []),
        field=f"{branches[0]}.detailedDescription",
        item_id=ids[0].id,
    )

    return lib.Serializable(
        [request],
        lib.to_dict,
        ctx={
            key: value
            for key, value in {
                "paperSize": paper_size,
                "rotate": rotate,
                # urlencode renders bools as "True"/"False"; PostNord expects
                # the lowercase JSON form.
                "multiPDF": str(multi_pdf).lower()
                if multi_pdf is not None
                else None,
                "pageHorizontalAlign": page_horizontal_align,
                "pageVerticalAlign": page_vertical_align,
            }.items()
            if value is not None
        },
    )


def parse_customs_declaration_response(
    _response: lib.Deserializable[dict],
    settings: provider_utils.Settings,
) -> typing.Tuple[typing.Optional[dict], typing.List[models.Message]]:
    """Parse the digital declaration response into a result dict + Messages.

    The result carries the ``bookingResponseCN`` acceptance — the booking id
    plus one ``id_information`` entry per declared id with its ``OK|FAIL``
    status. Rejection bodies (including the no-prior-EDI refusal) surface as
    unified Messages and yield a ``None`` result.
    """
    response = _response.deserialize()
    messages = error.parse_error_response(response, settings)
    booking = _booking_response(response)

    if booking is None:
        return None, messages

    return _declaration_result(booking), messages


def parse_customs_declaration_pdf_response(
    _response: lib.Deserializable[dict],
    settings: provider_utils.Settings,
) -> typing.Tuple[typing.Optional[dict], typing.List[models.Message]]:
    """Parse the PDF-variant response into a result dict + Messages.

    Same acceptance result as the digital endpoint, plus the rendered
    ``labelPrintout`` entries mapped onto ``ShippingDocument`` (category
    from PostNord's ``printoutComposition``, PDF format per the endpoint).
    """
    response = _response.deserialize()
    messages = error.parse_error_response(response, settings)
    booking = _booking_response(response)

    if booking is None:
        return None, messages

    documents = provider_shipment._customs_documents(
        response.get("labelPrintout") or [], "PDF"
    )
    result = _declaration_result(booking)

    return (
        {**result, **({"documents": documents} if documents else {})},
        messages,
    )


def _booking_response(
    response: dict,
) -> typing.Optional[postnord_res.BookingResponseType]:
    return lib.to_object(
        postnord_res.CustomsDeclarationResponseType, response
    ).bookingResponse


def _declaration_result(booking: postnord_res.BookingResponseType) -> dict:
    """Normalize a ``bookingResponseCN`` into the connector result shape."""
    return lib.to_dict(
        {
            "booking_id": booking.bookingId,
            "id_information": [
                _id_information(info) for info in (booking.idInformation or [])
            ],
        }
    )


def _id_information(info: postnord_res.IDInformationType) -> dict:
    references = info.references
    shipment_references = (
        [_reference(ref) for ref in (references.shipment or [])]
        if references
        else []
    )
    item_references = (
        [_reference(ref) for ref in (references.item or [])] if references else []
    )

    return lib.to_dict(
        {
            "status": info.status,
            "ids": [
                {"id_type": _id.idType, "value": _id.value}
                for _id in (info.ids or [])
            ],
            "references": lib.identity(
                {"shipment": shipment_references, "item": item_references}
                if (shipment_references or item_references)
                else None
            ),
        }
    )


def _reference(reference: postnord_res.ItemType) -> dict:
    return {
        "reference_no": reference.referenceNo,
        "reference_type": reference.referenceType,
        "reference_desc": reference.referenceDesc,
    }
