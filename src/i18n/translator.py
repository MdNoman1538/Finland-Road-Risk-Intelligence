from typing import Literal

Lang = Literal["en", "fi"]

SEVERITY_MAP: dict[str, str] = {
    "Ei henkilövahinkoja": "Property Damage Only (No Injuries)",
    "Loukkaantumiseen johtanut": "Injury Crash",
    "Vakavaan loukkaantumiseen johtanut": "Severe Injury Crash",
    "Kuolemaan johtanut": "Fatal Crash",
    "Unknown": "Unknown",
}

SURFACE_MAP: dict[str, str] = {
    "paljas, kuiva": "Bare, dry",
    "paljas, märkä": "Bare, wet",
    "jäinen": "Icy",
    "luminen": "Snowy",
    "sohjoinen": "Slushy",
    "polanteinen": "Packed snow / rutted ice",
    "kuura": "Frost / rime",
    "ajourat paljaat": "Bare wheel tracks (snow/ice between)",
    "sora, kuiva": "Gravel, dry",
    "sora, märkä": "Gravel, wet",
    "ei arvoa": "Not recorded",
    "unknown": "Unknown",
}

LIGHTING_MAP: dict[str, str] = {
    "päivänvalo": "Daylight",
    "hämärä": "Twilight / Dusk",
    "tie valaistu": "Dark (Streetlights on)",
    "pimeä (valaisematon)": "Dark (Unlit road)",
    "pimeä, valaisematon": "Dark (Unlit road)",
    "pimeä, valaistu": "Dark (Streetlights on)",
    "ei arvoa": "Not recorded",
    "unknown": "Unknown",
}

VEHICLE_MAP: dict[str, str] = {
    "henkilöauto": "Passenger Car",
    "pakettiauto": "Delivery Van",
    "kuorma-auto": "Truck / Lorry",
    "linja-auto": "Bus",
    "moottoripyörä": "Motorcycle",
    "mopo": "Moped",
    "mopedi": "Moped",
    "kevyt nelipyörä": "Microcar / Light Quadricycle",
    "polkupyöräilijä": "Cyclist",
    "polkupyörä": "Cyclist",
    "jalankulkija": "Pedestrian",
    "potkukelkkailija": "Kicksledder",
    "hirvi": "Moose (Elk)",
    "peura": "Deer",
    "poro": "Reindeer",
    "muu eläin": "Other Animal",
    "traktori": "Tractor",
    "työkone": "Work Machine",
    "raitiovaunu": "Tram",
    "juna": "Train",
}

ROAD_USER_LABELS: dict[str, dict[str, str | None]] = {
    "en": {
        "All Road Users": None,
        "Cyclist (Polkupyöräilijä)": "polkupyöräilijä",
        "Pedestrian (Jalankulkija)": "jalankulkija",
        "Passenger Car (Henkilöauto)": "henkilöauto",
        "Delivery Van (Pakettiauto)": "pakettiauto",
        "Truck / Heavy Vehicle (Kuorma-auto)": "kuorma-auto",
        "Moose (Hirvi)": "hirvi",
        "Deer (Peura)": "peura",
        "Reindeer (Poro)": "poro",
        "Motorcycle (Moottoripyörä)": "moottoripyörä",
        "Moped (Mopedi)": "mopedi",
    },
    "fi": {
        "Kaikki tienkäyttäjät": None,
        "Polkupyöräilijä": "polkupyöräilijä",
        "Jalankulkija": "jalankulkija",
        "Henkilöauto": "henkilöauto",
        "Pakettiauto": "pakettiauto",
        "Kuorma-auto": "kuorma-auto",
        "Hirvi": "hirvi",
        "Peura": "peura",
        "Poro": "poro",
        "Moottoripyörä": "moottoripyörä",
        "Mopedi": "mopedi",
    },
}

# Complete 1-to-1 mapping of all distinct normalized accident_type values in road_risk.duckdb
ACCIDENT_TYPE_EXACT: dict[str, str] = {
    "eläinonnettomuus": "Animal / wildlife collision",
    "suistuminen oikealle suoralla": "Run-off-road to the right on straight road",
    "muu onnettomuus": "Other accident type",
    "peräänajo jarruttavaan ajoneuvoon": "Rear-end collision with braking vehicle",
    "peräänajo liikenne-esteen takia pysäht. ajoneuvoon": "Rear-end collision with vehicle stopped due to traffic obstruction",
    "peruutusonnettomuus": "Reversing collision",
    "suistuminen vasemmalle suoralla": "Run-off-road to the left on straight road",
    "suistuminen oik. vasemmalle kääntyvässä kaarteessa": "Run-off-road to the right on left-hand curve",
    "muu risteämisonnettomuus, ei kääntymistä": "Other intersection crossing collision (no turning)",
    "ajo risteäviä ajosuuntia suoraan": "Crossing paths collision (both driving straight)",
    "suistuminen tieltä risteyksessä": "Run-off-road at intersection",
    "kylkikosketus": "Sideswipe / lateral collision",
    "suistuminen vas. oikealle kääntyvässä kaarteessa": "Run-off-road to the left on right-hand curve",
    "muu törmäys käännyttäessä vasemmalle": "Other collision while turning left",
    "kääntyminen vas. vastaantulevan eteen tai kylkeen": "Left turn into path or side of oncoming vehicle",
    "kääntyminen vasemmalle toisen eteen tai kylkeen": "Left turn into path or side of another vehicle",
    "muu tieltä suistuminen": "Other run-off-road crash",
    "pyöräilijä pyörätiellä risteyksessä": "Cyclist on cycle path at intersection",
    "kohtaaminen suoralla": "Head-on collision on straight road",
    "kaistanvaihto oikealle": "Lane-change collision to the right",
    "muu peräänajo liikkuvaan ajoneuvoon": "Other rear-end collision with moving vehicle",
    "suistuminen oik. oikealle kääntyvässä kaarteessa": "Run-off-road to the right on right-hand curve",
    "kaistanvaihto vasemmalle": "Lane-change collision to the left",
    "törmäys oik. reunassa olevaan pysäköityyn ajon": "Collision with parked vehicle on right edge",
    "muu samat ajosuunnat, ei kääntymistä": "Other same-direction collision (no turning)",
    "ohitus": "Overtaking collision",
    "muu kohtaamisonnettomuus, ei kääntymistä": "Other head-on collision (no turning)",
    "muu törmäys käännyttäessä oikealle": "Other collision while turning right",
    "suistuminen vas. vasemmalle kääntyvässä kaart": "Run-off-road to the left on left-hand curve",
    "peräänajo käännyttäessä vasemmalle": "Rear-end collision while turning left",
    "kohtaaminen kaarteessa": "Head-on collision on curve",
    "muu risteämisonnettomuus, kääntyminen": "Other intersection crossing collision (with turning)",
    "kääntyminen oikealle toisen eteen tai kylkeen": "Right turn into path or side of another vehicle",
    "käänt vasemmalle risteävän eteen tai kylkeen": "Left turn into path or side of crossing vehicle",
    "pp pyörätiellä, toinen ajoneuvo kääntyi oikealle": "Cyclist on cycle path, other vehicle turned right",
    "kumoonajo ajoradalla": "Single-vehicle overturning / rollover on carriageway",
    "törmäys esteeseen ajoradalla": "Collision with obstacle on carriageway",
    "muu jalankulkuonnettomuus suojatiellä": "Other pedestrian crash on crosswalk",
    "törmäys liikennekorokkeeseen": "Collision with traffic island / median",
    "muu jalankulkuonnettomuus suojatien ulkopuolella": "Other pedestrian crash outside crosswalk",
    "muu samat ajosuunnat, kääntyminen": "Other same-direction collision (with turning)",
    "pyöräilijä pyörätiellä muualla": "Cyclist on cycle path (non-intersection)",
    "suistuminen väistämisen seurauksena": "Run-off-road while swerving to avoid hazard",
    "u-käännös samaan suuntaan kulkevan ajoneuvon eteen": "U-turn into path of same-direction vehicle",
    "jk ylitti muutoin ajorataa suojatien ulkopuolella": "Pedestrian crossing carriageway outside crosswalk",
    "muu vastakkaiset ajosuunnat, kääntyminen": "Other opposite-direction collision (with turning)",
    "jk suojatiellä, ajoneuvo kääntyi vasemmalle": "Pedestrian on crosswalk, vehicle turned left",
    "pp pyörätiellä, toinen ajoneuvo kääntyi vasemmalle": "Cyclist on cycle path, other vehicle turned left",
    "pp pyörätiellä, vastakk. ajoneuvo kääntyi oikealle": "Cyclist on cycle path, oncoming vehicle turned right",
    "samat ajosuunnat muu törmäys käännyttäessä oikealle": "Same direction: other collision while turning right",
    "törmäys vas. reunassa olevaan pysäköityyn ajon": "Collision with parked vehicle on left edge",
    "jalankulkija suojatiellä risteyksen jälkeen": "Pedestrian on crosswalk after intersection",
    "ajo liikkeelle lähtevään ajoneuvoon": "Collision with vehicle pulling away / starting",
    "jalankulkija suojatiellä ennen risteystä": "Pedestrian on crosswalk before intersection",
    "kääntyminen oik. vastaantulevan eteen tai kylkeen": "Right turn into path or side of oncoming vehicle",
    "kääntyminen samaan ajosuuntaan": "Turning into same direction of travel",
    "jk suojatiellä, suojatie risteyksen ulkopuolella": "Pedestrian on mid-block crosswalk (outside intersection)",
    "jk suojatiellä, ajoneuvo kääntyi oikealle": "Pedestrian on crosswalk, vehicle turned right",
    "pp-tietä ajava pp käänt. ajon. eteen tai kylkeen": "Cyclist from cycle path turned into path/side of vehicle",
    "jk jalkakäytävällä tai liikennekorokkeella": "Pedestrian on sidewalk or traffic island",
    "jalankulkija kulki liikenteen suuntaan": "Pedestrian walking with traffic",
    "junan ja ajoneuvon törmäys": "Train and road vehicle collision",
    "matkustaja nousemassa ajon. tai poistumassa siitä": "Passenger boarding or alighting from vehicle",
    "jk suojatiellä, suojatien eteen pysähtynyt ajon": "Pedestrian on crosswalk, vehicle stopped before crosswalk",
    "kohtaaminen ohitettaessa suoralla": "Head-on collision while overtaking on straight road",
    "pp pyörätiellä, vastakk. ajon. kääntyi vasemmalle": "Cyclist on cycle path, oncoming vehicle turned left",
    "vastakkaiset ajosuunnat muu törmäys käännyttäessä oikealle": "Opposite directions: other collision while turning right",
    "jalankulkija pysähtyneenä ajoradalla": "Pedestrian standing/stopped on carriageway",
    "u-käännös vastaantulevan eteen": "U-turn into path of oncoming vehicle",
    "kääntyminen eri ajosuuntiin": "Turning into different directions",
    "jalankulkija tuli pysähtyneen ajoneuvon takaa": "Pedestrian emerged from behind stopped vehicle",
    "kaksoisohitus": "Double overtaking collision",
    "jalankulkija kulki liikennettä vastaan": "Pedestrian walking against traffic",
    "yhtäaikainen vasemmalle kääntyminen": "Simultaneous left turn collision",
    "kohtaaminen ohitettaessa kaarteessa": "Head-on collision while overtaking on curve",
    "junan ja jalankulkijan törmäys": "Train and pedestrian collision",
    "unknown": "Unknown",
}


def translate_severity(val: str, lang: Lang = "en") -> str:
    if lang == "fi" or not val:
        return val
    return SEVERITY_MAP.get(val.strip(), val)


def translate_surface(val: str, lang: Lang = "en") -> str:
    if lang == "fi" or not val:
        return val
    return SURFACE_MAP.get(val.strip().lower(), val)


def translate_lighting(val: str, lang: Lang = "en") -> str:
    if lang == "fi" or not val:
        return val
    return LIGHTING_MAP.get(val.strip().lower(), val)


def translate_vehicle(val: str, lang: Lang = "en") -> str:
    if lang == "fi" or not val:
        return val
    return VEHICLE_MAP.get(val.strip().lower(), val.capitalize())


def translate_accident_type(val: str, lang: Lang = "en") -> str:
    if lang == "fi" or not val:
        return val
    cleaned = " ".join(val.strip().split())
    normalized = cleaned.rstrip(".").lower()

    if normalized in ACCIDENT_TYPE_EXACT:
        return f"{ACCIDENT_TYPE_EXACT[normalized]} ({cleaned})"

    return cleaned
