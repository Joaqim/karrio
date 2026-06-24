import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class RateType:
    serviceCode: typing.Optional[str] = None
    serviceName: typing.Optional[str] = None
    totalCharge: typing.Optional[float] = None
    currency: typing.Optional[str] = None
    transitDays: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class RateResponseClassType:
    rates: typing.Optional[typing.List[RateType]] = jstruct.JList[RateType]


@attr.s(auto_attribs=True)
class RateResponseType:
    rateResponse: typing.Optional[RateResponseClassType] = jstruct.JStruct[RateResponseClassType]
