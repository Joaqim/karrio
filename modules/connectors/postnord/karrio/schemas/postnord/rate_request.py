import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class OptionsType:
    insurance: typing.Optional[bool] = None
    signaturerequired: typing.Optional[bool] = None


@attr.s(auto_attribs=True)
class PackageType:
    weight: typing.Optional[float] = None
    weightUnit: typing.Optional[str] = None
    length: typing.Optional[float] = None
    width: typing.Optional[float] = None
    height: typing.Optional[float] = None
    dimensionUnit: typing.Optional[str] = None
    packagingType: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class RecipientType:
    addressLine1: typing.Optional[str] = None
    city: typing.Optional[str] = None
    postalCode: typing.Optional[int] = None
    countryCode: typing.Optional[str] = None
    stateCode: typing.Optional[str] = None
    personName: typing.Optional[str] = None
    companyName: typing.Optional[str] = None
    phoneNumber: typing.Optional[str] = None
    email: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class RateRequestClassType:
    shipper: typing.Optional[RecipientType] = jstruct.JStruct[RecipientType]
    recipient: typing.Optional[RecipientType] = jstruct.JStruct[RecipientType]
    packages: typing.Optional[typing.List[PackageType]] = jstruct.JList[PackageType]
    services: typing.Optional[typing.List[str]] = None
    options: typing.Optional[OptionsType] = jstruct.JStruct[OptionsType]


@attr.s(auto_attribs=True)
class RateRequestType:
    rateRequest: typing.Optional[RateRequestClassType] = jstruct.JStruct[RateRequestClassType]
