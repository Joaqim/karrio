"""Karrio PostNord client proxy."""

import karrio.lib as lib
import karrio.api.proxy as proxy
import karrio.mappers.postnord.settings as provider_settings
from karrio.universal.mappers.rating_proxy import RatingMixinProxy


class Proxy(proxy.Proxy):
    settings: provider_settings.Settings

    def get_rates(self, request: lib.Serializable) -> lib.Deserializable:
        """Resolve static prices through the universal rating mixin.

        PostNord has no live money-rate API, so PRICE resolution delegates to
        the universal rating mixin (server-side RateSheet).
        """
        return RatingMixinProxy.get_rates(self, request)
