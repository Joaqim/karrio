import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class DocumentsType:
    invoice: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class MetaType:
    serviceCode: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class ShipmentResponseClassType:
    trackingNumber: typing.Optional[str] = None
    shipmentIdentifier: typing.Optional[str] = None
    labelType: typing.Optional[str] = None
    label: typing.Optional[str] = None
    documents: typing.Optional[DocumentsType] = jstruct.JStruct[DocumentsType]
    meta: typing.Optional[MetaType] = jstruct.JStruct[MetaType]


@attr.s(auto_attribs=True)
class ShipmentResponseType:
    shipmentResponse: typing.Optional[ShipmentResponseClassType] = jstruct.JStruct[ShipmentResponseClassType]
