import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class ShipmentType:
    trackingNumber: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class ManifestRequestClassType:
    accountNumber: typing.Optional[int] = None
    closeDate: typing.Optional[str] = None
    shipments: typing.Optional[typing.List[ShipmentType]] = jstruct.JList[ShipmentType]


@attr.s(auto_attribs=True)
class ManifestRequestType:
    manifestRequest: typing.Optional[ManifestRequestClassType] = jstruct.JStruct[ManifestRequestClassType]
