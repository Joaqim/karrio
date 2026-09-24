"""Karrio PostNord rate API implementation.

PostNord publishes no live money-rate API, so PRICE resolution is served from
Karrio's first-class static-rate mechanism: per-merchant contract prices live in
the server-side RateSheet and are resolved against the connection's service
levels by the universal rating mixin.
"""

from karrio.universal.providers.rating import (
    parse_rate_response,
    rate_request,
)

__all__ = ["parse_rate_response", "rate_request"]
