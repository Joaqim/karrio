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
class TrackingResponseType:
    url: typing.Optional[str] = None
    faults: typing.Optional[typing.List[FaultType]] = jstruct.JList[FaultType]
