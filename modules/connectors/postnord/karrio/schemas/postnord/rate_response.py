import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class RateType:
    basicServiceCode: typing.Optional[int] = None
    serviceName: typing.Optional[str] = None
    amount: typing.Optional[float] = None
    currency: typing.Optional[str] = None
    transitDays: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class RateResponseType:
    rates: typing.Optional[typing.List[RateType]] = jstruct.JList[RateType]
