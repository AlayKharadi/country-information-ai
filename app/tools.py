"""
REST Countries API integration.

This is the only module that communicates with the external API. All field
mapping and response parsing lives here so the nodes above it stay clean
and focused on control flow rather than HTTP and data wrangling.
"""

import httpx

from .config import COUNTRIES_API_BASE_URL, API_TIMEOUT_SECONDS
from .models import CountryData


# Maps our internal field names to the keys the REST Countries API returns.
# Decoupling these vocabularies means a change to the API response shape is
# contained to this single dict so no other file needs to know API internals.
_FIELD_MAP: dict[str, str] = {
    "population": "population",
    "capital": "capital",
    "currency": "currencies",
    "languages": "languages",
    "area": "area",
    "region": "region",
    "subregion": "subregion",
    "flag": "flags",
    "timezones": "timezones",
    "borders": "borders",
}


def _parse_field(field: str, raw_value) -> str | None:
    """
    Convert a raw API value into a human-readable string.

    The REST Countries API returns nested objects for some fields (currencies,
    languages, flags). This function normalises them all to plain strings so
    the synthesis prompt can work with simple bullet points rather than JSON.
    Returns None if raw_value is None (field absent from API response).
    """
    if raw_value is None:
        return None

    if field == "currency":
        # {"USD": {"name": "United States dollar", "symbol": "$"}, ...}
        parts = []
        for _code, info in raw_value.items():
            name = info.get("name", _code)
            symbol = info.get("symbol", "")
            parts.append(f"{name} ({symbol})" if symbol else name)
        return ", ".join(parts)

    if field == "languages":
        # {"eng": "English", "fra": "French"}
        return ", ".join(raw_value.values())

    if field == "flag":
        # {"png": "...", "svg": "...", "alt": "..."}
        # Prefer PNG for broad compatibility; fall back to SVG.
        return raw_value.get("png") or raw_value.get("svg") or ""

    if isinstance(raw_value, list):
        return ", ".join(str(v) for v in raw_value)

    return str(raw_value)


async def fetch_country_data(country: str, fields: list[str]) -> CountryData:
    """
    Fetch and filter country data from the REST Countries API.

    Accepts our internal field names, maps them to API keys, retrieves the
    first (most relevant) result, and returns a CountryData with only the
    requested fields parsed into readable strings.

    Error handling is deliberate: we never raise from here. Every failure mode
    returns a CountryData with found=False and a user-facing error message so
    the synthesis node can decide what to show.
    """
    url = f"{COUNTRIES_API_BASE_URL}/name/{country}"

    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT_SECONDS) as client:
            response = await client.get(url)

        if response.status_code == 404:
            return CountryData(
                country=country,
                fields=fields,
                data={},
                found=False,
                error=(
                    f"I couldn't find any country named '{country}'. "
                    "Please check the spelling and try again."
                ),
            )

        response.raise_for_status()
        # The API returns a list sorted by relevance; the first result is best.
        api_data: dict = response.json()[0]

    except httpx.TimeoutException:
        return CountryData(
            country=country,
            fields=fields,
            data={},
            found=False,
            error="The request timed out. Please try again in a moment.",
        )
    except Exception as exc:
        return CountryData(
            country=country,
            fields=fields,
            data={},
            found=False,
            error=f"Something went wrong while fetching country data: {exc}",
        )

    # Extract only the fields the intent node identified as relevant.
    # Fields absent from the API response get None rather than raising
    # the synthesis node will acknowledge them as "Not available".
    parsed: dict[str, str | None] = {}
    for field in fields:
        api_key = _FIELD_MAP.get(field)
        if api_key is None:
            # Unknown field: not in our supported set, skip silently.
            continue
        raw = api_data.get(api_key)
        parsed[field] = _parse_field(field, raw)

    return CountryData(country=country, fields=fields, data=parsed, found=True)
