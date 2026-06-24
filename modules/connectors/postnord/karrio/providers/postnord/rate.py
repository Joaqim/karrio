"""Karrio PostNord rate API implementation.

PostNord publishes no live money-rate API, so PRICE resolution is served from
Karrio's first-class static-rate mechanism: per-merchant contract prices live in
the server-side RateSheet and are resolved against the connection's service
levels by the universal rating mixin.

On top of that price resolution, ``rate()`` always calls PostNord's Transit
Time API (``GET /rest/transport/v2/transittime/addresstoaddress``) to enrich
each rate with an accurate ``transit_days`` and estimated delivery date, and to
drop services that PostNord reports as not bookable for the requested
origin/destination. This is a deliberate relaxation of the connector's
"rating performs no carrier call" property (decision D9): the transit lookup is
issued from the proxy and its parsed results are threaded to this parser via the
``Deserializable.ctx`` channel.

If the transit call is unavailable (network error, non-200, or unparseable
body), price rating still succeeds: the proxy attaches an empty transit context
plus a degrade marker, this parser leaves the static ``transit_days`` untouched,
applies no serviceability filtering, and surfaces a single warning ``Message``.
"""

import attr
import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.postnord.utils as provider_utils
from karrio.universal.providers.rating import (
    parse_rate_response as universal_parse_rate_response,
    rate_request,
)

__all__ = ["parse_rate_response", "rate_request"]


def parse_rate_response(
    _response: lib.Deserializable,
    settings: provider_utils.Settings,
) -> typing.Tuple[typing.List[models.RateDetails], typing.List[models.Message]]:
    """Resolve static prices, then merge PostNord transit-time enrichment.

    The universal parser produces base ``RateDetails`` (prices) from the static
    rate sheet. Transit results parsed by the proxy arrive on ``_response.ctx``
    keyed by ``carrier_service_code`` (PostNord ``basicServiceCode``). For each
    rate we override ``transit_days`` from the matching transit result, record
    the estimated delivery date in ``meta["estimated_delivery"]``, and drop any
    rate whose matching transit result is ``isBookable == false``. When the
    transit lookup degraded, no filtering or overriding occurs and a warning is
    surfaced.
    """
    rates, messages = universal_parse_rate_response(_response, settings)

    ctx = _response.ctx or {}
    transit_by_code: dict = ctx.get("transit_results") or {}
    degraded: bool = bool(ctx.get("transit_degraded"))

    if degraded:
        messages = [
            *messages,
            models.Message(
                carrier_id=settings.carrier_id,
                carrier_name=settings.carrier_name,
                code="transit_time_unavailable",
                message=(
                    "PostNord transit-time enrichment was unavailable; rates use "
                    "static transit days and no serviceability filtering."
                ),
            ),
        ]
        return rates, messages

    enriched: typing.List[models.RateDetails] = []
    for rate in rates:
        code = (rate.meta or {}).get("carrier_service_code")
        transit = transit_by_code.get(code) if code is not None else None

        if transit is None:
            enriched.append(rate)
            continue

        if transit.get("is_bookable") is False:
            continue

        transit_days = transit.get("transit_days")
        estimated_delivery = transit.get("estimated_delivery")

        meta = {**(rate.meta or {})}
        if estimated_delivery is not None:
            meta["estimated_delivery"] = estimated_delivery

        enriched.append(
            attr.evolve(
                rate,
                transit_days=(
                    transit_days if transit_days is not None else rate.transit_days
                ),
                meta=meta,
            )
        )

    return enriched, messages
