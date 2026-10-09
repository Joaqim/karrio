import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class ApplicationType:
    name: typing.Optional[str] = None
    version: typing.Optional[str] = None
    applicationId: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class CategoryOfItemType:
    categoryType: typing.Optional[typing.List[str]] = None
    explanation: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class WeightType:
    value: typing.Optional[float] = None
    unit: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class TotalNumberOfPackagesType:
    value: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class PostalChargesType:
    amount: typing.Optional[float] = None
    currency: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class CustomsDeclarationCN22DetailedDescriptionType:
    content: typing.Optional[str] = None
    quantity: typing.Optional[TotalNumberOfPackagesType] = jstruct.JStruct[TotalNumberOfPackagesType]
    grossWeight: typing.Optional[WeightType] = jstruct.JStruct[WeightType]
    value: typing.Optional[PostalChargesType] = jstruct.JStruct[PostalChargesType]
    hsTariffNumber: typing.Optional[str] = None
    countryCode: typing.Optional[str] = None
    rowNo: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class ReferenceType:
    referenceNo: typing.Optional[str] = None
    referenceType: typing.Optional[str] = None
    referenceDesc: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class CustomsDeclarationCN22Type:
    declarationType: typing.Optional[str] = None
    references: typing.Optional[typing.List[ReferenceType]] = jstruct.JList[ReferenceType]
    EORIorPersonalIdNumber: typing.Optional[str] = None
    voec: typing.Optional[str] = None
    ioss: typing.Optional[str] = None
    hmrc: typing.Optional[str] = None
    countryOfOrigin: typing.Optional[str] = None
    hsTariffNumber: typing.Optional[typing.List[str]] = None
    categoryOfItem: typing.Optional[CategoryOfItemType] = jstruct.JStruct[CategoryOfItemType]
    detailedDescription: typing.Optional[typing.List[CustomsDeclarationCN22DetailedDescriptionType]] = jstruct.JList[CustomsDeclarationCN22DetailedDescriptionType]
    totalGrossWeight: typing.Optional[WeightType] = jstruct.JStruct[WeightType]
    totalValue: typing.Optional[PostalChargesType] = jstruct.JStruct[PostalChargesType]
    postalCharges: typing.Optional[PostalChargesType] = jstruct.JStruct[PostalChargesType]


@attr.s(auto_attribs=True)
class CommercialItemType:
    hsTariffNumber: typing.Optional[str] = None
    countryCode: typing.Optional[str] = None
    detailedDescRowNo: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class QuarantineCommentType:
    comments: typing.Optional[str] = None
    licenceNumber: typing.Optional[str] = None
    certificateNumber: typing.Optional[str] = None
    invoiceNumber: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class CustomsDeclarationCN23Type:
    declarationType: typing.Optional[str] = None
    references: typing.Optional[typing.List[ReferenceType]] = jstruct.JList[ReferenceType]
    EORIorPersonalIdNumber: typing.Optional[str] = None
    voec: typing.Optional[str] = None
    ioss: typing.Optional[str] = None
    hmrc: typing.Optional[str] = None
    categoryOfItem: typing.Optional[CategoryOfItemType] = jstruct.JStruct[CategoryOfItemType]
    detailedDescription: typing.Optional[typing.List[CustomsDeclarationCN22DetailedDescriptionType]] = jstruct.JList[CustomsDeclarationCN22DetailedDescriptionType]
    totalGrossWeight: typing.Optional[WeightType] = jstruct.JStruct[WeightType]
    totalValue: typing.Optional[PostalChargesType] = jstruct.JStruct[PostalChargesType]
    itemIds: typing.Optional[typing.List[str]] = None
    senderCustomsReferenceId: typing.Optional[str] = None
    importerReference: typing.Optional[str] = None
    importerContactInfo: typing.Optional[str] = None
    commercialItems: typing.Optional[typing.List[CommercialItemType]] = jstruct.JList[CommercialItemType]
    quarantineComments: typing.Optional[typing.List[QuarantineCommentType]] = jstruct.JList[QuarantineCommentType]
    officeOfOrigin: typing.Optional[str] = None
    dateOfPosting: typing.Optional[str] = None
    postalCharges: typing.Optional[PostalChargesType] = jstruct.JStruct[PostalChargesType]


@attr.s(auto_attribs=True)
class ContactsType:
    name: typing.Optional[str] = None
    phoneNo: typing.Optional[str] = None
    emailAddress: typing.Optional[str] = None
    smsNo: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class PartyIdentificationType:
    partyId: typing.Optional[str] = None
    partyIdType: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class BuyerType:
    partyIdentification: typing.Optional[PartyIdentificationType] = jstruct.JStruct[PartyIdentificationType]
    vatNo: typing.Optional[str] = None
    name: typing.Optional[str] = None
    streets: typing.Optional[typing.List[str]] = None
    city: typing.Optional[str] = None
    postalCode: typing.Optional[int] = None
    countryCode: typing.Optional[str] = None
    contacts: typing.Optional[ContactsType] = jstruct.JStruct[ContactsType]
    eoriNo: typing.Optional[str] = None
    place: typing.Optional[str] = None
    refItemIds: typing.Optional[typing.List[str]] = None


@attr.s(auto_attribs=True)
class AttributeListType:
    type: typing.Optional[str] = None
    value: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class CustomsInvoiceDetailedDescriptionType:
    quantity: typing.Optional[int] = None
    units: typing.Optional[str] = None
    returnHsTariffNumber: typing.Optional[str] = None
    hsTariffNumber: typing.Optional[str] = None
    hsTariffNumberCountryCode: typing.Optional[str] = None
    content: typing.Optional[str] = None
    marksAndNumbers: typing.Optional[str] = None
    countryOfOrigin: typing.Optional[str] = None
    netWeight: typing.Optional[WeightType] = jstruct.JStruct[WeightType]
    grossWeight: typing.Optional[WeightType] = jstruct.JStruct[WeightType]
    itemValue: typing.Optional[PostalChargesType] = jstruct.JStruct[PostalChargesType]
    refItemIds: typing.Optional[typing.List[str]] = None
    articleNumber: typing.Optional[str] = None
    orderNumber: typing.Optional[str] = None
    attributeList: typing.Optional[typing.List[AttributeListType]] = jstruct.JList[AttributeListType]
    reasonForExportation: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class FreightCostType:
    amount: typing.Optional[float] = None
    currency: typing.Optional[str] = None
    typeOfPayment: typing.Optional[str] = None
    paymentSystem: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class IDType:
    id: typing.Optional[str] = None
    idType: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class InvoiceType:
    invoiceNo: typing.Optional[str] = None
    shippingDate: typing.Optional[str] = None
    shippingId: typing.Optional[str] = None
    purchaseOrderNo: typing.Optional[str] = None
    reasonForExportation: typing.Optional[int] = None
    termsOfSale: typing.Optional[str] = None
    importerReference: typing.Optional[str] = None
    exportReference: typing.Optional[str] = None
    termsOfPayment: typing.Optional[str] = None
    customsDeclarationId: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class TransportType:
    mrn: typing.Optional[str] = None
    transportModeBorder: typing.Optional[int] = None
    transportIdentityBorder: typing.Optional[str] = None
    transportNationalityBorder: typing.Optional[str] = None
    transportName: typing.Optional[str] = None
    transportUniqueId: typing.Optional[str] = None
    truckId: typing.Optional[str] = None
    departurePlace: typing.Optional[str] = None
    additionalInformation: typing.Optional[str] = None
    departureCountryCode: typing.Optional[str] = None
    destinationCountryCode: typing.Optional[str] = None
    arrivalDate: typing.Optional[str] = None
    arrivalTime: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class CustomsInvoiceType:
    declarationType: typing.Optional[str] = None
    type: typing.Optional[str] = None
    basicServiceCode: typing.Optional[int] = None
    references: typing.Optional[typing.List[ReferenceType]] = jstruct.JList[ReferenceType]
    voec: typing.Optional[str] = None
    ioss: typing.Optional[str] = None
    hmrc: typing.Optional[str] = None
    splitShipmentId: typing.Optional[str] = None
    splitShipmentReference: typing.Optional[str] = None
    seller: typing.Optional[BuyerType] = jstruct.JStruct[BuyerType]
    buyer: typing.Optional[BuyerType] = jstruct.JStruct[BuyerType]
    shipTo: typing.Optional[BuyerType] = jstruct.JStruct[BuyerType]
    invoice: typing.Optional[InvoiceType] = jstruct.JStruct[InvoiceType]
    ids: typing.Optional[typing.List[IDType]] = jstruct.JList[IDType]
    detailedDescription: typing.Optional[typing.List[CustomsInvoiceDetailedDescriptionType]] = jstruct.JList[CustomsInvoiceDetailedDescriptionType]
    totalNetWeight: typing.Optional[WeightType] = jstruct.JStruct[WeightType]
    totalGrossWeight: typing.Optional[WeightType] = jstruct.JStruct[WeightType]
    totalNumberOfPackages: typing.Optional[TotalNumberOfPackagesType] = jstruct.JStruct[TotalNumberOfPackagesType]
    invoiceSubTotal: typing.Optional[PostalChargesType] = jstruct.JStruct[PostalChargesType]
    freightCost: typing.Optional[FreightCostType] = jstruct.JStruct[FreightCostType]
    invoiceTotal: typing.Optional[PostalChargesType] = jstruct.JStruct[PostalChargesType]
    transport: typing.Optional[TransportType] = jstruct.JStruct[TransportType]
    otherRemarks: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class CustomsDeclarationRequestType:
    messageDate: typing.Optional[str] = None
    messageFunction: typing.Optional[str] = None
    messageId: typing.Optional[str] = None
    application: typing.Optional[ApplicationType] = jstruct.JStruct[ApplicationType]
    language: typing.Optional[str] = None
    updateIndicator: typing.Optional[str] = None
    testIndicator: typing.Optional[bool] = None
    ids: typing.Optional[typing.List[IDType]] = jstruct.JList[IDType]
    customsDeclarationCN22: typing.Optional[CustomsDeclarationCN22Type] = jstruct.JStruct[CustomsDeclarationCN22Type]
    customsDeclarationCN23: typing.Optional[CustomsDeclarationCN23Type] = jstruct.JStruct[CustomsDeclarationCN23Type]
    customsInvoice: typing.Optional[CustomsInvoiceType] = jstruct.JStruct[CustomsInvoiceType]
