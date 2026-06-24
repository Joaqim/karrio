"""Karrio PostNord rate API implementation.

PostNord publishes no live money-rate API, so rating is served from Karrio's
first-class static-rate mechanism: per-merchant contract prices live in the
server-side RateSheet and are resolved against the connection's service levels
by the universal rating mixin. The ``rate_request``/``parse_rate_response``
entrypoints below are thin re-exports of that universal implementation, keeping
the generated ``mapper.py`` (which calls
``karrio.providers.postnord.rate.rate_request`` and ``parse_rate_response``)
working unchanged.
"""

from karrio.universal.providers.rating import (
    parse_rate_response,
    rate_request,
)

__all__ = ["parse_rate_response", "rate_request"]
