"""Karrio DHL Freight rate API implementation.

The SE API Farm pricequote API is out of Phase 0 scope, so price resolution
is served from Karrio's static-rate mechanism: per-merchant contract prices
live in the server-side RateSheet and are resolved against the connection's
service levels by the universal rating mixin. No carrier call is made.
"""

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.dhl_freight_sweden.utils as provider_utils
from karrio.universal.providers.rating import (
    parse_rate_response as universal_parse_rate_response,
    rate_request,
)

__all__ = ["parse_rate_response", "rate_request"]


def parse_rate_response(
    _response: lib.Deserializable,
    settings: provider_utils.Settings,
) -> typing.Tuple[typing.List[models.RateDetails], typing.List[models.Message]]:
    return universal_parse_rate_response(_response, settings)
