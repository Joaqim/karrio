"""PostNord carrier tests fixtures."""

import karrio.sdk as karrio


_settings = dict(
    id="123456789",
    test_mode=True,
    carrier_id="postnord",
    apikey="TEST_API_KEY",
    issuer_code="Z12",
    customer_number="00000000",
    application_id="2458",
    account_country_code="SE",
    # PostNord has no live rate API: per-merchant contract prices arrive via
    # Karrio's server-side RateSheet, modeled here as service-level zones.
    services=[
        dict(
            service_name="PostNord Parcel",
            service_code="postnord_parcel",
            carrier_service_code="18",
            currency="SEK",
            transit_days=2,
            domicile=True,
            international=False,
            zones=[dict(label="Sweden", rate=89.0, country_codes=["SE"])],
        ),
        dict(
            service_name="PostNord MyPack Home",
            service_code="postnord_mypack_home",
            carrier_service_code="17",
            currency="SEK",
            transit_days=2,
            domicile=True,
            international=False,
            zones=[dict(label="Sweden", rate=99.0, country_codes=["SE"])],
        ),
    ],
)

# Default gateway: transit-time enrichment OFF (no carrier call on rate()).
gateway = karrio.gateway["postnord"].create(dict(_settings))

# Opt-in gateway: transit-time enrichment ON via connection config.
gateway_with_transit = karrio.gateway["postnord"].create(
    dict(_settings, config=dict(enable_transit_times=True))
)

# Letter-service gating fixtures: an international parcel service plus the two
# gated letter products (34 tracked, UX export), all priced. Gating is driven by
# issuer_code + the offer_* toggles, independent of transit enrichment (off).
_letter_services = [
    dict(
        service_name="PostNord Postpaket Utrikes",
        service_code="postnord_postpaket_utrikes",
        carrier_service_code="91",
        currency="SEK",
        transit_days=5,
        domicile=False,
        international=True,
        zones=[dict(label="International", rate=250.0)],
    ),
    dict(
        service_name="PostNord Tracked Letter",
        service_code="postnord_tracked_letter",
        carrier_service_code="34",
        currency="SEK",
        transit_days=3,
        domicile=False,
        international=True,
        zones=[dict(label="International", rate=59.0)],
    ),
    dict(
        service_name="PostNord Export Letter",
        service_code="postnord_export_letter",
        carrier_service_code="UX",
        currency="SEK",
        transit_days=4,
        domicile=False,
        international=True,
        zones=[dict(label="International", rate=39.0)],
    ),
]

# Toggles off (Z12): only the ungated parcel service is offered.
gateway_letters_off = karrio.gateway["postnord"].create(
    dict(_settings, services=_letter_services)
)

# Toggles on (Z12): both letter products join the parcel service.
gateway_letters_on = karrio.gateway["postnord"].create(
    dict(
        _settings,
        services=_letter_services,
        config=dict(offer_tracked_letter=True, offer_export_letter=True),
    )
)

# Toggles on but Denmark issuer (Z11): tracked letter is offered, export letter
# is withheld because it is scoped to the Sweden (Z12) issuer.
gateway_letters_z11 = karrio.gateway["postnord"].create(
    dict(
        _settings,
        issuer_code="Z11",
        services=_letter_services,
        config=dict(offer_tracked_letter=True, offer_export_letter=True),
    )
)
