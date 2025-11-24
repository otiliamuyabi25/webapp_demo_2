import streamlit as st
import folium
from folium.plugins import MarkerCluster, MeasureControl
import xyzservices.providers as xyz
from streamlit_folium import folium_static
import geopandas as gpd
import pandas as pd
import leafmap.foliumap as leafmap
from apps import sh_functions, variables

st.set_page_config(layout="wide")
def app():
    """This function adds the app that dispace the pea lovation and fs catchment boundaries
    """
    st.title("Hub Definition Management")
    # st.header('Hub Definition Management')
    # Define tabs for app
    hub_definition_tab = st.tabs(
        ["Hub Definition"]
        )

        # Start of hub definition tab
    with hub_definition_tab[0]:
            st.header("View latest hub definition") # Tab header
    # define GIS layers
    gdf5 = variables.get_pea_locations()
    gdf6 = variables.get_fs_catchment_boundaries()
    gdf7 = variables.get_zambia_boundaries()

    # --------------------------
    # Step 1: Load GIS layers
    # --------------------------
    pea_locations = gdf5
    fs_catchment_boundaries = gdf6
    zambia_boundaries = gdf7


# Set CRS for each GeoDataFrame (assuming WGS84)
    pea_locations.crs = "EPSG:4326"
    fs_catchment_boundaries.crs = "EPSG:4326"
    zambia_boundaries.crs = "EPSG:4326"

# Step 4: Create five columns for filters
# # --------------------------

    col1, col2 ,col3 ,col4 = st.columns(4)

    with col1:
        region_options = ["All"] + sorted(fs_catchment_boundaries["FE Region"].unique())
        selected_region = st.selectbox("Select Region", region_options)
    with col2:
        if selected_region != "All":
            filtered_hubs = fs_catchment_boundaries[fs_catchment_boundaries["FE Region"] == selected_region]
            hub_options = ["All"] + sorted(filtered_hubs["Hub Name"].unique())
        else:
            hub_options = ["All"] + sorted(fs_catchment_boundaries["Hub Name"].unique())
        selected_hub = st.selectbox("Select Hub", hub_options)
    with col3:
        if selected_hub != "All":
            filtered_fs_catchments = fs_catchment_boundaries[fs_catchment_boundaries["Hub Name"] == selected_hub]
            fs_catchment_options = ["All"] + sorted(filtered_fs_catchments["Name"].unique())
        else:
            fs_catchment_options = ["All"] + sorted(fs_catchment_boundaries["Name"].unique())
        selected_fs_catchment = st.selectbox("Select FS Catchment", fs_catchment_options)
    with col4:
        # Basemap selection
        basemap_options = {
            "OpenStreetMap": "OpenStreetMap",
            "Google Satellite": "SATELLITE",
            "Google Hybrid": "HYBRID",
            "CartoDB Dark": "CartoDB.DarkMatter",
        }
        selected_basemap = st.selectbox("Select Basemap", list(basemap_options.keys()))

    # Step 5: Filter history
# --------------------------
    filtered_fs_catchment_area = fs_catchment_boundaries.copy()
    if selected_region != "All":
        filtered_fs_catchment_area = filtered_fs_catchment_area[filtered_fs_catchment_area["FE Region"] == selected_region]
    if selected_hub != "All":
        filtered_fs_catchment_area = filtered_fs_catchment_area[filtered_fs_catchment_area["Hub Name"] == selected_hub]
    if selected_fs_catchment != "All":
        filtered_fs_catchment_area = filtered_fs_catchment_area[filtered_fs_catchment_area["Name"] == selected_fs_catchment]

# Step 6: Function to create the map
# --------------------------
    def create_map(basemap):
        m = leafmap.Map(locate_control=True, draw_control=True)

        m.add_basemap(basemap)
        # Add Zambia Boundaries Layer
        zambia_boundaries_layer = folium.FeatureGroup(name="Zambia Boundaries").add_to(m)
        for _, z_row in zambia_boundaries.iterrows():
            folium.GeoJson(
                z_row['geometry'],
                style_function=lambda x: {
                    "color": "black",
                    "weight": 1,
                    "fillOpacity": 0
                },
                tooltip=f"<b>Country:</b> {z_row['country']}"
            ).add_to(zambia_boundaries_layer)

        # Add fs catchment Layer
        fs_catchment_boundaries_layer = folium.FeatureGroup(name="Catchments").add_to(m)
        for _, f_row in filtered_fs_catchment_area.iterrows():
            folium.GeoJson(
                f_row['geometry'],
                style_function=lambda x: {
                    "color": "blue",
                    "weight": 2,
                    "fillOpacity": 0
                },
                tooltip=f"<b>Catchment:</b> {f_row['Name']}<br>"
                        f"<b>Hub:</b> {f_row['Hub Name']}<br>"
                        f"<b>Region:</b> {f_row['FE Region']}<br>"
                        f"<b>FS:</b> {f_row['FS']}<br>"
                        f"<b>RM:</b> {f_row['RM']}"
            ).add_to(fs_catchment_boundaries_layer)

        # # Add Pea Locations Layer
        # pea_locations_layer = folium.FeatureGroup(name="Pea_locations").add_to(m)
        # for _, b_row in pea_locations.iterrows():
        #     folium.GeoJson(
        #         b_row['geometry'],
        #         style_function=lambda x: {
        #             "color": "blue",
        #             "weight": 1,
        #             "fillOpacity": 0.2
        #         },
        #         tooltip=f"<b>Pea:</b> {b_row['pea']}<br>"
        #                 f"<b>FS:</b> {b_row['fs']}<br>"
        #                 f"<b>Hub:</b> {b_row['hub']}<br>"
        #                 f"<b>Region:</b> {b_row['region']}"
        #     ).add_to(pea_locations_layer)

        # Add Pea Locations as Markers
        pea_locations_layer = folium.FeatureGroup(name="Pea Locations").add_to(m)
        for _, p_row in pea_locations.iterrows():
            folium.CircleMarker(
                location=[p_row.geometry.y, p_row.geometry.x],
                radius=1 ,
                color="green",
                fill=True,
                fill_color="green",
                fill_opacity=2,
                tooltip=f"<b>Pea:</b> {p_row['pea']}<br>"
                        f"<b>FS:</b> {p_row['fs']}<br>"
                        f"<b>Hub:</b> {p_row['hub']}<br>"
                        f"<b>Region:</b> {p_row['region']}"
            ).add_to(pea_locations_layer)

        return m

# --------------------------
# Step 7: Create and display the map
# --------------------------
    m = create_map(basemap_options[selected_basemap])
# zooming to bounds of filtered catchment areas
    if not filtered_fs_catchment_area.empty:
        bounds = filtered_fs_catchment_area.total_bounds  # [minx, miny, maxx, maxy]
        m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    else:
        bounds = zambia_boundaries.total_bounds  # [minx, miny, maxx, maxy]
        m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    
    m.to_streamlit(width=1200, height=500)