#User Guide
## Get Access

For getting access to DHL Freight APIs, please login the portal as developer and request access for the Freight APIs by clicking at the top right corner of the screen as "Get Access". Then fill out the DHL Freight Customer Onboarding Form and select which Freight APIs you need. After initial evaluation and business approval you will be informed via your developer email and you can find your SANDBOX APP with requested APIs under your user profile under  My Apps.

## Authentication

To access DHL Freight APIs, first authenticate to gain access, then obtain a 30-minute OAuth 2.0 Bearer Token. This token is required for every call and can be passed via the request header or a query string parameter.

To view your API subscription keys:

1. From the My Apps screen, click on the name of your app.
    The Details screen appears.
2. If you have access to more than one Freight API, click the name of the relevant Freight API.
    *Note:* The APIs are listed under the “Credentials” section.
3. Click the Show link below the asterisks that is hiding the Consumer Key.
    The Consumer Key appears.

With your obtained API Key and API Secret, set username with your API Key and set Password with your API Secret to obtain a Bearer Token via DHL Freight APIs.
You do not need to request access directly to the DHL Group Authentication API, as Bearer Token mechanism is included in all DHL Freight APIs.
Above link to the DHL Group Authentication API is only for documentation and developer instructions.

## Environments

The addressable API base URL/URI environments are:

|Environment|Description|
|-|-|
|https://api-sandbox.dhl.com/freight/shipping/orders/v1|Sandbox environment|
|https://api.dhl.com/freight/shipping/orders/v1|Production environment|
