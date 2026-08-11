import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class ValidationErrorType:
    field: typing.Optional[str] = None
    errorCode: typing.Optional[int] = None
    message: typing.Optional[str] = None
    incompatibleFields: typing.Optional[typing.List[typing.Any]] = None


@attr.s(auto_attribs=True)
class ErrorResponseType:
    status: typing.Optional[str] = None
    validationErrors: typing.Optional[typing.List[ValidationErrorType]] = jstruct.JList[ValidationErrorType]
    title: typing.Optional[str] = None
    detail: typing.Optional[str] = None
