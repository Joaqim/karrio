import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class ApplicationType:
    name: typing.Optional[str] = None
    version: typing.Optional[str] = None
    applicationId: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class GoodsValueType:
    amount: typing.Optional[float] = None
    currency: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class CashOnDeliveryType:
    transactionIdentifier: typing.Optional[str] = None
    codType: typing.Optional[str] = None
    codAmount: typing.Optional[GoodsValueType] = jstruct.JStruct[GoodsValueType]


@attr.s(auto_attribs=True)
class CategoryOfItemType:
    categoryType: typing.Optional[typing.List[str]] = None
    explanation: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class TotalGrossWeightType:
    value: typing.Optional[float] = None
    unit: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class NumberOfPackagesType:
    value: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class CustomsDeclarationCN22DetailedDescriptionType:
    content: typing.Optional[str] = None
    quantity: typing.Optional[NumberOfPackagesType] = jstruct.JStruct[NumberOfPackagesType]
    grossWeight: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]
    value: typing.Optional[GoodsValueType] = jstruct.JStruct[GoodsValueType]
    hsTariffNumber: typing.Optional[str] = None
    countryCode: typing.Optional[str] = None
    rowNo: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class CustomsDeclarationCN22ReferenceType:
    referenceNo: typing.Optional[str] = None
    referenceType: typing.Optional[str] = None
    referenceDesc: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class CustomsDeclarationCN22Type:
    declarationType: typing.Optional[str] = None
    references: typing.Optional[typing.List[CustomsDeclarationCN22ReferenceType]] = jstruct.JList[CustomsDeclarationCN22ReferenceType]
    EORIorPersonalIdNumber: typing.Optional[str] = None
    voec: typing.Optional[str] = None
    ioss: typing.Optional[str] = None
    hmrc: typing.Optional[str] = None
    countryOfOrigin: typing.Optional[str] = None
    hsTariffNumber: typing.Optional[typing.List[str]] = None
    categoryOfItem: typing.Optional[CategoryOfItemType] = jstruct.JStruct[CategoryOfItemType]
    detailedDescription: typing.Optional[typing.List[CustomsDeclarationCN22DetailedDescriptionType]] = jstruct.JList[CustomsDeclarationCN22DetailedDescriptionType]
    totalGrossWeight: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]
    totalValue: typing.Optional[GoodsValueType] = jstruct.JStruct[GoodsValueType]
    postalCharges: typing.Optional[GoodsValueType] = jstruct.JStruct[GoodsValueType]


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
    references: typing.Optional[typing.List[CustomsDeclarationCN22ReferenceType]] = jstruct.JList[CustomsDeclarationCN22ReferenceType]
    EORIorPersonalIdNumber: typing.Optional[str] = None
    voec: typing.Optional[str] = None
    ioss: typing.Optional[str] = None
    hmrc: typing.Optional[str] = None
    categoryOfItem: typing.Optional[CategoryOfItemType] = jstruct.JStruct[CategoryOfItemType]
    detailedDescription: typing.Optional[typing.List[CustomsDeclarationCN22DetailedDescriptionType]] = jstruct.JList[CustomsDeclarationCN22DetailedDescriptionType]
    totalGrossWeight: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]
    totalValue: typing.Optional[GoodsValueType] = jstruct.JStruct[GoodsValueType]
    itemIds: typing.Optional[typing.List[str]] = None
    senderCustomsReferenceId: typing.Optional[str] = None
    importerReference: typing.Optional[str] = None
    importerContactInfo: typing.Optional[str] = None
    commercialItems: typing.Optional[typing.List[CommercialItemType]] = jstruct.JList[CommercialItemType]
    quarantineComments: typing.Optional[typing.List[QuarantineCommentType]] = jstruct.JList[QuarantineCommentType]
    officeOfOrigin: typing.Optional[str] = None
    dateOfPosting: typing.Optional[str] = None
    postalCharges: typing.Optional[GoodsValueType] = jstruct.JStruct[GoodsValueType]


@attr.s(auto_attribs=True)
class ContactType:
    name: typing.Optional[str] = None
    phoneNo: typing.Optional[str] = None
    emailAddress: typing.Optional[str] = None
    smsNo: typing.Optional[str] = None
    contactName: typing.Optional[str] = None


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
    contacts: typing.Optional[ContactType] = jstruct.JStruct[ContactType]
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
    netWeight: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]
    grossWeight: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]
    itemValue: typing.Optional[GoodsValueType] = jstruct.JStruct[GoodsValueType]
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
    references: typing.Optional[typing.List[CustomsDeclarationCN22ReferenceType]] = jstruct.JList[CustomsDeclarationCN22ReferenceType]
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
    totalNetWeight: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]
    totalGrossWeight: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]
    totalNumberOfPackages: typing.Optional[NumberOfPackagesType] = jstruct.JStruct[NumberOfPackagesType]
    invoiceSubTotal: typing.Optional[GoodsValueType] = jstruct.JStruct[GoodsValueType]
    freightCost: typing.Optional[FreightCostType] = jstruct.JStruct[FreightCostType]
    invoiceTotal: typing.Optional[GoodsValueType] = jstruct.JStruct[GoodsValueType]
    transport: typing.Optional[TransportType] = jstruct.JStruct[TransportType]
    otherRemarks: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class DateAndTimesType:
    loadingDate: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class FreeTextType:
    usageCode: typing.Optional[str] = None
    text: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class DimensionsType:
    height: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]
    width: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]
    length: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]


@attr.s(auto_attribs=True)
class ItemIdentificationType:
    itemId: typing.Optional[str] = None
    itemIdType: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class ItemReferenceType:
    referenceNo: typing.Optional[str] = None
    referenceType: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class ItemType:
    itemIdentification: typing.Optional[ItemIdentificationType] = jstruct.JStruct[ItemIdentificationType]
    references: typing.Optional[typing.List[ItemReferenceType]] = jstruct.JList[ItemReferenceType]
    dimensions: typing.Optional[DimensionsType] = jstruct.JStruct[DimensionsType]
    grossWeight: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]
    volume: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]
    itemValue: typing.Optional[GoodsValueType] = jstruct.JStruct[GoodsValueType]


@attr.s(auto_attribs=True)
class GoodsItemType:
    marking: typing.Optional[str] = None
    goodsDescription: typing.Optional[str] = None
    packageTypeCode: typing.Optional[str] = None
    numberOfPackageTypeCodeItems: typing.Optional[NumberOfPackagesType] = jstruct.JStruct[NumberOfPackagesType]
    references: typing.Optional[typing.List[ItemReferenceType]] = jstruct.JList[ItemReferenceType]
    items: typing.Optional[typing.List[ItemType]] = jstruct.JList[ItemType]


@attr.s(auto_attribs=True)
class InsuranceType:
    typeOfInsurance: typing.Optional[str] = None
    insuranceAmount: typing.Optional[GoodsValueType] = jstruct.JStruct[GoodsValueType]


@attr.s(auto_attribs=True)
class AddressType:
    streets: typing.Optional[typing.List[str]] = None
    postalCode: typing.Optional[int] = None
    placeName: typing.Optional[str] = None
    state: typing.Optional[str] = None
    city: typing.Optional[str] = None
    countryCode: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class NameIdentificationType:
    name: typing.Optional[str] = None
    companyName: typing.Optional[str] = None
    careOfName: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class PartyType:
    nameIdentification: typing.Optional[NameIdentificationType] = jstruct.JStruct[NameIdentificationType]
    address: typing.Optional[AddressType] = jstruct.JStruct[AddressType]
    contact: typing.Optional[ContactType] = jstruct.JStruct[ContactType]


@attr.s(auto_attribs=True)
class ConsignType:
    issuerCode: typing.Optional[str] = None
    partyIdentification: typing.Optional[PartyIdentificationType] = jstruct.JStruct[PartyIdentificationType]
    party: typing.Optional[PartyType] = jstruct.JStruct[PartyType]


@attr.s(auto_attribs=True)
class PartiesType:
    consignor: typing.Optional[ConsignType] = jstruct.JStruct[ConsignType]
    consignee: typing.Optional[ConsignType] = jstruct.JStruct[ConsignType]


@attr.s(auto_attribs=True)
class ServiceType:
    basicServiceCode: typing.Optional[int] = None
    additionalServiceCode: typing.Optional[typing.List[str]] = None


@attr.s(auto_attribs=True)
class ShipmentIdentificationType:
    shipmentId: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class ShipmentType:
    shipmentIdentification: typing.Optional[ShipmentIdentificationType] = jstruct.JStruct[ShipmentIdentificationType]
    dateAndTimes: typing.Optional[DateAndTimesType] = jstruct.JStruct[DateAndTimesType]
    service: typing.Optional[ServiceType] = jstruct.JStruct[ServiceType]
    cashOnDelivery: typing.Optional[CashOnDeliveryType] = jstruct.JStruct[CashOnDeliveryType]
    insurance: typing.Optional[InsuranceType] = jstruct.JStruct[InsuranceType]
    goodsValue: typing.Optional[GoodsValueType] = jstruct.JStruct[GoodsValueType]
    freeText: typing.Optional[typing.List[FreeTextType]] = jstruct.JList[FreeTextType]
    numberOfPackages: typing.Optional[NumberOfPackagesType] = jstruct.JStruct[NumberOfPackagesType]
    totalGrossWeight: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]
    references: typing.Optional[typing.List[CustomsDeclarationCN22ReferenceType]] = jstruct.JList[CustomsDeclarationCN22ReferenceType]
    parties: typing.Optional[PartiesType] = jstruct.JStruct[PartiesType]
    goodsItem: typing.Optional[typing.List[GoodsItemType]] = jstruct.JList[GoodsItemType]
    customsDeclarationCN22: typing.Optional[CustomsDeclarationCN22Type] = jstruct.JStruct[CustomsDeclarationCN22Type]
    customsDeclarationCN23: typing.Optional[CustomsDeclarationCN23Type] = jstruct.JStruct[CustomsDeclarationCN23Type]
    customsInvoice: typing.Optional[CustomsInvoiceType] = jstruct.JStruct[CustomsInvoiceType]


@attr.s(auto_attribs=True)
class ShipmentRequestType:
    messageDate: typing.Optional[str] = None
    language: typing.Optional[str] = None
    updateIndicator: typing.Optional[str] = None
    testIndicator: typing.Optional[bool] = None
    application: typing.Optional[ApplicationType] = jstruct.JStruct[ApplicationType]
    shipment: typing.Optional[typing.List[ShipmentType]] = jstruct.JList[ShipmentType]
