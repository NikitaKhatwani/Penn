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
    [31,119,180,200],[255,127,14,200],[44,160,44,200],[214,39,40,200],
    [148,103,189,200],[140,86,75,200],[227,119,194,200],[127,127,127,200],
    [188,189,34,200],[23,190,207,200],
]

# =============================
# HELPERS
# =============================
def build_program_color_map(program_list):
    return {
        prog: DISTINCT_COLORS[i % len(DISTINCT_COLORS)]
        for i, prog in enumerate(sorted(program_list))
    }

def normalize_priority(val):
    if pd.isna(val): return False
    if isinstance(val, bool): return val
    if isinstance(val, (int,float)): return val != 0
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
df["precinct"] = df_raw.get("Precinct", None)
df["proposed_status"] = df_raw["Proposed_Status"].fillna("None")

# =============================
# SIDEBAR
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

    # show_precinct_overlay = st.checkbox("Show precinct circles", False)
    show_precinct_labels = st.checkbox("Show precinct labels", False)

    st.divider()

    all_programs = sorted(df["program"].unique())
    selected_programs = st.multiselect("Program Types to show", all_programs, default=all_programs)

    # precinct filter (NO default → so all buildings show initially)
    all_precincts = sorted(df["precinct"].dropna().unique())
    selected_precincts = st.multiselect("Precincts", all_precincts)

    # proposed status
    all_status = sorted(df["proposed_status"].unique())
    selected_status = st.multiselect("Proposed Status", all_status, default=all_status)

# =============================
# FILTER (FIXED)
# =============================
df_view = df.copy()

df_view = df_view[df_view["program"].isin(selected_programs)]

if len(selected_precincts) > 0:
    df_view = df_view[df_view["precinct"].isin(selected_precincts)]

df_view = df_view[df_view["proposed_status"].isin(selected_status)]

if show_only_priority:
    df_view = df_view[df_view["priority"]]

if df_view.empty:
    st.warning("No buildings match current filters.")
    st.stop()

# =============================
# COLORING
# =============================
if color_by_program:
    cmap = build_program_color_map(df["program"].unique())
    df_view["base_color"] = df_view["program"].map(cmap)
else:
    df_view["base_color"] = [DEFAULT_BLUE]*len(df_view)

if highlight_priority:
    df_view["color"] = df_view.apply(
        lambda r: MAROON if r["priority"] else r["base_color"], axis=1
    )
else:
    df_view["color"] = df_view["base_color"]

# =============================
# PRECINCT CIRCLES (FIXED)
# =============================
precinct_summary = None

# if show_precinct_overlay:

#     valid_df = df.copy()

#     if len(selected_precincts) > 0:
#         valid_df = valid_df[valid_df["precinct"].isin(selected_precincts)]

#     valid_df = valid_df[valid_df["proposed_status"].isin(selected_status)]

#     if not valid_df.empty:

#         precinct_summary = (
#             valid_df.groupby("precinct")
#             .agg(
#                 center_lat=("lat","mean"),
#                 center_lon=("lon","mean"),
#                 lat_min=("lat","min"),
#                 lat_max=("lat","max"),
#                 lon_min=("lon","min"),
#                 lon_max=("lon","max"),
#                 count=("lat","count")
#             )
#             .reset_index()
#         )

#         # convert spans to meters
#         lat_span = (precinct_summary["lat_max"] - precinct_summary["lat_min"]) * 111000
#         lon_span = (precinct_summary["lon_max"] - precinct_summary["lon_min"]) * 85000

#         # radius = half diagonal
#         precinct_summary["radius"] = ((lat_span**2 + lon_span**2) ** 0.5) / 2

#         # small padding
#         precinct_summary["radius"] = precinct_summary["radius"] * 1.1

#         precinct_summary["label"] = precinct_summary.apply(
#             lambda r: f"{r['precinct']}\n{r['count']} buildings",
#             axis=1
#         )

# =============================
# MAP LAYERS
# =============================
layers = []

layers.append(pdk.Layer(
    "ScatterplotLayer",
    data=df_view,
    get_position="[lon, lat]",
    get_fill_color="color",
    get_radius=25,
    pickable=True,
))

# labels
if show_labels or show_priority_labels_only:

    label_df = df_view[df_view["priority"]] if show_priority_labels_only else df_view

    layers.append(pdk.Layer(
        "TextLayer",
        data=label_df,
        get_position="[lon, lat]",
        get_text="name",
        get_size=13,
        get_color=[0,0,0,220],
        get_pixel_offset=[0,-18],
    ))

# precinct circles
if precinct_summary is not None:

    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=precinct_summary,
        get_position="[center_lon, center_lat]",
        get_radius="radius",
        get_fill_color=[200,0,0,60],
        stroked=True,
    ))

    if show_precinct_labels:
        layers.append(pdk.Layer(
            "TextLayer",
            data=precinct_summary,
            get_position="[center_lon, center_lat]",
            get_text="label",
            get_size=16,
            get_color=[60,0,0,230],
        ))

# =============================
# MAP VIEW
# =============================
if "initialized" not in st.session_state:

    st.session_state.initial_view = pdk.ViewState(
        latitude=float(df["lat"].mean()),
        longitude=float(df["lon"].mean()),
        zoom=14,
        bearing=-55
    )

    st.session_state.initialized = True

deck = pdk.Deck(
    layers=layers,
    initial_view_state=st.session_state.initial_view,
    tooltip={
        "html": "<b>{name}</b><br/>Precinct: {precinct}<br/>Proposed: {proposed_status}"
    },
    map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
)

st.pydeck_chart(deck, use_container_width=True, height=750)

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
