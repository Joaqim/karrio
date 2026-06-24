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
class ErrorResponseType:
    message: typing.Optional[str] = None
    compositeFault: typing.Optional[CompositeFaultType] = jstruct.JStruct[CompositeFaultType]
