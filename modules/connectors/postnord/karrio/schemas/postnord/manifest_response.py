import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class ManifestResponseClassType:
    manifestId: typing.Optional[str] = None
    manifestUrl: typing.Optional[str] = None
    manifestData: typing.Optional[str] = None
    status: typing.Optional[str] = None
    shipmentCount: typing.Optional[int] = None
    creationDate: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class ManifestResponseType:
    manifestResponse: typing.Optional[ManifestResponseClassType] = jstruct.JStruct[ManifestResponseClassType]
