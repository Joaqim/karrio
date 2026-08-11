import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class PageOptionsType:
    pageType: typing.Optional[str] = None
    marginLeft: typing.Optional[int] = None
    marginTop: typing.Optional[int] = None
    padding: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class OptionsType:
    label: typing.Optional[bool] = None
    waybill: typing.Optional[bool] = None
    returnLabel: typing.Optional[bool] = None
    pageOptions: typing.Optional[PageOptionsType] = jstruct.JStruct[PageOptionsType]


@attr.s(auto_attribs=True)
class PrintRequestType:
    shipmentIds: typing.Optional[typing.List[str]] = None
    options: typing.Optional[OptionsType] = jstruct.JStruct[OptionsType]
