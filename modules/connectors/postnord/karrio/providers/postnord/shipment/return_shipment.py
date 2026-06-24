"""Karrio PostNord return shipment API implementation.

PostNord has no dedicated returns endpoint; a return is a normal Booking EDI
shipment with a return service code (e.g. ``20`` Return Pickup, ``24`` Return
Drop Off) and the shipper/recipient already swapped by the SDK fluent
interface. The request/response therefore reuse the create flow unchanged.
"""

import karrio.providers.postnord.shipment.create as create

# Returns reuse the Booking EDI create flow (addresses pre-swapped by the SDK).
return_shipment_request = create.shipment_request
parse_return_shipment_response = create.parse_shipment_response
