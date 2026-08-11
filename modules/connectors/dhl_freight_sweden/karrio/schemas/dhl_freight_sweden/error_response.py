import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class ValidationErrorType:
    field: typing.Optional[str] = None
    errorCode: typing.Optional[int] = None
    message: typing.Optional[str] = None
    incompatibleFields: typing.Optional[typing.List[str]] = None


@attr.s(auto_attribs=True)
class ErrorResponseType:
    status: typing.Optional[str] = None
    errorMessage: typing.Optional[str] = None
    validationErrors: typing.Optional[typing.List[ValidationErrorType]] = jstruct.JList[ValidationErrorType]
