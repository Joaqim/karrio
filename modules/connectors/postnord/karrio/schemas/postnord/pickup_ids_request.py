import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class PickupIDSRequestElementType:
    itemId: typing.Optional[str] = None
    earliestPickupDate: typing.Optional[str] = None
    latestPickupDate: typing.Optional[str] = None
