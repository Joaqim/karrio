import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class TrackingRequestType:
    country: typing.Optional[str] = None
    id: typing.Optional[str] = None
    language: typing.Optional[str] = None
