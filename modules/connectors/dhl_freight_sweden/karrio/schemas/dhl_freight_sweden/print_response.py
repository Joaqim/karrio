import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class ReportType:
    name: typing.Optional[str] = None
    content: typing.Optional[str] = None
    contentType: typing.Optional[str] = None
    type: typing.Optional[str] = None
    valid: typing.Optional[bool] = None


@attr.s(auto_attribs=True)
class PrintResponseType:
    reports: typing.Optional[typing.List[ReportType]] = jstruct.JList[ReportType]
