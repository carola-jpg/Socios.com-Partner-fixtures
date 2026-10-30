"""Which ESPN competitions to check for each group of partners.

Each value is a list of ESPN league slugs, or "tsdb:<id>" for a TheSportsDB league
(used where ESPN has gaps). Slugs marked "unverified" are
best guesses; if ESPN doesn't have them, the run carries on and lists them
as "Not available" on the Coverage sheet of the Excel file.

To add a competition for every partner in a group, add its slug here.
To add one for a single partner, use the extra_competitions column in
config/partners.csv instead.
"""

UEFA_CLUB = [
    "uefa.champions",
    "uefa.champions_qual",
    "uefa.europa",
    "uefa.europa_qual",
    "uefa.europa.conf",
    "uefa.europa.conf_qual",
    "uefa.super_cup",  # unverified
]

CONMEBOL_CLUB = [
    "conmebol.libertadores",
    "conmebol.sudamericana",
    "conmebol.recopa",
]

AFC_CLUB = [
    "afc.champions",
    "afc.cup",
]

GROUPS = {
    # Clubs: top two divisions (to follow promotion/relegation), domestic cups, continental
    "ITA": ["ita.1", "ita.2", "ita.coppa_italia", "ita.super_cup"] + UEFA_CLUB,
    "ENG": ["eng.1", "eng.2", "eng.fa", "eng.league_cup", "eng.charity"] + UEFA_CLUB,
    "ESP": ["esp.1", "esp.2", "esp.copa_del_rey", "esp.super_cup"] + UEFA_CLUB,
    "FRA": ["fra.1", "fra.2", "fra.coupe_de_france", "fra.super_cup"] + UEFA_CLUB,
    "POR": ["por.1", "por.taca.portugal"] + UEFA_CLUB,
    "NED": ["ned.1", "ned.2", "ned.cup"] + UEFA_CLUB,
    "TUR": ["tur.1", "tur.cup"] + UEFA_CLUB,  # tur.cup unverified
    # ESPN has no 2026-27 Cypriot season, so the league comes from TheSportsDB (id 4630)
    "CYP": ["tsdb:4630", "cyp.1"] + UEFA_CLUB,
    "CRO": ["cro.1"] + UEFA_CLUB,  # cro.1 unverified
    "POL": ["pol.1"] + UEFA_CLUB,  # pol.1 unverified
    "SUI": ["sui.1"] + UEFA_CLUB,  # sui.1 unverified
    "BRA": [
        "bra.1",
        "bra.2",
        "bra.copa_do_brazil",
        # State championships (Jan-Apr), unverified slugs
        "bra.camp.paulista",
        "bra.camp.carioca",
        "bra.camp.mineiro",
        "bra.camp.gaucho",
    ] + CONMEBOL_CLUB,
    "COL": ["col.1"] + CONMEBOL_CLUB,
    "MYS": ["mys.1"] + AFC_CLUB,
    "IDN": ["idn.1"] + AFC_CLUB,
    # National teams
    "NAT_UEFA_MEN": [
        "fifa.friendly",
        "uefa.nations",
        "fifa.worldq.uefa",
        "uefa.euroq",
        "fifa.world",
        "uefa.euro",
    ],
    "NAT_CAF_MEN": [
        "fifa.friendly",
        "fifa.worldq.caf",
        "caf.nations_qual",
        "caf.nations",
        "fifa.world",
    ],
    "NAT_UEFA_WOMEN": [
        "fifa.friendly.w",
        "uefa.w.nations",
        "fifa.wworldq.uefa",
        "uefa.weuro",
        "fifa.wwc",
    ],
    "NAT_U21": [
        "uefa.euro_u21_qual",
        "uefa.euro_u21",
        "fifa.friendly_u21",
    ],
}

# Readable names used when ESPN doesn't return one.
FALLBACK_NAMES = {
    "uefa.champions": "UEFA Champions League",
    "uefa.champions_qual": "UEFA Champions League Qualifying",
    "uefa.europa": "UEFA Europa League",
    "uefa.europa_qual": "UEFA Europa League Qualifying",
    "uefa.europa.conf": "UEFA Conference League",
    "uefa.europa.conf_qual": "UEFA Conference League Qualifying",
    "uefa.super_cup": "UEFA Super Cup",
    "ita.1": "Serie A",
    "ita.2": "Serie B",
    "ita.coppa_italia": "Coppa Italia",
    "ita.super_cup": "Supercoppa Italiana",
    "eng.1": "Premier League",
    "eng.2": "Championship",
    "eng.fa": "FA Cup",
    "eng.league_cup": "Carabao Cup",
    "eng.charity": "Community Shield",
    "esp.1": "LALIGA",
    "esp.2": "LALIGA 2",
    "esp.copa_del_rey": "Copa del Rey",
    "esp.super_cup": "Supercopa de España",
    "fra.1": "Ligue 1",
    "fra.2": "Ligue 2",
    "fra.coupe_de_france": "Coupe de France",
    "fra.super_cup": "Trophée des Champions",
    "por.1": "Primeira Liga",
    "por.taca.portugal": "Taça de Portugal",
    "ned.1": "Eredivisie",
    "ned.2": "Eerste Divisie",
    "ned.cup": "KNVB Beker",
    "tur.1": "Süper Lig",
    "tur.cup": "Turkish Cup",
    "cyp.1": "Cypriot First Division",
    "tsdb:4630": "Cypriot First Division",
    "cro.1": "Croatian HNL",
    "pol.1": "Ekstraklasa",
    "sui.1": "Swiss Super League",
    "bra.1": "Brasileirão Série A",
    "bra.2": "Brasileirão Série B",
    "bra.copa_do_brazil": "Copa do Brasil",
    "bra.camp.paulista": "Campeonato Paulista",
    "bra.camp.carioca": "Campeonato Carioca",
    "bra.camp.mineiro": "Campeonato Mineiro",
    "bra.camp.gaucho": "Campeonato Gaúcho",
    "conmebol.libertadores": "Copa Libertadores",
    "conmebol.sudamericana": "Copa Sudamericana",
    "conmebol.recopa": "Recopa Sudamericana",
    "col.1": "Colombian Primera A",
    "mys.1": "Malaysia Super League",
    "idn.1": "Indonesia Super League",
    "afc.champions": "AFC Champions League Elite",
    "afc.cup": "AFC Champions League Two",
    "fifa.friendly": "International Friendly",
    "uefa.nations": "UEFA Nations League",
    "fifa.worldq.uefa": "World Cup Qualifying (UEFA)",
    "uefa.euroq": "Euro Qualifying",
    "fifa.world": "FIFA World Cup",
    "uefa.euro": "UEFA European Championship",
    "fifa.worldq.caf": "World Cup Qualifying (CAF)",
    "caf.nations_qual": "AFCON Qualifying",
    "caf.nations": "Africa Cup of Nations",
    "fifa.friendly.w": "Women's International Friendly",
    "uefa.w.nations": "UEFA Women's Nations League",
    "fifa.wworldq.uefa": "Women's World Cup Qualifying (UEFA)",
    "uefa.weuro": "UEFA Women's Euro",
    "fifa.wwc": "FIFA Women's World Cup",
    "uefa.euro_u21_qual": "U21 Euro Qualifying",
    "uefa.euro_u21": "UEFA U21 Championship",
    "fifa.friendly_u21": "U21 International Friendly",
}


def competitions_for(group: str, extra: list[str]) -> list[str]:
    if group not in GROUPS:
        raise ValueError(f"Unknown group '{group}' in partners.csv. Valid groups: {', '.join(GROUPS)}")
    slugs = list(GROUPS[group])
    for s in extra:
        if s and s not in slugs:
            slugs.append(s)
    return slugs
