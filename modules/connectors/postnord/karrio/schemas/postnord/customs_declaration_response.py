import attr
import jstruct
import typing


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
class ReferenceType:
    shipment: typing.Optional[typing.List[ItemType]] = jstruct.JList[ItemType]
    item: typing.Optional[typing.List[ItemType]] = jstruct.JList[ItemType]


@attr.s(auto_attribs=True)
class IDInformationType:
    status: typing.Optional[str] = None
    references: typing.Optional[ReferenceType] = jstruct.JStruct[ReferenceType]
    ids: typing.Optional[typing.List[IDType]] = jstruct.JList[IDType]


@attr.s(auto_attribs=True)
class BookingResponseType:
    bookingId: typing.Optional[str] = None
    idInformation: typing.Optional[typing.List[IDInformationType]] = jstruct.JList[IDInformationType]


@attr.s(auto_attribs=True)
class ParamValueType:
    param: typing.Optional[str] = None
    value: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class FaultType:
    explanationText: typing.Optional[str] = None
    faultCode: typing.Optional[str] = None
    paramValues: typing.Optional[typing.List[ParamValueType]] = jstruct.JList[ParamValueType]


@attr.s(auto_attribs=True)
class CompositeFaultType:
    faults: typing.Optional[typing.List[FaultType]] = jstruct.JList[FaultType]


@attr.s(auto_attribs=True)
class ErrorResponseType:
    message: typing.Optional[str] = None
    compositeFault: typing.Optional[CompositeFaultType] = jstruct.JStruct[CompositeFaultType]


@attr.s(auto_attribs=True)
class ItemIDType:
    itemIds: typing.Optional[str] = None
    printId: typing.Optional[str] = None
    basicServiceCode: typing.Optional[str] = None
    reference: typing.Optional[ReferenceType] = jstruct.JStruct[ReferenceType]
    status: typing.Optional[str] = None
    errorResponse: typing.Optional[ErrorResponseType] = jstruct.JStruct[ErrorResponseType]


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
    itemIds: typing.Optional[typing.List[ItemIDType]] = jstruct.JList[ItemIDType]
    printout: typing.Optional[PrintoutType] = jstruct.JStruct[PrintoutType]
    printoutComposition: typing.Optional[typing.Dict[str, int]] = None


@attr.s(auto_attribs=True)
class CustomsDeclarationResponseType:
    bookingResponse: typing.Optional[BookingResponseType] = jstruct.JStruct[BookingResponseType]
    labelPrintout: typing.Optional[typing.List[LabelPrintoutType]] = jstruct.JList[LabelPrintoutType]
