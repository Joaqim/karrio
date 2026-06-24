"""Karrio PostNord rate API implementation.

PostNord exposes no public money-rate API, so rating is static and
config-driven (D1): ``rate_request`` echoes the requested service codes and
``parse_rate_response`` synthesizes a ``RateDetails`` per service present in
the merchant-configured rate table read from ``ConnectionConfig.rate_table``.
"""

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.postnord.error as error
import karrio.providers.postnord.utils as provider_utils
import karrio.providers.postnord.units as provider_units


def parse_rate_response(
    _response: lib.Deserializable[dict],
    settings: provider_utils.Settings,
) -> typing.Tuple[typing.List[models.RateDetails], typing.List[models.Message]]:
    response = _response.deserialize()
    messages = error.parse_error_response(response, settings)

    rate_table = settings.connection_config.rate_table.state or {}
    requested = response.get("services") or []

    # Synthesize one RateDetails per service in the table, optionally narrowed
    # to the services the caller asked for (when the payload named any).
    service_codes = [
        code
        for code in rate_table.keys()
        if not requested or str(code) in [str(_) for _ in requested]
    ]

    rates = [
        _extract_details((str(code), rate_table[code]), settings)
        for code in service_codes
    ]

    return rates, messages


def _extract_details(
    data: typing.Tuple[str, dict],
    settings: provider_utils.Settings,
) -> models.RateDetails:
    service_code, entry = data
    service = provider_units.ShippingService.map(service_code)
    currency = entry.get("currency") or "SEK"

    return models.RateDetails(
        carrier_id=settings.carrier_id,
        carrier_name=settings.carrier_name,
        service=service.name_or_key,
        total_charge=lib.to_money(entry.get("amount")),
        currency=currency,
        meta=dict(
            service_name=service.name or service_code,
            rate_provider="postnord",
        ),
    )


def rate_request(
    payload: models.RateRequest,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    services = lib.to_services(payload.services, provider_units.ShippingService)

    # No carrier call: the request only carries the requested service codes so
    # the (static) rate provider can filter the configured rate table.
    request = dict(
        services=[
            getattr(service, "value", None) or service
            for service in services
        ],
    )

    return lib.Serializable(request, lib.to_dict)
