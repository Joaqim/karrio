import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class EventType:
    date: typing.Optional[str] = None
    time: typing.Optional[str] = None
    code: typing.Optional[str] = None
    description: typing.Optional[str] = None
    location: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class TrackingInfoType:
    trackingNumber: typing.Optional[str] = None
    status: typing.Optional[str] = None
    statusDetails: typing.Optional[str] = None
    estimatedDelivery: typing.Optional[str] = None
    events: typing.Optional[typing.List[EventType]] = jstruct.JList[EventType]


@attr.s(auto_attribs=True)
class TrackingResponseClassType:
    trackingInfo: typing.Optional[typing.List[TrackingInfoType]] = jstruct.JList[TrackingInfoType]


@attr.s(auto_attribs=True)
class TrackingResponseType:
    trackingResponse: typing.Optional[TrackingResponseClassType] = jstruct.JStruct[TrackingResponseClassType]
