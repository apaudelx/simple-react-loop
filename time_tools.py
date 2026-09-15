"""Tools the agent can call: geocoding a place name, and time lookup by coordinates."""

import requests

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
TIME_URL = "https://timeapi.io/api/Time/current/coordinate"

TIMEOUT = 10


def geocode_location(location_name: str) -> str:
    """Look up the coordinates of a place from its name.

    Args:
        location_name: A place name, e.g. "Paris" or "Grand Canyon".
    """
    try:
        response = requests.get(
            GEOCODE_URL,
            params={"name": location_name, "count": 1, "language": "en", "format": "json"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        results = response.json().get("results")
    except requests.RequestException as e:
        return f"Geocoding error: {e}"

    if not results:
        return f"No place named '{location_name}' was found."

    place = results[0]
    label = ", ".join(
        part for part in (place.get("name"), place.get("admin1"), place.get("country")) if part
    )
    return (
        f"{label} is at latitude {place['latitude']}, longitude {place['longitude']} "
        f"(timezone {place.get('timezone', 'unknown')})."
    )


def get_time_at_coordinates(latitude: float, longitude: float) -> str:
    """Get the current local time at a set of coordinates.

    Args:
        latitude: Latitude in decimal degrees.
        longitude: Longitude in decimal degrees.
    """
    try:
        response = requests.get(
            TIME_URL,
            params={"latitude": latitude, "longitude": longitude},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        return f"Time API error: {e}"

    return (
        f"{data['dayOfWeek']} {data['date']} at {data['time']} "
        f"({data['timeZone']}, DST active: {data['dstActive']})."
    )


if __name__ == "__main__":
    # Exercise the tools directly, without the model in the loop.
    print(geocode_location("Grand Canyon"))
    print(get_time_at_coordinates(36.05443, -112.13934))
