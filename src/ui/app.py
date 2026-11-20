import duckdb
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from src.i18n import ROAD_USER_LABELS, translate_accident_type
from src.scoring import RiskQuery, SpatialRiskEngine

st.set_page_config(page_title="Finland Road Risk Explorer", layout="wide")

if "lat" not in st.session_state:
    st.session_state.lat = 65.01210
if "lon" not in st.session_state:
    st.session_state.lon = 25.46510


@st.cache_resource
def get_engine() -> SpatialRiskEngine:
    return SpatialRiskEngine()


@st.cache_data
def get_regions_and_municipalities(_db_path: str) -> pd.DataFrame:
    con = duckdb.connect(_db_path, read_only=True)
    try:
        return con.execute("""
            SELECT
                TRIM(region) AS region,
                TRIM(municipality) AS municipality,
                COUNT(*) AS total_crashes,
                MEDIAN(lat) AS center_lat,
                MEDIAN(lon) AS center_lon
            FROM road_accidents
            WHERE municipality IS NOT NULL
              AND TRIM(municipality) NOT IN ('', 'Unknown', 'Ei arvoa', '-')
              AND region IS NOT NULL
              AND TRIM(region) NOT IN ('', 'Unknown', 'Ei arvoa', '-')
              AND lat IS NOT NULL
              AND lon IS NOT NULL
            GROUP BY TRIM(region), TRIM(municipality)
            ORDER BY total_crashes DESC;
        """).fetchdf()
    finally:
        con.close()


@st.cache_data
def get_municipality_hotspots(
    _db_path: str, municipality: str, winter_only: bool, road_user: str | None
) -> pd.DataFrame:
    con = duckdb.connect(_db_path, read_only=True)
    # Silent `except: pass` hides failures; tracked as known issue #1-2 in docs/project-status.md,
    # replaced by a shared connection helper in the spatial-extension fix PR.
    try:  # noqa: SIM105
        con.execute("INSTALL spatial; LOAD spatial;")
    except Exception:
        pass  # Fallback if already loaded or running offline
    try:
        where_clauses = ["TRIM(r.municipality) = $1"]
        params: list = [municipality]

        if winter_only:
            where_clauses.append(
                "LOWER(r.surface_condition) IN ('jäinen', 'luminen', 'sohjoinen', 'polanteinen', 'kuura')"
            )

        join_clause = ""
        if road_user:
            join_clause = """
                INNER JOIN (
                    SELECT DISTINCT accident_id
                    FROM accident_participants
                    WHERE LOWER(vehicle_type) = LOWER($2)
                ) p ON r.accident_id = p.accident_id
            """
            params.append(road_user)

        sql = f"""
            SELECT
                ROUND(ST_X(r.geom_3067) / 250.0) * 250 AS grid_x,
                ROUND(ST_Y(r.geom_3067) / 250.0) * 250 AS grid_y,
                COUNT(*) AS crashes,
                SUM(CASE WHEN r.severity = 'Kuolemaan johtanut' THEN 10
                         WHEN r.severity = 'Vakavaan loukkaantumiseen johtanut' THEN 5
                         WHEN r.severity = 'Loukkaantumiseen johtanut' THEN 3
                         ELSE 1 END) AS severity_points,
                AVG(r.lat) AS lat,
                AVG(r.lon) AS lon,
                MODE(r.accident_type) AS dominant_crash_type
            FROM road_accidents r
            {join_clause}
            WHERE {" AND ".join(where_clauses)}
            GROUP BY grid_x, grid_y
            ORDER BY severity_points DESC, crashes DESC
            LIMIT 10;
        """
        return con.execute(sql, params).fetchdf()
    finally:
        con.close()


def severity_color(severity_label: str) -> str:
    s = severity_label.lower()
    if "fatal" in s or "severe" in s or "kuolemaan" in s or "vakavaan" in s:
        return "red"
    if "injury" in s or "loukkaantumiseen" in s:
        return "orange"
    return "blue"


engine = get_engine()
geo_df = get_regions_and_municipalities(str(engine.db_path))

with st.sidebar:
    lang_choice = st.radio("Language / Kieli", ["English", "Suomi"], horizontal=True)
    lang = "en" if lang_choice == "English" else "fi"

    st.divider()
    st.header("1. Region & Municipality" if lang == "en" else "1. Maakunta ja kunta")

    region_counts = geo_df.groupby("region")["total_crashes"].sum().sort_values(ascending=False)
    all_reg_label = "All Regions (Whole Finland)" if lang == "en" else "Kaikki maakunnat (Koko Suomi)"
    region_options = [all_reg_label] + [f"{reg} ({cnt:,})" for reg, cnt in region_counts.items()]
    default_reg_idx = next((i for i, r in enumerate(region_options) if "Pohjois-Pohjanmaa" in r), 0)
    selected_region_label = st.selectbox(
        "Zone / Region (Maakunta)" if lang == "en" else "Maakunta",
        region_options,
        index=default_reg_idx,
    )

    if selected_region_label == all_reg_label:
        filtered_munis = geo_df
    else:
        selected_region = selected_region_label.split(" (")[0]
        filtered_munis = geo_df[geo_df["region"] == selected_region]

    muni_options = [f"{row.municipality} ({row.total_crashes:,})" for row in filtered_munis.itertuples()]
    default_muni_idx = next((i for i, m in enumerate(muni_options) if m.startswith("Oulu ")), 0)
    selected_muni_label = st.selectbox(
        "Municipality (Kunta)" if lang == "en" else "Kunta",
        muni_options,
        index=default_muni_idx,
    )
    selected_muni = selected_muni_label.split(" (")[0]

    btn_center = "Center Map on Municipality" if lang == "en" else "Keskitä kartta kuntaan"
    if st.button(btn_center, use_container_width=True):
        m_row = filtered_munis[filtered_munis["municipality"] == selected_muni].iloc[0]
        st.session_state.lat = float(m_row["center_lat"])
        st.session_state.lon = float(m_row["center_lon"])
        st.rerun()

    st.divider()
    st.header("2. Risk & Context Filters" if lang == "en" else "2. Riski- ja olosuhdesuodattimet")
    winter_only = st.checkbox(
        "Winter / Icy / Snowy Surfaces Only" if lang == "en" else "Vain talvi- / jää- / lumikelit",
        value=False,
    )

    user_options = ROAD_USER_LABELS[lang]
    selected_user_label = st.selectbox(
        "Road User Filter" if lang == "en" else "Tienkäyttäjä",
        list(user_options.keys()),
    )
    user_filter = user_options[selected_user_label]

    radius_m = st.slider(
        "Evaluation Radius (meters)" if lang == "en" else "Tarkastelusäde (metriä)",
        min_value=50,
        max_value=2000,
        value=250,
        step=50,
    )

    hotspots_df = get_municipality_hotspots(str(engine.db_path), selected_muni, winter_only, user_filter)
    if not hotspots_df.empty:
        hotspot_labels = [
            f"#{i + 1}: {row.crashes} crashes — {translate_accident_type(row.dominant_crash_type, lang)}"
            for i, row in enumerate(hotspots_df.itertuples())
        ]
        chosen_hs = st.selectbox(
            f"Top Hotspots in {selected_muni}" if lang == "en" else f"Riskikeskittymät: {selected_muni}",
            hotspot_labels,
        )
        if st.button("Jump to Hotspot" if lang == "en" else "Siirry keskittymään", use_container_width=True):
            hs_idx = hotspot_labels.index(chosen_hs)
            st.session_state.lat = float(hotspots_df.iloc[hs_idx]["lat"])
            st.session_state.lon = float(hotspots_df.iloc[hs_idx]["lon"])
            st.rerun()

    st.divider()
    st.header("3. Exact Coordinates" if lang == "en" else "3. Tarkat koordinaatit")
    manual_lat = st.number_input("Latitude", value=float(st.session_state.lat), format="%.5f")
    manual_lon = st.number_input("Longitude", value=float(st.session_state.lon), format="%.5f")
    if manual_lat != st.session_state.lat or manual_lon != st.session_state.lon:
        st.session_state.lat = manual_lat
        st.session_state.lon = manual_lon
        st.rerun()

st.title(
    "Finland Spatial Road Risk Explorer (2014–2025)"
    if lang == "en"
    else "Suomen tieliikenteen riskikartta (2014–2025)"
)

query = RiskQuery(
    lat=st.session_state.lat,
    lon=st.session_state.lon,
    radius_m=float(radius_m),
    winter_only=winter_only,
    road_user_filter=user_filter,
    lang=lang,
)
profile = engine.evaluate_point(query)

col1, col2, col3, col4 = st.columns(4)
col1.metric(
    "Normalized Risk Score" if lang == "en" else "Riskipisteet", f"{profile.normalized_risk_score} / 100"
)
col2.metric("Risk Tier" if lang == "en" else "Riskitaso", profile.risk_tier)
col3.metric(
    "Total Crashes in Radius" if lang == "en" else "Onnettomuudet säteellä", f"{profile.total_accidents:,}"
)
col4.metric(
    "Decayed Risk Index" if lang == "en" else "Aikapainotettu indeksi", f"{profile.decayed_risk_index}"
)

st.divider()

left_col, right_col = st.columns([3, 2])

with left_col:
    st.subheader(
        "Interactive Map (Click Anywhere to Evaluate Risk)"
        if lang == "en"
        else "Interaktiivinen kartta (klikkaa mitä tahansa pistettä)"
    )
    m = folium.Map(
        location=[st.session_state.lat, st.session_state.lon], zoom_start=14, tiles="OpenStreetMap"
    )

    folium.Marker(
        [st.session_state.lat, st.session_state.lon],
        tooltip="Evaluation Point" if lang == "en" else "Tarkastelupiste",
        icon=folium.Icon(color="black", icon="crosshairs", prefix="fa"),
    ).add_to(m)

    folium.Circle(
        location=[st.session_state.lat, st.session_state.lon],
        radius=radius_m,
        color="#2563eb",
        fill=True,
        fill_opacity=0.12,
    ).add_to(m)

    for inc in profile.nearest_incidents:
        popup_html = (
            f"<b>Year:</b> {inc.year} (Month {inc.month})<br>"
            f"<b>Severity:</b> {inc.severity}<br>"
            f"<b>Type:</b> {inc.accident_type}<br>"
            f"<b>Surface:</b> {inc.surface_condition} | <b>Speed:</b> {inc.speed_limit} km/h<br>"
            f"<b>Score:</b> {inc.weighted_score}"
        )
        folium.CircleMarker(
            location=[inc.lat, inc.lon],
            radius=6,
            color=severity_color(inc.severity),
            fill=True,
            fill_opacity=0.85,
            popup=folium.Popup(popup_html, max_width=300),
        ).add_to(m)

    map_state = st_folium(m, height=480, use_container_width=True, returned_objects=["last_clicked"])

    if map_state and map_state.get("last_clicked"):
        clicked_lat = round(float(map_state["last_clicked"]["lat"]), 5)
        clicked_lon = round(float(map_state["last_clicked"]["lng"]), 5)
        if clicked_lat != round(st.session_state.lat, 5) or clicked_lon != round(st.session_state.lon, 5):
            st.session_state.lat = clicked_lat
            st.session_state.lon = clicked_lon
            st.rerun()

with right_col:
    st.subheader("Environmental & Crash Breakdown" if lang == "en" else "Olosuhde- ja onnettomuusjakauma")
    if profile.severity_breakdown:
        st.write("**Severity Distribution**" if lang == "en" else "**Vakavuusjakauma**")
        st.bar_chart(pd.Series(profile.severity_breakdown))

    if profile.top_surface_conditions:
        st.write(
            "**Top Road Surface Conditions**" if lang == "en" else "**Yleisimmät tienpinnan olosuhteet**"
        )
        st.dataframe(
            pd.DataFrame(
                list(profile.top_surface_conditions.items()),
                columns=[
                    "Surface Condition" if lang == "en" else "Tienpinta",
                    "Count" if lang == "en" else "Lkm",
                ],
            ),
            hide_index=True,
            use_container_width=True,
        )

    if profile.top_accident_types:
        st.write("**Dominant Collision Mechanisms**" if lang == "en" else "**Yleisimmät onnettomuustyypit**")
        st.dataframe(
            pd.DataFrame(
                list(profile.top_accident_types.items()),
                columns=[
                    "Accident Type" if lang == "en" else "Onnettomuustyyppi",
                    "Count" if lang == "en" else "Lkm",
                ],
            ),
            hide_index=True,
            use_container_width=True,
        )

if profile.nearest_incidents:
    st.subheader(
        "Highest-Weighted Historical Incidents" if lang == "en" else "Riskipainotetuimmat onnettomuudet"
    )
    df_table = pd.DataFrame([inc.model_dump() for inc in profile.nearest_incidents])
    st.dataframe(
        df_table[
            [
                "year",
                "month",
                "severity",
                "surface_condition",
                "lighting",
                "speed_limit",
                "accident_type",
                "distance_m",
                "weighted_score",
            ]
        ],
        hide_index=True,
        use_container_width=True,
    )
