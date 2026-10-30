"""Work out a fixture's local time zone from where it's played."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")

COUNTRY_TZ = {
    "italy": "Europe/Rome", "england": "Europe/London", "scotland": "Europe/London",
    "wales": "Europe/London", "northern ireland": "Europe/London", "united kingdom": "Europe/London",
    "ireland": "Europe/Dublin", "spain": "Europe/Madrid", "france": "Europe/Paris",
    "portugal": "Europe/Lisbon", "netherlands": "Europe/Amsterdam", "belgium": "Europe/Brussels",
    "germany": "Europe/Berlin", "austria": "Europe/Vienna", "switzerland": "Europe/Zurich",
    "monaco": "Europe/Monaco", "türkiye": "Europe/Istanbul", "turkey": "Europe/Istanbul",
    "cyprus": "Asia/Nicosia", "croatia": "Europe/Zagreb", "poland": "Europe/Warsaw",
    "czechia": "Europe/Prague", "czech republic": "Europe/Prague", "slovakia": "Europe/Bratislava",
    "hungary": "Europe/Budapest", "romania": "Europe/Bucharest", "bulgaria": "Europe/Sofia",
    "serbia": "Europe/Belgrade", "slovenia": "Europe/Ljubljana", "bosnia and herzegovina": "Europe/Sarajevo",
    "montenegro": "Europe/Podgorica", "north macedonia": "Europe/Skopje", "albania": "Europe/Tirane",
    "kosovo": "Europe/Belgrade", "greece": "Europe/Athens", "denmark": "Europe/Copenhagen",
    "sweden": "Europe/Stockholm", "norway": "Europe/Oslo", "finland": "Europe/Helsinki",
    "iceland": "Atlantic/Reykjavik", "ukraine": "Europe/Kyiv", "israel": "Asia/Jerusalem",
    "georgia": "Asia/Tbilisi", "armenia": "Asia/Yerevan", "azerbaijan": "Asia/Baku",
    "kazakhstan": "Asia/Almaty", "luxembourg": "Europe/Luxembourg", "malta": "Europe/Malta",
    "estonia": "Europe/Tallinn", "latvia": "Europe/Riga", "lithuania": "Europe/Vilnius",
    "moldova": "Europe/Chisinau", "andorra": "Europe/Andorra", "san marino": "Europe/San_Marino",
    "liechtenstein": "Europe/Vaduz", "gibraltar": "Europe/Gibraltar", "faroe islands": "Atlantic/Faroe",
    "brazil": "America/Sao_Paulo", "argentina": "America/Argentina/Buenos_Aires",
    "uruguay": "America/Montevideo", "paraguay": "America/Asuncion", "chile": "America/Santiago",
    "colombia": "America/Bogota", "peru": "America/Lima", "ecuador": "America/Guayaquil",
    "bolivia": "America/La_Paz", "venezuela": "America/Caracas",
    "malaysia": "Asia/Kuala_Lumpur", "indonesia": "Asia/Jakarta", "singapore": "Asia/Singapore",
    "thailand": "Asia/Bangkok", "vietnam": "Asia/Ho_Chi_Minh", "japan": "Asia/Tokyo",
    "south korea": "Asia/Seoul", "korea republic": "Asia/Seoul", "china": "Asia/Shanghai",
    "saudi arabia": "Asia/Riyadh", "qatar": "Asia/Qatar", "united arab emirates": "Asia/Dubai",
    "uae": "Asia/Dubai", "iran": "Asia/Tehran", "india": "Asia/Kolkata", "philippines": "Asia/Manila",
    "south africa": "Africa/Johannesburg", "morocco": "Africa/Casablanca", "egypt": "Africa/Cairo",
    "nigeria": "Africa/Lagos", "ghana": "Africa/Accra", "senegal": "Africa/Dakar",
    "algeria": "Africa/Algiers", "tunisia": "Africa/Tunis", "cameroon": "Africa/Douala",
    "ivory coast": "Africa/Abidjan", "côte d'ivoire": "Africa/Abidjan", "kenya": "Africa/Nairobi",
    "mexico": "America/Mexico_City", "canada": "America/Toronto", "usa": "America/New_York",
    "united states": "America/New_York", "australia": "Australia/Sydney",
}

# Cities in a different zone from the rest of their country.
CITY_TZ = {
    "las palmas": "Atlantic/Canary", "las palmas de gran canaria": "Atlantic/Canary",
    "santa cruz de tenerife": "Atlantic/Canary", "tenerife": "Atlantic/Canary",
    "funchal": "Atlantic/Madeira", "ponta delgada": "Atlantic/Azores",
    "manaus": "America/Manaus", "cuiaba": "America/Cuiaba", "cuiabá": "America/Cuiaba",
    "porto velho": "America/Porto_Velho", "rio branco": "America/Rio_Branco",
    "campo grande": "America/Campo_Grande", "boa vista": "America/Boa_Vista",
    "denpasar": "Asia/Makassar", "bali": "Asia/Makassar", "gianyar": "Asia/Makassar",
    "makassar": "Asia/Makassar", "samarinda": "Asia/Makassar", "balikpapan": "Asia/Makassar",
    "jayapura": "Asia/Jayapura",
}

# When a fixture has no country yet: the competition's country (from its code).
SLUG_TZ = {
    "ita": "Europe/Rome", "eng": "Europe/London", "fra": "Europe/Paris", "esp": "Europe/Madrid",
    "por": "Europe/Lisbon", "ned": "Europe/Amsterdam", "tur": "Europe/Istanbul", "cyp": "Asia/Nicosia",
    "cro": "Europe/Zagreb", "pol": "Europe/Warsaw", "sui": "Europe/Zurich", "bra": "America/Sao_Paulo",
    "col": "America/Bogota", "mys": "Asia/Kuala_Lumpur", "idn": "Asia/Jakarta",
    "tsdb:4630": "Asia/Nicosia", "tsdb:4629": "Europe/Zagreb", "tsdb:4422": "Europe/Warsaw",
    "tsdb:4675": "Europe/Zurich", "tsdb:4790": "Asia/Jakarta",
}


def local_zone(r: dict) -> ZoneInfo | None:
    """The time zone the match is played in, or None if we can't tell."""
    city = (r.get("city") or "").strip().lower()
    for c in (city, city.split(",")[0].strip()):
        if c in CITY_TZ:
            return ZoneInfo(CITY_TZ[c])
    country = (r.get("country") or "").strip().lower()
    if country in COUNTRY_TZ:
        return ZoneInfo(COUNTRY_TZ[country])
    # National team at home with no venue yet: the home nation.
    if r.get("side") == "Home" and not r.get("neutral"):
        home = (r.get("home") or "").strip().lower()
        if home in COUNTRY_TZ:
            return ZoneInfo(COUNTRY_TZ[home])
    slug = r.get("slug") or ""
    key = slug if slug.startswith("tsdb:") else slug.split(".")[0]
    if key in SLUG_TZ and r.get("side") == "Home":
        return ZoneInfo(SLUG_TZ[key])
    return None


def parse_utc(iso: str) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def offset_label(dt: datetime) -> str:
    """'UTC+1', 'UTC-3', 'UTC+5:30'."""
    off = dt.utcoffset()
    mins = int(off.total_seconds() // 60) if off is not None else 0
    if mins == 0:
        return "UTC+0"
    sign = "+" if mins > 0 else "-"
    h, m = divmod(abs(mins), 60)
    return f"UTC{sign}{h}" + (f":{m:02d}" if m else "")


def local_and_utc(r: dict) -> tuple[datetime | None, datetime | None, str]:
    """(local kick-off, UTC kick-off, zone label). Local is None if the zone is unknown."""
    utc = parse_utc(r.get("date_utc", ""))
    if not utc:
        return None, None, ""
    zone = local_zone(r)
    if not zone:
        return None, utc, ""
    loc = utc.astimezone(zone)
    return loc, utc, offset_label(loc)
