import attr
import jstruct
import typing


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
class ResponseType:
    message: typing.Optional[str] = None
    compositeFault: typing.Optional[CompositeFaultType] = jstruct.JStruct[CompositeFaultType]


@attr.s(auto_attribs=True)
class IDType:
    idType: typing.Optional[str] = None
    value: typing.Optional[str] = None
    printId: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class URLType:
    type: typing.Optional[str] = None
    url: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class IDInformationType:
    status: typing.Optional[str] = None
    ids: typing.Optional[typing.List[IDType]] = jstruct.JList[IDType]
    urls: typing.Optional[typing.List[URLType]] = jstruct.JList[URLType]
    errorResponse: typing.Optional[ResponseType] = jstruct.JStruct[ResponseType]


@attr.s(auto_attribs=True)
class ManifestResponseType:
    bookingId: typing.Optional[str] = None
    idInformation: typing.Optional[typing.List[IDInformationType]] = jstruct.JList[IDInformationType]
    handlingResponse: typing.Optional[ResponseType] = jstruct.JStruct[ResponseType]
