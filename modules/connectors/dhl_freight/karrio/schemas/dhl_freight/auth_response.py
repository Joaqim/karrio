import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class AuthResponseType:
    accesstoken: typing.Optional[str] = None
    idtoken: typing.Optional[str] = None
    tokentype: typing.Optional[str] = None
    expiresin: typing.Optional[int] = None
