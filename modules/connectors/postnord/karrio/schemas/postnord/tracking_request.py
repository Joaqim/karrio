import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class TrackingRequestClassType:
    trackingNumbers: typing.Optional[typing.List[str]] = None
    languageCode: typing.Optional[str] = None
    reference: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class TrackingRequestType:
    trackingRequest: typing.Optional[TrackingRequestClassType] = jstruct.JStruct[TrackingRequestClassType]
