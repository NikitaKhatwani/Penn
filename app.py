import math
import pandas as pd
import streamlit as st
import pydeck as pdk

st.set_page_config(page_title="Penn State Campus Map", layout="wide")

# =============================
# CONSTANTS
# =============================
MAROON = [128, 0, 32, 230]
DEFAULT_BLUE = [30, 144, 255, 180]
UNKNOWN_PROGRAM = "Program type unknown"
DATA_PATH = "NBBJ_Buildings_.xlsx"

DISTINCT_COLORS = [
    [31,119,180,200],    # blue
    [255,127,14,200],    # orange
    [44,160,44,200],     # green
    [214,39,40,200],     # red
    [148,103,189,200],   # purple
    [140,86,75,200],     # brown
    [227,119,194,200],   # pink
    [127,127,127,200],   # gray
    [188,189,34,200],    # olive
    [23,190,207,200],    # cyan

    [255,0,0,200],       # bright red
    [0,128,255,200],     # strong blue
    [0,200,0,200],       # bright green
    [255,140,0,200],     # dark orange
    [128,0,128,200],     # deep purple
    [0,150,150,200],     # teal
    [200,0,150,200],     # magenta
    [100,100,0,200],     # dark olive
    [0,0,0,200],         # black
    [255,105,180,200],   # hot pink
]
# =============================
# HELPERS
# =============================
def build_program_color_map(program_list):
    return {
        prog: DISTINCT_COLORS[i % len(DISTINCT_COLORS)]
        for i, prog in enumerate(sorted(program_list))
    }

def compute_zoom(lat_series, lon_series):
    lat_range = float(lat_series.max() - lat_series.min())
    lon_range = float(lon_series.max() - lon_series.min())
    span = max(lat_range, lon_range)
    if not math.isfinite(span) or span <= 0:
        return 15
    zoom = 13 - math.log(span + 1e-6, 2)
    return float(max(3, min(17, zoom)))

def normalize_priority(val):
    if pd.isna(val):
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int,float)):
        return val != 0
    return str(val).strip().lower() in {"true","1","yes","y"}

# =============================
# LOAD DATA
# =============================
@st.cache_data
def load_data():
    df = pd.read_excel(DATA_PATH)
    df.columns = df.columns.str.strip()
    return df

df_raw = load_data()

df = pd.DataFrame()
df["name"] = df_raw["BLDG_NAME"].astype(str)
df["lat"] = pd.to_numeric(df_raw["Latitude"], errors="coerce")
df["lon"] = pd.to_numeric(df_raw["Longitude"], errors="coerce")

df = df.dropna(subset=["lat","lon"]).reset_index(drop=True)

if df.empty:
    st.error("No valid coordinates found.")
    st.stop()

df["program"] = df_raw.get("Program Type", UNKNOWN_PROGRAM).fillna(UNKNOWN_PROGRAM)
df["priority"] = df_raw.get("EUI > Median EUI", False).apply(normalize_priority)

if "Precinct" in df_raw.columns:
    df["precinct"] = df_raw["Precinct"]
else:
    df["precinct"] = None

if "Energy (MMBtu)" in df_raw.columns:
    df["energy"] = pd.to_numeric(df_raw["Energy (MMBtu)"], errors="coerce").fillna(0)
else:
    df["energy"] = 0

# =============================
# SIDEBAR CONTROLS
# =============================
st.title("Penn State Campus Map")

with st.sidebar:

    color_by_program = st.checkbox("Color buildings by Program Type", True)
    highlight_priority = st.checkbox("Highlight priority buildings (maroon)", True)

    st.divider()

    show_only_priority = st.checkbox("Show ONLY priority buildings", False)

    st.divider()

    show_labels = st.checkbox("Show building names", False)
    show_priority_labels_only = st.checkbox("Show ONLY priority building names", False)

    st.divider()

    show_precinct_overlay = st.checkbox("Show precinct circles", False)
    show_precinct_labels = st.checkbox("Show precinct labels", False)
    st.divider()

    all_programs = sorted(df["program"].unique())
    selected_programs = st.multiselect(
        "Program Types to show",
        all_programs,
        default=all_programs
    )




# =============================
# FILTER BUILDINGS
# =============================
df_view = df[df["program"].isin(selected_programs)].copy()

if show_only_priority:
    df_view = df_view[df_view["priority"]]

if df_view.empty:
    st.warning("No buildings match current filters.")
    st.stop()


# =============================
# COLORING
# =============================
if color_by_program:
    program_color_map = build_program_color_map(df["program"].unique())
    df_view["base_color"] = df_view["program"].map(program_color_map)
else:
    df_view["base_color"] = [DEFAULT_BLUE]*len(df_view)

if highlight_priority:
    df_view["color"] = df_view.apply(
        lambda r: MAROON if r["priority"] else r["base_color"], axis=1
    )
else:
    df_view["color"] = df_view["base_color"]

# =============================
# PRECINCT AGGREGATION
# =============================
precinct_summary = None

if show_precinct_overlay:

    valid_precinct_df = df.dropna(subset=["precinct"])

    if not valid_precinct_df.empty:

        precinct_summary = (
            valid_precinct_df.groupby("precinct", as_index=False)
                              .agg(
                                  center_lat=("lat","mean"),
                                  center_lon=("lon","mean"),
                                  total_energy=("energy","sum")
                              )
        )

        precinct_summary = precinct_summary.dropna(
            subset=["center_lat","center_lon"]
        )

        if not precinct_summary.empty:

            max_energy = precinct_summary["total_energy"].max()
            if max_energy == 0:
                max_energy = 1

            precinct_summary["radius"] = (
                precinct_summary["total_energy"] / max_energy
            ) * 400

            precinct_summary["label"] = precinct_summary.apply(
            lambda r: f"{r['precinct']}\n{r['total_energy']:,.0f} MMBtu",
            axis=1
        )

            # Add placeholder fields so tooltip works cleanly
            precinct_summary["name"] = None
            precinct_summary["program"] = None
            precinct_summary["priority"] = None

# =============================
# MAP LAYERS
# =============================
layers = []

scatter_layer = pdk.Layer(
    "ScatterplotLayer",
    data=df_view,
    get_position="[lon, lat]",
    get_fill_color="color",
    get_radius=25,
    pickable=True,
)

layers.append(scatter_layer)

if show_labels or show_priority_labels_only:

    label_df = df_view[df_view["priority"]] if show_priority_labels_only else df_view

    text_layer = pdk.Layer(
        "TextLayer",
        data=label_df,
        get_position="[lon, lat]",
        get_text="name",
        get_size=13,
        size_units="pixels",
        get_color=[0,0,0,220],
        get_text_anchor="'middle'",
        get_alignment_baseline="'bottom'",
        get_pixel_offset=[0,-18],
    )

    layers.append(text_layer)



if precinct_summary is not None and not precinct_summary.empty:

    # --- Circles (always shown if overlay enabled) ---
    precinct_layer = pdk.Layer(
        "ScatterplotLayer",
        data=precinct_summary,
        get_position="[center_lon, center_lat]",
        get_radius="radius",
        get_fill_color=[200,0,0,60],  # lighter transparency
        get_line_color=[150,0,0],
        stroked=True,
        filled=True,
        pickable=True,
    )

    layers.append(precinct_layer)

    # --- Labels (only when checkbox enabled) ---
    if show_precinct_labels:

        precinct_text_layer = pdk.Layer(
            "TextLayer",
            data=precinct_summary,
            get_position="[center_lon, center_lat]",
            get_text="label",
            get_size=16,
            size_units="pixels",
            get_color=[60, 0, 0, 230],
            get_text_anchor="'middle'",
            get_alignment_baseline="'center'",
            pickable=False,
        )

        layers.append(precinct_text_layer)



# =============================
# MAP VIEW
# =============================
# center_lat = float(df["lat"].mean())
# center_lon = float(df["lon"].mean())
# zoom = compute_zoom(df["lat"], df["lon"])

# view_state = pdk.ViewState(
#     latitude=center_lat,
#     longitude=center_lon,
#     zoom=zoom,
#     bearing=-55
# )

# tooltip = {
#     "html": """
#     <b>{name}</b><br/>
#     Program: {program}<br/>
#     Priority: {priority}<br/>
#     <hr/>
#     <b>Precinct:</b> {precinct}<br/>
#     <b>Total Energy:</b> {total_energy}
#     """,
#     "style": {
#         "backgroundColor": "white",
#         "color": "black"
#     }
# }

# deck = pdk.Deck(
#     layers=layers,
#     initial_view_state=view_state,
#     tooltip=tooltip,
#     map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
# )

# st.pydeck_chart(deck, use_container_width=True, height=750)





# =============================
# MAP VIEW (STABLE + NO RESET)
# =============================


# =============================
# MAP VIEW (TRUE STABLE VERSION)
# =============================

if "initialized" not in st.session_state:

    center_lat = float(df["lat"].mean())
    center_lon = float(df["lon"].mean())
    # zoom = compute_zoom(df["lat"], df["lon"])
    zoom = 14

    st.session_state.initial_view = pdk.ViewState(
        latitude=center_lat,
        longitude=center_lon,
        zoom=zoom,
        bearing=-55
    )

    st.session_state.initialized = True



tooltip = {
    "html": """
    <b>{name}</b><br/>
    Program: {program}<br/>
    Priority: {priority}<br/>
    <hr/>
    <b>Precinct:</b> {precinct}<br/>
    <!-- <b>Total Energy:</b> {total_energy} -->
    """,
    "style": {
        "backgroundColor": "white",
        "color": "black"
    }
}



# Only use initial_view_state once
deck = pdk.Deck(
    layers=layers,
    initial_view_state=st.session_state.initial_view,
    tooltip=tooltip,
    map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
)

st.pydeck_chart(deck, use_container_width=True, height=750)

# # 🔥 Immediately delete it so reruns don't reset
# st.session_state.initial_view = None
# =============================
# PROGRAM TYPE LEGEND
# =============================
if color_by_program:

    st.divider()
    st.subheader("Legend – Program Type")

    program_color_map = build_program_color_map(df["program"].unique())

    # Only show legend items for currently visible programs
    visible_programs = sorted(df_view["program"].unique())

    for prog in visible_programs:

        color = program_color_map[prog]
        hex_color = "#{:02x}{:02x}{:02x}".format(
            color[0], color[1], color[2]
        )

        st.markdown(
            f"""
            <div style="display: flex; align-items: center; margin-bottom: 6px;">
                <div style="
                    width: 14px;
                    height: 14px;
                    background-color: {hex_color};
                    border-radius: 3px;
                    margin-right: 8px;
                    border: 1px solid #999;">
                </div>
                <div style="font-size: 13px;">
                    {prog}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    if highlight_priority:
        st.markdown("---")
        maroon_hex = "#{:02x}{:02x}{:02x}".format(
            MAROON[0], MAROON[1], MAROON[2]
        )

        st.markdown(
            f"""
            <div style="display: flex; align-items: center;">
                <div style="
                    width: 14px;
                    height: 14px;
                    background-color: {maroon_hex};
                    border-radius: 3px;
                    margin-right: 8px;
                    border: 1px solid #999;">
                </div>
                <div style="font-size: 13px;">
                    Priority (EUI > Median)
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )