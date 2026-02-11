import datetime
import streamlit as st
import geopandas as gpd
import geemap.foliumap as geemap
from folium.plugins import MeasureControl
import folium
import ee
import pandas as pd

from apps import ee_functions, variables


# Folium/streamlit JSON serialization helpers
def _folium_safe_gdf(gdf: gpd.GeoDataFrame, keep_cols=None) -> gpd.GeoDataFrame:
    """
    Folium serializes GeoJSON via json.dumps; pandas Timestamps (and some other
    objects) are not JSON-serializable by default. This helper keeps only a
    small set of columns and converts non-geometry values to strings.
    """
    if gdf is None:
        return gdf

    safe = gdf.copy()

    if keep_cols is not None:
        cols = [c for c in keep_cols if c in safe.columns]
        if "geometry" in safe.columns and "geometry" not in cols:
            cols.append("geometry")
        safe = safe[cols] if cols else safe[["geometry"]]

    for col in list(safe.columns):
        if col == "geometry":
            continue
        # Convert everything else to string to guarantee JSON serializable props
        # (including pandas Timestamp, datetime, UUIDs, etc.)
        safe[col] = safe[col].apply(lambda v: None if pd.isna(v) else str(v))

    return safe


def _first_existing_col(gdf: gpd.GeoDataFrame, candidates) -> str | None:
    """Case-insensitive column match; returns actual column name or None."""
    if gdf is None or gdf.empty:
        return None
    lower_map = {str(c).lower(): c for c in gdf.columns}
    for cand in candidates:
        key = str(cand).lower()
        if key in lower_map:
            return lower_map[key]
    return None


def _infer_farmer_id_and_name_cols(gdf: gpd.GeoDataFrame) -> tuple[str | None, str | None]:
    """
    Best-effort inference for smallholder layer attribute columns.
    Returns (farmer_id_col, farmer_name_col).
    """
    farmer_id_col = _first_existing_col(
        gdf,
        [
            "farmer_id",
            "farmerid",
            "farmer id",
            "fid",
            "id",
            "uuid",
            "farmer_no",
            "farmer number",
        ],
    )
    farmer_name_col = _first_existing_col(
        gdf,
        [
            "farmer_name",
            "farmername",
            "farmer name",
            "name",
            "farmer",
            "full_name",
            "fullname",
        ],
    )
    return farmer_id_col, farmer_name_col


def _add_smallholder_circle_layer(m, gdf: gpd.GeoDataFrame) -> None:
    """
    Add smallholder farmer locations as filled circle markers with a tooltip.
    """
    if gdf is None or gdf.empty:
        return

    farmer_id_col, farmer_name_col = _infer_farmer_id_and_name_cols(gdf)

    # If geometries are polygons/lines, fall back to centroids for point display.
    geom_types = set(map(str, gdf.geom_type.unique().tolist()))
    point_types = {"Point", "MultiPoint"}
    gdf_points = gdf
    if not geom_types.issubset(point_types):
        try:
            tmp = gdf.copy()
            tmp_3857 = tmp.to_crs(epsg=3857)
            tmp_3857["geometry"] = tmp_3857.geometry.centroid
            gdf_points = tmp_3857.to_crs(gdf.crs)
        except Exception:
            gdf_points = gdf

    # Keep only what we need; stringify attributes to avoid JSON issues.
    keep_cols = [c for c in [farmer_id_col, farmer_name_col, "geometry"] if c is not None]
    safe = _folium_safe_gdf(gdf_points, keep_cols)

    fg = folium.FeatureGroup(name="Farmer Fields", show=True)

    for _, row in safe.iterrows():
        geom = row.get("geometry", None)
        if geom is None or geom.is_empty:
            continue
        # Works for Points; if we got MultiPoint, use its representative point.
        try:
            pt = geom if geom.geom_type == "Point" else geom.representative_point()
            lat, lon = float(pt.y), float(pt.x)
        except Exception:
            continue

        farmer_id_val = str(row.get(farmer_id_col, "")).strip() if farmer_id_col else ""
        farmer_name_val = str(row.get(farmer_name_col, "")).strip() if farmer_name_col else ""

        tooltip_lines = []
        if farmer_id_val and farmer_id_val.lower() != "nan":
            tooltip_lines.append(f"Farmer ID: {farmer_id_val}")
        if farmer_name_val and farmer_name_val.lower() != "nan":
            tooltip_lines.append(f"Farmer Name: {farmer_name_val}")
        tooltip_text = "<br>".join(tooltip_lines) if tooltip_lines else "Farmer"

        folium.CircleMarker(
            location=(lat, lon),
            radius=4,
            color="#2b8cbe",
            weight=1,
            fill=True,
            fill_color="#2b8cbe",
            fill_opacity=0.8,
            tooltip=folium.Tooltip(tooltip_text, sticky=False),
        ).add_to(fg)

    fg.add_to(m)


# Load FS catchment boundaries
def _load_fs_catchments() -> gpd.GeoDataFrame:
    gdf = variables.get_fs_catchment_boundaries()
    # Keep only geometry + id/name columns if obvious
    return gdf


def _get_name_column(gdf: gpd.GeoDataFrame) -> str:
    """
    Try to infer the column that identifies FS catchments.
    Falls back to the first non-geometry column if nothing matches.
    """
    # Prefer human-readable catchment name over IDs.
    # Explicitly prioritise "Name" (your FS catchment name field),
    # then other name-like columns, and only then ID-style fields.
    candidate_cols = [
        "Name",
        "name",
        "fs_name",
        "FS_NAME",
        "catchment",
        "Catchment",
        "fs",
        "FS",
    ]

    for col in candidate_cols:
        if col in gdf.columns:
            return col

    # Fallback: first non-geometry column
    non_geom_cols = [c for c in gdf.columns if c.lower() != "geometry"]
    return non_geom_cols[0] if non_geom_cols else gdf.columns[0]


fs_gdf = _load_fs_catchments()

# Ensure FS catchments have a CRS (assume WGS84 if missing)
if fs_gdf.crs is None:
    fs_gdf.set_crs(epsg=4326, inplace=True)

FS_NAME_COL = _get_name_column(fs_gdf)

# Load smallholder fields once and keep in memory
try:
    sh_gdf = variables.get_sh_farms()
    # Ensure smallholder layer has a CRS (assume WGS84 if missing)
    if sh_gdf.crs is None:
        sh_gdf.set_crs(epsg=4326, inplace=True)
except Exception:
    sh_gdf = None


def app():
    """FS catchment crop health / moisture viewer using Sentinel‑2 imagery."""

    st.header("FS Catchment Crop Health")

    indices_list = variables.available_crop_health_metrics()

    # Selector layout: FS catchment, metric, date range, cloud cover, image date
    fs_col, index_col, start_date_col, end_date_col, cloud_col, date_col = st.columns(
        [1.7, 1.7, 1.5, 1.5, 1.5, 2.0]
    )

    with fs_col:
        catchment_names = (
            fs_gdf[FS_NAME_COL]
            .astype(str)
            .sort_values()
            .unique()
            .tolist()
        )
        selected_fs_name = st.selectbox(
            "Select FS catchment",
            catchment_names,
            index=None,
            placeholder="Select FS catchment...",
            key="fs_catchment_name",
        )

    with index_col:
        selected_index = st.selectbox(
            "Select the metric to monitor",
            indices_list,
            index=None,
            placeholder="Select metric...",
            key="fs_metric",
        )

    today = datetime.date.today()
    with start_date_col:
        selected_start_date = str(
            st.date_input(
                "Select start date",
                today - datetime.timedelta(days=7),
                key="fs_start_date",
            )
        )

    with end_date_col:
        selected_end_date = str(
            st.date_input(
                "Select end date",
                today,
                key="fs_end_date",
            )
        )

    with cloud_col:
        max_cloud_cover = st.slider(
            "Select maximum cloud cover",
            min_value=0,
            max_value=100,
            value=20,
            step=5,
            key="fs_cloud_cover",
        )

    selected_available_image_date = None

    # Helper: get selected catchment GeoDataFrame
    def get_selected_catchment_gdf():
        if selected_fs_name is None:
            return None
        filtered = fs_gdf[fs_gdf[FS_NAME_COL].astype(str) == str(selected_fs_name)]
        return filtered if not filtered.empty else None

    selected_fs_gdf = get_selected_catchment_gdf()

    with st.spinner(
        f"Getting available images for {selected_fs_name}...",
        show_time=True,
    ):
        with date_col:
            if selected_fs_name is None:
                selected_available_image_date = st.selectbox(
                    "Select image date",
                    ["Select FS catchment"],
                    index=None,
                    placeholder="Select date...",
                    key="fs_image_date_placeholder",
                )
            else:
                if selected_fs_gdf is None:
                    st.info("No geometry found for the selected FS catchment.")
                else:
                    image_collection = ee_functions.get_available_images(
                        selected_fs_gdf,
                        selected_start_date,
                        selected_end_date,
                        max_cloud_cover,
                    )

                    available_image_dates_list = (
                        ee_functions.available_imagery_dates_list(image_collection)
                    )

                    if not available_image_dates_list:
                        st.info(
                            "No imagery available for the selected filters yet. "
                            "Try widening the date range or relaxing the cloud cover."
                        )
                    else:
                        selected_available_image_date = st.selectbox(
                            "Select the image date",
                            available_image_dates_list,
                            index=0,
                            key="fs_image_date",
                        )

    if selected_fs_name is not None and selected_available_image_date is None:
        st.info(
            "Select a different date range or FS catchment to see available imagery."
        )

    # If nothing is selected yet, just show all FS catchments on a simple map
    if selected_fs_name is None:
        m = geemap.Map(
            control_scale=True,
            draw_control=False,
            layer_control=False,
        )
        m.add_child(
            MeasureControl(
                primary_length_unit="kilometers",
                secondary_length_unit="meters",
                primary_area_unit="sqmeters",
                secondary_area_unit="hectares",
            )
        )
        m.zoom_to_gdf(fs_gdf)
        m.add_gdf(_folium_safe_gdf(fs_gdf, [FS_NAME_COL, "geometry"]), layer_name="FS Catchments")
        m.to_streamlit(height=550)
        return

    # If FS catchment and date are selected, show imagery and metrics
    if selected_fs_name is not None and selected_available_image_date is not None:
        if selected_fs_gdf is None:
            st.warning("Unable to load the selected FS catchment geometry.")
            return

        buffered_selected_fs_gdf = ee_functions.get_buffered_farm_gdf(selected_fs_gdf)

        # For large FS catchments, single Sentinel‑2 tiles might not cover
        # the whole area. Build a mosaic of all tiles intersecting the
        # catchment on the selected date, then clip to the buffered AOI.
        selected_start_date_img, selected_end_date_img = (
            ee_functions.selected_date_range(selected_available_image_date)
        )

        image_collection = ee_functions.get_available_images(
            selected_fs_gdf,
            selected_start_date_img,
            selected_end_date_img,
            max_cloud_cover,
        )

        # If the date-range filter yields no images, the EE tile layer won't render.
        try:
            image_count = int(image_collection.size().getInfo())
        except Exception:
            image_count = 0

        if image_count == 0:
            st.warning(
                "No Sentinel-2 imagery found for the selected catchment/date. "
                "Try selecting a different image date, widening the date range, or increasing cloud cover."
            )
            m = geemap.Map(control_scale=True, draw_control=False, layer_control=False)
            m.add_child(
                MeasureControl(
                    primary_length_unit="kilometers",
                    secondary_length_unit="meters",
                    primary_area_unit="hectares",
                    secondary_area_unit="sqmeters",
                )
            )
            m.add_gdf(
                _folium_safe_gdf(selected_fs_gdf, [FS_NAME_COL, "geometry"]),
                layer_name="FS Catchment",
            )
            m.zoom_to_gdf(buffered_selected_fs_gdf)
            m.to_streamlit(height=550)
            return

        buffered_selected_fs_ee = geemap.gdf_to_ee(buffered_selected_fs_gdf)
        # Mosaic may drop metadata; preserve a representative acquisition timestamp.
        image_for_date = ee.Image(image_collection.sort("system:time_start", False).first())
        true_color_image = (
            image_collection.mosaic()
            .clip(buffered_selected_fs_ee)
            .copyProperties(image_for_date, ["system:time_start"])
        )

        true_color_visparams = ee_functions.get_vis_params("True Color")
        image_date = ee_functions.get_imagery_date(true_color_image)

        m = geemap.Map(control_scale=True, draw_control=False, layer_control=False)
        m.add_ee_layer = ee_functions.add_ee_layer.__get__(m)

        m.add_child(
            MeasureControl(
                primary_length_unit="kilometers",
                secondary_length_unit="meters",
                primary_area_unit="hectares",
                secondary_area_unit="sqmeters",
            )
        )

        # Base true color image
        m.add_ee_layer(
            true_color_image,
            visparams=true_color_visparams,
            name="True Color",
        )

        # If a metric is selected, calculate index, classify, and show chart + legend
        if selected_index is not None:
            with st.spinner(f"Calculating {selected_index.lower()}...", show_time=True):
                calculated_index_image = ee_functions.calculate_index(
                    selected_index, true_color_image
                )
                classified_index_image = ee_functions.classifiy_index_values(
                    selected_fs_gdf,
                    calculated_index_image,
                    selected_index,
                )

            selected_index_visparams = ee_functions.get_vis_params(selected_index)
            legend_labels, legend_colors = ee_functions.legend_params(selected_index)

            fig_df = ee_functions.area_chart_df(
                selected_fs_gdf, classified_index_image, selected_index
            )
            chart = ee_functions.altair_chart(fig_df, selected_index)

            with st.expander(f"View {selected_index} metrics..."):
                with st.spinner("Calculating metrics...", show_time=True):
                    bar_chart_col, _ = st.columns([4, 1])
                    with bar_chart_col:
                        st.altair_chart(chart)

            with st.spinner(
                f"Adding {selected_index.lower()} to map...", show_time=True
            ):
                m.add_ee_layer(
                    classified_index_image,
                    visparams=selected_index_visparams,
                    name=selected_index,
                )

            legend_dict = dict(zip(legend_labels, legend_colors))

            from apps import soil_functions  # Local import to avoid circulars at top

            soil_functions.add_categorical_legend(
                m,
                selected_index,
                list(legend_dict.values()),
                list(legend_dict.keys()),
            )

        m.add_gdf(
            _folium_safe_gdf(selected_fs_gdf, [FS_NAME_COL, "geometry"]),
            layer_name="FS Catchment",
        )

        # Overlay smallholder fields that fall inside the selected FS catchment
        if sh_gdf is not None and not sh_gdf.empty:
            try:
                # Align CRS for spatial join
                fs_for_join = selected_fs_gdf.copy()
                sh_for_join = sh_gdf.copy()

                if fs_for_join.crs is None:
                    fs_for_join.set_crs(epsg=4326, inplace=True)
                if sh_for_join.crs is None:
                    sh_for_join.set_crs(epsg=4326, inplace=True)

                if sh_for_join.crs != fs_for_join.crs:
                    sh_for_join = sh_for_join.to_crs(fs_for_join.crs)

                # Spatial join: keep smallholder fields within the selected FS catchment
                sh_in_catchment = gpd.sjoin(
                    sh_for_join, fs_for_join[["geometry"]], how="inner", predicate="within"
                )

                if not sh_in_catchment.empty:
                    _add_smallholder_circle_layer(m, sh_in_catchment)
            except Exception:
                # If anything goes wrong, just skip the overlay instead of breaking the app
                pass
        m.zoom_to_gdf(buffered_selected_fs_gdf)
        m.add_text(image_date, position="topright", fontsize=16, bold=True)
        m.to_streamlit(height=550)

