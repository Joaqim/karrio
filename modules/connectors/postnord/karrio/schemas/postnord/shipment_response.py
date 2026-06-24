import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class AttributeType:
    param: typing.Optional[str] = None
    value: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class FaultType:
    explanationText: typing.Optional[str] = None
    faultCode: typing.Optional[str] = None
    paramValues: typing.Optional[typing.List[AttributeType]] = jstruct.JList[AttributeType]


@attr.s(auto_attribs=True)
class CompositeFaultType:
    faults: typing.Optional[typing.List[FaultType]] = jstruct.JList[FaultType]


@attr.s(auto_attribs=True)
class ResponseType:
    message: typing.Optional[str] = None
    compositeFault: typing.Optional[CompositeFaultType] = jstruct.JStruct[CompositeFaultType]


@attr.s(auto_attribs=True)
class IDType:
    idType: typing.Optional[str] = None
    value: typing.Optional[str] = None
    printId: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class ItemType:
    referenceNo: typing.Optional[str] = None
    referenceType: typing.Optional[str] = None
    referenceDesc: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class ReferencesType:
    shipment: typing.Optional[typing.List[ItemType]] = jstruct.JList[ItemType]
    item: typing.Optional[typing.List[ItemType]] = jstruct.JList[ItemType]


@attr.s(auto_attribs=True)
class URLType:
    type: typing.Optional[str] = None
    url: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class IDInformationType:
    status: typing.Optional[str] = None
    references: typing.Optional[ReferencesType] = jstruct.JStruct[ReferencesType]
    ids: typing.Optional[typing.List[IDType]] = jstruct.JList[IDType]
    urls: typing.Optional[typing.List[URLType]] = jstruct.JList[URLType]
    attributes: typing.Optional[typing.List[AttributeType]] = jstruct.JList[AttributeType]
    errorResponse: typing.Optional[ResponseType] = jstruct.JStruct[ResponseType]


@attr.s(auto_attribs=True)
class BookingResponseType:
    bookingId: typing.Optional[str] = None
    idInformation: typing.Optional[typing.List[IDInformationType]] = jstruct.JList[IDInformationType]
    handlingResponse: typing.Optional[ResponseType] = jstruct.JStruct[ResponseType]


@attr.s(auto_attribs=True)
class PrintoutType:
    id: typing.Optional[int] = None
    type: typing.Optional[str] = None
    labelFormat: typing.Optional[str] = None
    encoding: typing.Optional[str] = None
    uriResource: typing.Optional[str] = None
    data: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class LabelPrintoutType:
    itemIds: typing.Optional[typing.List[str]] = None
    printout: typing.Optional[PrintoutType] = jstruct.JStruct[PrintoutType]
    printoutComposition: typing.Optional[typing.Dict[str, int]] = None


@attr.s(auto_attribs=True)
class ShipmentResponseType:
    bookingResponse: typing.Optional[BookingResponseType] = jstruct.JStruct[BookingResponseType]
    labelPrintout: typing.Optional[typing.List[LabelPrintoutType]] = jstruct.JList[LabelPrintoutType]
