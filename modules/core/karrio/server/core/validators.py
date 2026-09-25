import re
import typing
import functools
import unicodedata
import phonenumbers
from datetime import datetime
from karrio.server.core.logging import logger

import karrio.lib as lib
import karrio.core.units as units
import karrio.server.serializers as serializers

DIMENSIONS = ["width", "height", "length"]


def dimensions_required_together(value):
    any_dimension_specified = any(value.get(dim) is not None for dim in DIMENSIONS)
    has_any_dimension_undefined = any(value.get(dim) is None for dim in DIMENSIONS)
    dimension_unit_is_undefined = value.get("dimension_unit") is None

    if any_dimension_specified and has_any_dimension_undefined:
        raise serializers.ValidationError(
            {
                "dimensions": "When one dimension is specified, all must be specified with a dimension_unit"
            }
        )

    if (
        any_dimension_specified
        and not has_any_dimension_undefined
        and dimension_unit_is_undefined
    ):
        raise serializers.ValidationError(
            {
                "dimension_unit": "dimension_unit is required when dimensions are specified"
            }
        )


class TimeFormatValidator:
    """Validator for HH:MM time format that can be pickled."""

    def __init__(self, prop: str):
        self.prop = prop

    def __call__(self, value):
        try:
            datetime.strptime(value, "%H:%M")
        except Exception:
            raise serializers.ValidationError(
                "The time format must match HH:HM",
                code="invalid",
            )


class DateFormatValidator:
    """Validator for YYYY-MM-DD date format that can be pickled."""

    def __init__(self, prop: str):
        self.prop = prop

    def __call__(self, value):
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except Exception:
            raise serializers.ValidationError(
                "The date format must match YYYY-MM-DD",
                code="invalid",
            )


class DateTimeFormatValidator:
    """Validator for YYYY-MM-DD HH:MM datetime format that can be pickled."""

    def __init__(self, prop: str):
        self.prop = prop

    def __call__(self, value):
        try:
            datetime.strptime(value, "%Y-%m-%d %H:%M")
        except Exception:
            raise serializers.ValidationError(
                "The datetime format must match YYYY-MM-DD HH:HM",
                code="invalid",
            )


def valid_time_format(prop: str):
    """Factory function for time format validator."""
    return TimeFormatValidator(prop)


def valid_date_format(prop: str):
    """Factory function for date format validator."""
    return DateFormatValidator(prop)


def valid_datetime_format(prop: str):
    """Factory function for datetime format validator."""
    return DateTimeFormatValidator(prop)


class Base64Validator:
    """Validator for base64 encoded content that can be pickled."""

    def __init__(self, prop: str, max_size: int = 5242880):
        self.prop = prop
        self.max_size = max_size

    def __call__(self, value: str):
        error = None

        try:
            buffer = lib.to_buffer(value, validate=True)

            if buffer.getbuffer().nbytes > self.max_size:
                error = f"Error: file size exceeds {self.max_size} bytes."

        except Exception as e:
            logger.error("Invalid base64 file content", error=str(e))
            error = "Invalid base64 file content"
            raise serializers.ValidationError(
                error,
                code="invalid",
            )

        if error is not None:
            raise serializers.ValidationError(error, code="invalid")


def valid_base64(prop: str, max_size: int = 5242880):
    """Factory function for base64 validator."""
    return Base64Validator(prop, max_size)


class OptionDefaultSerializer(serializers.Serializer):
    def __init__(self, instance=None, **kwargs):
        data = kwargs.get("data", {})
        if data:
            # Get existing options from data and instance
            options = {
                **(
                    getattr(instance, "options", None) or {}
                ),  # Start with instance options
                **(data.get("options") or {}),  # Override with new options
            }

            # Get shipping_date from options or default to next business day
            shipping_date = options.get("shipping_date")
            shipment_date = options.get("shipment_date")

            if not shipping_date:
                shipping_date = lib.fdatetime(
                    lib.to_next_business_datetime(
                        lib.to_date(shipment_date) or datetime.now()
                    ),
                    output_format="%Y-%m-%dT%H:%M",
                )

            if not shipment_date:
                shipment_date = lib.fdate(
                    shipping_date, current_format="%Y-%m-%dT%H:%M"
                )

            # Update only the date fields in options
            options.update(
                {"shipping_date": shipping_date, "shipment_date": shipment_date}
            )

            # Update the data with merged options
            kwargs["data"]["options"] = options

        super().__init__(instance, **kwargs)


class PresetSerializer(serializers.Serializer):
    def validate(self, data):
        import karrio.server.core.dataunits as dataunits

        dimensions_required_together(data)

        if data is not None and "package_preset" in data:
            package_presets = dataunits.REFERENCE_MODELS.get("package_presets", {})
            preset_name = data["package_preset"]

            # Find the preset across all carriers
            preset = lib.identity(
                next(
                    (
                        presets[preset_name]
                        for carrier_id, presets in package_presets.items()
                        if preset_name in presets
                    ),
                    None,
                )
                or {}
            )

            data.update(
                {
                    **data,
                    "width": data.get("width") or preset.get("width"),
                    "length": data.get("length") or preset.get("length"),
                    "height": data.get("height") or preset.get("height"),
                    "dimension_unit": data.get("dimension_unit")
                    or preset.get("dimension_unit"),
                }
            )

        return data


def shipment_documents_accessor(cls=None, *, include_base64: bool = False):
    """
    Class decorator that computes shipping_documents for Shipment serializers.

    When applied to a serializer class, this decorator overrides to_representation()
    to dynamically build the shipping_documents list based on the shipment's
    label and invoice fields.

    Args:
        include_base64: If True, includes base64 content in shipping_documents.
                       If False (default), only includes URLs.

    Usage:
        @shipment_documents_accessor
        class Shipment(Serializer):
            ...  # shipping_documents will have URLs only

        @shipment_documents_accessor(include_base64=True)
        class PurchasedShipment(Shipment):
            ...  # shipping_documents will include base64 content
    """

    def decorator(klass):
        # Store the flag on the class for reference
        klass._include_base64_documents = include_base64

        # Store original to_representation
        original_to_representation = klass.to_representation

        def to_representation(self, instance):
            # Get the original serialized data
            data = original_to_representation(self, instance)

            # Build shipping_documents dynamically
            documents = []

            # Add label document if exists
            label = getattr(instance, "label", None)
            if label:
                label_format = getattr(instance, "label_type", None) or "PDF"
                documents.append(
                    {
                        "category": "label",
                        "format": label_format,
                        "url": getattr(instance, "label_url", None),
                        "base64": label if include_base64 else None,
                    }
                )

            # Add invoice document if exists
            invoice = getattr(instance, "invoice", None)
            if invoice:
                documents.append(
                    {
                        "category": "invoice",
                        "format": "PDF",
                        "url": getattr(instance, "invoice_url", None),
                        "base64": invoice if include_base64 else None,
                    }
                )

            # Add extra documents (return labels, COD documents, etc.)
            extra_documents = getattr(instance, "extra_documents", None) or []
            for doc in extra_documents:
                doc_data = doc if isinstance(doc, dict) else lib.to_dict(doc)
                documents.append(
                    {
                        "category": doc_data.get("category", "other"),
                        "format": doc_data.get("format", "PDF"),
                        "url": doc_data.get("url"),
                        "base64": doc_data.get("base64") if include_base64 else None,
                    }
                )

            # Update the data with computed shipping_documents
            data["shipping_documents"] = documents

            return data

        klass.to_representation = to_representation
        return klass

    # Handle both @shipment_documents_accessor and @shipment_documents_accessor(...)
    if cls is not None:
        # Called as @shipment_documents_accessor without parentheses
        return decorator(cls)
    else:
        # Called as @shipment_documents_accessor(...) with arguments
        return decorator


# ø and æ are single base letters (not NFD-decomposable), so they are folded
# through an explicit translation to match ASCII-typed Nordic names; å folds
# through NFD like other accented characters.
_NORDIC_FOLD_TRANSLATION = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE"})


def _fold_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.translate(_NORDIC_FOLD_TRANSLATION))
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return stripped.casefold().strip()


STATE_NAME_SUFFIXES = tuple(
    _fold_text(suffix)
    for suffix in [
        " län",
        " fylke",
        " maakunta",
        " lääni",
        " region",
        " county",
        " province",
        " state",
    ]
)


def _state_match_keys(value: str) -> list[str]:
    folded = _fold_text(value)
    keys = [folded]
    keys += [
        folded[: -len(suffix)].strip()
        for suffix in STATE_NAME_SUFFIXES
        if folded.endswith(suffix)
    ]

    if folded.startswith("region "):
        keys.append(folded[len("region ") :])

    keys += [key[:-1] for key in keys if key.endswith("s")]
    keys += [key.replace("ae", "e") for key in keys if "ae" in key]

    return list(dict.fromkeys(key for key in keys if key))


# Legacy subdivision aliases consulted when both the code and the name lookups
# miss. "PQ" is the legacy Canada Post province code for Quebec. Names of
# dissolved Norwegian counties have no alias and pass through unchanged.
STATE_INPUT_ALIASES = {
    "CA": {"PQ": "QC"},
}


# Subdivisions used only to normalize address input.
# They are kept out of units.CountryState because /references exports that enum,
# and the dashboard address form requires a state for every country listed there.
NORMALIZATION_ONLY_STATES = {
    "DK": {
        "81": "Nordjylland",
        "82": "Midtjylland",
        "83": "Syddanmark",
        "84": "Hovedstaden",
        "85": "Sjælland",
    },
    "FI": {
        "01": "Åland",
        "02": "Etelä-Karjala",
        "03": "Etelä-Pohjanmaa",
        "04": "Etelä-Savo",
        "05": "Kainuu",
        "06": "Kanta-Häme",
        "07": "Keski-Pohjanmaa",
        "08": "Keski-Suomi",
        "09": "Kymenlaakso",
        "10": "Lappi",
        "11": "Pirkanmaa",
        "12": "Pohjanmaa",
        "13": "Pohjois-Karjala",
        "14": "Pohjois-Pohjanmaa",
        "15": "Pohjois-Savo",
        "16": "Päijät-Häme",
        "17": "Satakunta",
        "18": "Uusimaa",
        "19": "Varsinais-Suomi",
    },
    # County numbers in effect since 2024-01-01. ISO 3166-2:NO still lists the
    # 2020-2023 codes 30, 38 and 54 and has not adopted 31, 32, 33, 39, 40, 55
    # or 56.
    "NO": {
        "03": "Oslo",
        "11": "Rogaland",
        "15": "Møre og Romsdal",
        "18": "Nordland",
        "21": "Svalbard",
        "22": "Jan Mayen",
        "31": "Østfold",
        "32": "Akershus",
        "33": "Buskerud",
        "34": "Innlandet",
        "39": "Vestfold",
        "40": "Telemark",
        "42": "Agder",
        "46": "Vestland",
        "50": "Trøndelag",
        "55": "Troms",
        "56": "Finnmark",
    },
    "SE": {
        "AB": "Stockholms län",
        "AC": "Västerbottens län",
        "BD": "Norrbottens län",
        "C": "Uppsala län",
        "D": "Södermanlands län",
        "E": "Östergötlands län",
        "F": "Jönköpings län",
        "G": "Kronobergs län",
        "H": "Kalmar län",
        "I": "Gotlands län",
        "K": "Blekinge län",
        "M": "Skåne län",
        "N": "Hallands län",
        "O": "Västra Götalands län",
        "S": "Värmlands län",
        "T": "Örebro län",
        "U": "Västmanlands län",
        "W": "Dalarnas län",
        "X": "Gävleborgs län",
        "Y": "Västernorrlands län",
        "Z": "Jämtlands län",
    },
}


def _country_states(country_code: str) -> typing.Optional[dict[str, str]]:
    states = units.CountryState.__members__.get(country_code)

    if states is None:
        return NORMALIZATION_ONLY_STATES.get(country_code)

    return {state.name: state.value for state in states.value}


@functools.lru_cache(maxsize=None)
def _state_code_lookups(
    country_code: str,
) -> typing.Optional[tuple[dict[str, str], dict[str, str]]]:
    states = _country_states(str(country_code).upper())

    if states is None:
        return None

    code_lookup = {_fold_text(code): code for code in states}

    keys_by_code = {code: _state_match_keys(name) for code, name in states.items()}
    codes_by_key = {
        key: {code for code, code_keys in keys_by_code.items() if key in code_keys}
        for keys in keys_by_code.values()
        for key in keys
    }

    name_lookup = {
        key: next(iter(codes)) for key, codes in codes_by_key.items() if len(codes) == 1
    }

    return code_lookup, name_lookup


@functools.lru_cache(maxsize=None)
def _state_alias_lookup(country_code: str) -> dict[str, str]:
    aliases = STATE_INPUT_ALIASES.get(str(country_code).upper(), {})
    return {_fold_text(alias): code for alias, code in aliases.items()}


def normalize_state_code(country_code: str, state_code: str) -> str:
    country = str(country_code).upper()
    lookups = _state_code_lookups(country)

    if lookups is None:
        return state_code

    code_lookup, name_lookup = lookups
    value = str(state_code).strip()
    country_prefix = f"{country}-"

    if value.upper().startswith(country_prefix):
        value = value[len(country_prefix) :]

    code = code_lookup.get(_fold_text(value))
    if code is not None:
        return code

    match_keys = _state_match_keys(value)

    return next(
        (
            lookup[key]
            for lookup in (name_lookup, _state_alias_lookup(country))
            for key in match_keys
            if key in lookup
        ),
        state_code,
    )


class AugmentedAddressSerializer(serializers.Serializer):
    def validate(self, data):
        # Format and validate Postal Code
        if all(data.get(key) is not None for key in ["country_code", "postal_code"]):
            postal_code = data["postal_code"]
            country_code = data["country_code"]

            if country_code == units.Country.CA.name:
                formatted = "".join(
                    [c for c in postal_code.split() if c not in ["-", "_"]]
                ).upper()
                if not re.match(r"^([A-Za-z]\d[A-Za-z][-]?\d[A-Za-z]\d)", formatted):
                    raise serializers.ValidationError(
                        {"postal_code": "The Canadian postal code must match Z9Z9Z9"}
                    )

            elif country_code == units.Country.US.name:
                formatted = "".join(postal_code.split())
                if not re.match(r"^\d{5}(-\d{4})?$", formatted):
                    raise serializers.ValidationError(
                        {
                            "postal_code": "The American postal code must match 12345 or 12345-6789"
                        }
                    )

            else:
                formatted = postal_code

            data.update({**data, "postal_code": formatted})

        # Format and validate Phone Number
        if all(
            data.get(key) is not None and data.get(key) != ""
            for key in ["country_code", "phone_number"]
        ):
            phone_number = data["phone_number"]
            country_code = data["country_code"]

            try:
                formatted = phonenumbers.parse(phone_number, country_code)
                data.update(
                    {
                        **data,
                        "phone_number": phonenumbers.format_number(
                            formatted, phonenumbers.PhoneNumberFormat.INTERNATIONAL
                        ),
                    }
                )
            except Exception as e:
                logger.warning("Invalid phone number format", error=str(e))
                raise serializers.ValidationError(
                    {"phone_number": "Invalid phone number format"}
                )

        # Normalize State or Province Code
        if all(
            data.get(key) is not None and data.get(key) != ""
            for key in ["country_code", "state_code"]
        ):
            data.update(
                {
                    **data,
                    "state_code": normalize_state_code(
                        data["country_code"], data["state_code"]
                    ),
                }
            )

        return data
