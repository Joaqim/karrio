import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class ErrorType:
    code: typing.Optional[str] = None
    message: typing.Optional[str] = None
    details: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class ErrorResponseClassType:
    errors: typing.Optional[typing.List[ErrorType]] = jstruct.JList[ErrorType]


@attr.s(auto_attribs=True)
class ErrorResponseType:
    errorResponse: typing.Optional[ErrorResponseClassType] = jstruct.JStruct[ErrorResponseClassType]
