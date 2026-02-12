import streamlit as st
import geopandas as gpd
import datetime

# import farms vector file as a gdf

def get_farms_gdf():
    farms_gdf = gpd.read_file(r"data/vector/ce_farms.gpkg")
    farms_gdf = farms_gdf[['farmer','Classifica', 'crop','variety','model', 'district', 'province', 'area_hectares', 'geometry', 'year']]
    return farms_gdf


def get_sh_farms():
    gdf = gpd.read_file(r"data/vector/field_measure_farms.gpkg")
    # gdf = gdf[:500]
    # gdf = gdf[['farmer_id', 'camp', 'pea', 'hub', 'fs', 'district', 'region','geometry']]
    gdf['lon'] = gdf.geometry.x
    gdf['lat'] = gdf.geometry.y

    return gdf

def get_pea_locations():
    gdf5 = gpd.read_file(r"data/vector/Pea_locations.gpkg")
    return gdf5

def get_fs_catchment_boundaries():
    gdf6 = gpd.read_file(r"data/vector/fs_catchment_boundaries.gpkg")
    return gdf6

def get_zambia_boundaries():
    gdf7 = gpd.read_file(r"data/vector/zambia_aoi.gpkg")
    return gdf7

def get_foundation_farm_boundaries():
    gdf2 = gpd.read_file(r"data/vector/Foundation_Farm_Boundary.gpkg")
    return gdf2

def get_buildings():
    gdf3 = gpd.read_file(r"data/vector/Buildings_2.gpkg")
    return gdf3

def get_Crop_blocks():
    gdf4 = gpd.read_file(r"data/vector/Crop_Blocks.gpkg")
    return gdf4

def available_crop_health_metrics():
    health_metrics = ['Crop Health', 'Crop Moisture', ]
    return health_metrics

def farm_names_list():
    farms_gdf = get_farms_gdf()
    # List of farms
    farm_names = sorted(list(set(farms_gdf["farmer"].to_list())))
    return farm_names

def farm_years_list():
    farms_gdf = get_farms_gdf()
    # List of years
    farm_years = sorted(list(set(farms_gdf["year"].to_list())))
    return farm_years

def add_selectors_crop_health(backtrack_days=7):
    farm_names = farm_names_list()
    farm_years = farm_years_list()

    # crop health metrics
    indices_list = available_crop_health_metrics()

    # specify columns and their widths
    year_col, farm_names_col, indices_list_col, start_date_col, end_date_col, max_cloud_cover_col = st.columns([2.2,3, 3, 2, 2, 2.5])
    with year_col:
        selected_year = st.selectbox(
            "Select year",
            farm_years,
            index=None,
            placeholder="Select year...",
            key=0
        )

    with farm_names_col:
        farms_gdf = get_farms_gdf()

        if selected_year is not None:
            farms_filtered = farms_gdf[farms_gdf["year"] == selected_year]
            farm_names_for_year = sorted(farms_filtered["farmer"].unique().tolist())

            if not farm_names_for_year:
                farm_names_for_year = farm_names
        else:
            farm_names_for_year = farm_names

        selected_farm_name = st.selectbox(
            "Select the farm to monitor",
            farm_names_for_year,
            index=None,
            placeholder="Select farm...",
            key=1
        )

    with indices_list_col:
        selected_index = st.selectbox(
            "Select the metric to monitor",
            indices_list,
            index=None,
            placeholder="Select metric...",
            key=2
        )

    with start_date_col:
        selected_start_date = str(st.date_input(
            "Select start date",
            datetime.date.today() - datetime.timedelta(days=backtrack_days),
            key=3
        ))

    with end_date_col:
        selected_end_date = str(st.date_input(
            "Select end date",
            datetime.date.today(),
            key=4
        ))

    with max_cloud_cover_col:
        # max_cloud_cover = st.text_input('Select maximum cloud cover',
                                    # 0, 100, 20, step=5)
        max_cloud_cover = st.slider(
            'Select maximum cloud cover',
            min_value =0,
            max_value=100, 
            value= 20,
            step=5,
            key=5
            )

    return selected_year, selected_farm_name, selected_index, selected_start_date, selected_end_date, max_cloud_cover

def add_selectors_crop_monitor(backtrack_days=7):
    farm_names = farm_names_list()
    farm_years=farm_years_list()

    # crop health metrics
    indices_list = available_crop_health_metrics()

    # specify columns and their widths
    year_col, farm_names_col, indices_list_col, start_date_col, end_date_col, max_cloud_cover_col = st.columns([2.2,3, 3, 2, 2, 2.5])
    with year_col:
        selected_year = st.selectbox(
            "Select year",
            farm_years,
            index=None,
            placeholder="Select year...",
            key=9
        )

    # with farm_names_col:
    #     selected_farm_name = st.selectbox(
    #         "Select the farm to monitor",
    #         farm_names,
    #         index=None,
    #         placeholder="Select farm...",
    #         key=10
    #     )

        with farm_names_col:
            # filter farms by the selected year and show only those farm names
            farms_gdf = get_farms_gdf()
            farms_filtered = farms_gdf[farms_gdf["year"] == selected_year]
            farm_names_for_year = sorted(farms_filtered["farmer"].unique().tolist())

            # fallback to all farms if no farm found for the year
            if not farm_names_for_year:
                farm_names_for_year = farm_names

            selected_farm_name = st.selectbox(
            "Select the farm to monitor",
            farm_names_for_year,
            index=None,
            placeholder="Select farm...",
            key=10
            )

    with indices_list_col:
        selected_index = st.selectbox(
            "Select the metric to monitor",
            indices_list,
            index=None,
            placeholder="Select metric...",
            key=11
        )

    with start_date_col:
        selected_start_date = str(st.date_input(
            "Select start date",
            datetime.date.today() - datetime.timedelta(days=backtrack_days),
            key=12
        ))

    with end_date_col:
        selected_end_date = str(st.date_input(
            "Select end date",
            datetime.date.today(),
            key=13
        ))

    with max_cloud_cover_col:
        # max_cloud_cover = st.text_input('Select maximum cloud cover',
                                    # 0, 100, 20, step=5)
        max_cloud_cover = st.slider(
            'Select maximum cloud cover',
            0, 100, 20, step=5,
            key=14
            )

    return selected_year, selected_farm_name, selected_index, selected_start_date, selected_end_date, max_cloud_cover
