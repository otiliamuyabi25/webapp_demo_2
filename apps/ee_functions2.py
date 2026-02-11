from datetime import datetime, timedelta
import math
import streamlit as st
import geemap.foliumap as geemap
import ee
import pandas as pd
import folium
import altair as alt

def get_buffered_farm_gdf(selected_farm_gdf):
    proj_selected_farm_gdf = selected_farm_gdf.to_crs(epsg=3857)
    proj_selected_farm_gdf["geometry"] = proj_selected_farm_gdf.geometry.buffer(50)
    buffered_selected_farm_gdf = proj_selected_farm_gdf.to_crs(epsg=4326)

    return buffered_selected_farm_gdf

def get_available_images(selected_farm_gdf, selected_start_date, selected_end_date, max_cloud_cover):
    buffered_selected_farm_gdf = get_buffered_farm_gdf(selected_farm_gdf)

    buffered_selected_farm_ee = geemap.gdf_to_ee(buffered_selected_farm_gdf)

    available_images =  ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
        .filterBounds(buffered_selected_farm_ee) \
        .filterDate(selected_start_date, selected_end_date) \
        .select(["B12", "B11", "B8", "B4", "B3", "B2"]) \
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud_cover))

    return available_images

def get_available_image(selected_farm_gdf, selected_start_date, selected_end_date, max_cloud_cover):
    buffered_selected_farm_gdf = get_buffered_farm_gdf(selected_farm_gdf)

    buffered_selected_farm_ee = geemap.gdf_to_ee(buffered_selected_farm_gdf)

    available_images = get_available_images(
        selected_farm_gdf, selected_start_date, selected_end_date, max_cloud_cover
        )

    available_image = available_images.first().clip(buffered_selected_farm_ee)

    return available_image

# Define NDVI intervals with description and correspondings color
def index_intervals(selected_index):
    if selected_index == 'Crop Health': # NDVI
        ndvi_intervals = [
            (-1.00, 0.30, 'No Vegetation', "#860000", 0),
            (0.30, 0.40, 'Very Poor/Stressed', "#FC1D1D", 1),
            (0.40, 0.50, 'Poor/Early Stress',"#ffbc69", 2),
            (0.50, 0.70, 'Moderate', "#5d9557", 3),
            (0.70, 0.85, 'Good', "#00FF00", 4),
            (0.85, 1.00, 'Excellent/Optimal', "#003b0d", 5)
        ]
        return ndvi_intervals

    elif selected_index == 'Crop Moisture': # NDMI
        ndmi_intervals = [
            (-1.00, -0.40, 'No Vegetation', "#700000", 0),
            (-0.40, 0.20, 'Poor Moisture/Early Stress', "#e02d2c", 1),
            (0.20, 0.40, 'Mild Water Stress',"#ffab69", 2),
            (0.40, 0.55, 'Adequate Moisture', "#006cc4", 3),
            (0.55, 0.80, 'Optimal Moisture', "#3721FF", 4),
            (0.80, 1.00, 'Overwatered/Overflooded', "#060046", 5)
        ]
        return ndmi_intervals

# Select visualisation parameters for selected index
def get_vis_params(selected_index):
    if selected_index is None:
        pass
    elif selected_index == "True Color":
        true_color_vis = {'min': 200, 'max': 1500, 'bands': ['B4', 'B3', 'B2']}
        return true_color_vis
    else:
        palette = [color for _, _, _, color, _ in index_intervals(selected_index) ]
        min = 0
        max = len(palette) - 1

        indices_vis = {"min": min, "max": max, "palette": palette}

        return indices_vis

def calculate_index(selected_index, true_color_image):
    """
    Calculate a vegetation/moisture index from an EE image.

    `true_color_image` may be any EE object that can be coerced to an
    `ee.Image` (e.g. results of mosaic/clip/expressions). We normalise
    it here to avoid AttributeErrors on non-Image types.
    """
    # Ensure we always work with an ee.Image instance
    try:
        img = ee.Image(true_color_image)
    except Exception as e:
        raise ValueError(f"Expected an Earth Engine image for index calculation, got {type(true_color_image)}") from e

    if selected_index == "Crop Health": # NDVI
        return img.normalizedDifference(["B8", "B4"])
    elif selected_index == "Crop Moisture": # NDMI
        return img.normalizedDifference(["B8", "B11"])
    # elif selected_index == "LSWI":
    #     return true_color_image.normalizedDifference(["B8", "B12"])

# Group selected index pixel values
def classifiy_index_values(selected_farm_gdf, calculated_index, selected_index):
    aoi = geemap.gdf_to_ee(selected_farm_gdf)
    intervals = index_intervals(selected_index)

    # Start with a blank image (type byte for classification)
    grouped_index = ee.Image(0).byte().rename("classified").clip(aoi)

    # Iterate through NDVI intervals
    for lower, upper, _, _, class_id in intervals:
        # Create mask for range
        mask = calculated_index.gte(lower).And(calculated_index.lt(upper))

        # Add to classified raster (set class_value for pixels in range)
        grouped_index = grouped_index.where(mask,class_id)

    return grouped_index

# Define legend visualisation parameters
def legend_params(selected_index):
    intervals = index_intervals(selected_index)

    # Get legend labels
    labels = []
    for key, interval in enumerate(intervals):
        description = interval[2]
        labels.append(description)
    reversed_labels = labels[::-1]

    # Get legend colors
    colors = [] 
    for color, interval in enumerate(intervals):
        colour = intervals[color][3]
        colors.append(colour)
    reversed_colors = colors[::-1]

    return reversed_labels, reversed_colors

def get_imagery_date(true_color_image):
    """
    Return a human-friendly capture date for an EE Image.

    Note: Images produced via operations like mosaic()/visualize() may not carry
    the original metadata properties (including system:time_start).
    """
    try:
        # Robust server-side check for the property (avoids KeyError on getInfo()).
        has_ts = true_color_image.propertyNames().contains("system:time_start")
        date_str = ee.String(
            ee.Algorithms.If(
                has_ts,
                ee.Date(true_color_image.get("system:time_start")).format("dd MMMM YYYY"),
                "Imagery date unavailable",
            )
        ).getInfo()
        return date_str
    except Exception:
        return "Imagery date unavailable"

# Calculate area of pixels per index category
def index_class_pixels_area(farm_gdf, classified_index, selected_index):
    aoi = geemap.gdf_to_ee(farm_gdf)
    intervals = index_intervals(selected_index)

    indices_area_ha = {}
    bar_colors = []

    # Get the name of the band in the calculated index image
    band_name = "classified"

    # Iterate through index intervals
    for _, _, index_value_class, color, class_id in intervals:
        # Create mask for range
        mask = classified_index.gte(class_id).And(classified_index.lt(class_id + 1))

        # Calculate pixel area in square meters
        pixel_area = mask.multiply(ee.Image.pixelArea())
        total_area_m2 = pixel_area.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=aoi,
            scale=10,
            maxPixels=1e9
        )

        # Extract the area using the band name
        value = total_area_m2.get(band_name)
        if value:
            total_area_ha = ee.Number(value).divide(10000).getInfo()
        else:
            total_area_ha = 0

        # Store area per class
        indices_area_ha[index_value_class] = round(total_area_ha, 2)
        bar_colors.append(color)

    return indices_area_ha, bar_colors

def area_chart_df(selected_farm_gdf, classified_index, selected_index):
    pixel_class_area, colors = index_class_pixels_area(
        selected_farm_gdf, classified_index, selected_index
    )

    # Build a DataFrame
    df = pd.DataFrame({
        selected_index: list(pixel_class_area.keys()),
        "Area (Ha)": list(pixel_class_area.values()),
        "Color": colors
    })

    # Calculate total area
    total_area = df["Area (Ha)"].sum()

    # Add formatted percentage column
    if total_area > 0:
        df["Percentage"] = df["Area (Ha)"].apply(
            lambda area: f"{(area / total_area) * 100:.1f}%"
        )
    else:
        df["Percentage"] = "0.0%"

    return df

def altair_chart(figure_df, selected_index):
    # Define custom order
    custom_order = figure_df[selected_index].to_list()[::-1]

    chart = alt.Chart(figure_df).mark_bar().encode(
        x=alt.X('Area (Ha):Q'),
        y=alt.Y(f'{selected_index}:N',
                sort=custom_order),
        color=alt.Color('Color:N', scale=None, legend=None),  # legend=None hides color label
        tooltip=[
                alt.Tooltip(f'{selected_index}:N'),
                 alt.Tooltip('Area (Ha):Q'),
                 alt.Tooltip('Percentage:N')
                 ]
        ).properties(
            width=500,
            height=250
    )

    return chart

def add_ee_layer(self, ee_object, visparams=None, name="Layer", shown=True, opacity=1.0):
    """
    Lightweight version of geemap's add_ee_layer for Folium maps.

    It is intentionally tolerant of object types:
    - Any ee.Image/ee.ImageCollection-like object is rendered as a raster tile layer.
    - ee.Geometry / ee.Feature / ee.FeatureCollection are rendered as GeoJSON.
    """
    if visparams is None:
        visparams = {}

    try:
        # Vector data as GeoJSON
        if isinstance(ee_object, (ee.Geometry, ee.Feature, ee.FeatureCollection)):
            folium.GeoJson(data=ee_object.getInfo(), name=name).add_to(self)
            return

        # Everything else is treated as raster imagery.
        img = None
        if isinstance(ee_object, ee.ImageCollection):
            img = ee_object.mosaic()
        else:
            # This will also handle plain Images and many computed objects.
            img = ee.Image(ee_object)

        map_id_dict = img.getMapId(visparams)
        folium.raster_layers.TileLayer(
            tiles=map_id_dict["tile_fetcher"].url_format,
            attr="Google Earth Engine",
            name=name,
            overlay=True,
            control=True,
            show=shown,
            opacity=opacity,
        ).add_to(self)

    except Exception as e:
        # Surface enough info in logs to debug if it fails again.
        print("Error adding Earth Engine layer:", repr(e))
        print("  EE object type:", type(ee_object))

# **************Functions specifically for "Compare Crop Health" Section************************
def add_crop_monitor_image_date_selectors(available_image_dates):
    with st.expander(f"Click to select images to compare within date range specified above..."):
        image1_col, image2_col, image3_col, image4_col = st.columns([3, 3, 3, 3])

        with image1_col:
            image1 = st.selectbox(
                "Select first image date", 
                available_image_dates,
                index=0,
                key=20
                )

        with image2_col:
            image2 = st.selectbox(
                "Select second image date",
                available_image_dates, 
                index=math.ceil(len(available_image_dates)*0.25),
                key=21
                )

        if len(available_image_dates) < 4:
            return image1, image2
        else:
            with image3_col:
                image3 = st.selectbox(
                    "Select third image date",
                    available_image_dates,
                    index=math.ceil(len(available_image_dates)*0.75) - 1,
                    key=22
                    )
            with image4_col:
                image4 = st.selectbox(
                    "Select fourth image date",
                    available_image_dates,
                    index=len(available_image_dates) - 1,
                    key=23
                    )
            return image1, image2, image3, image4

def available_imagery_dates_list(image_collection):
    # Create empty list for available images
    available_images_list = []

    # Loop to loop through available images and add info to list
    for i in range(len(image_collection.getInfo()['features'])):
        # Get date imagery was captured
        start_date = image_collection.getInfo()['features'][i]['properties']['system:time_start']

        # Change format for the date the image was captured
        dates = datetime.utcfromtimestamp(start_date/1000).strftime("%d %B %Y")

        # Add combined sentence to list
        available_images_list.append(dates)

    # unique_available_images_list = list(set(available_images_list))

    return available_images_list[::-1]

def selected_date_range(selected_date):
    date_object = datetime.strptime(selected_date, '%d %B %Y')

    # Add one day
    start_date = date_object - timedelta(days=1)
    # Format the new date
    start_date = start_date.strftime('%Y-%m-%d')

    # Add one day
    end_date = date_object + timedelta(days=1)
    # Format the new date
    end_date = end_date.strftime('%Y-%m-%d')

    return start_date, end_date

def get_images_list(selected_image_dates_list, image_collection, selected_farm_gdf):
    buffered_selected_farm_gdf = get_buffered_farm_gdf(selected_farm_gdf)

    buffered_selected_farm_ee = geemap.gdf_to_ee(buffered_selected_farm_gdf)

    images_list = []

    for image_date in selected_image_dates_list:
        image_start, image_end = selected_date_range(image_date)

        image = image_collection \
            .filterDate(image_start, image_end) \
            .first().clip(buffered_selected_farm_ee)

        images_list.append(image)

    return images_list

def get_index_images_list(images_list, selected_index, selected_farm_gdf):
    index_images_list = []

    for image in images_list:
        calculated_index_image = calculate_index(selected_index, image)
        classified_index_image = classifiy_index_values(selected_farm_gdf, calculated_index_image, selected_index)

        index_images_list.append(classified_index_image)

    return index_images_list

def add_specific_map(selected_farm_gdf, selected_date, ee_image, index_image, selected_index, true_color_visparams, index_visparams):
    m = geemap.Map()
    m.add_ee_layer = add_ee_layer.__get__(m)

    buffered_selected_farm_gdf = get_buffered_farm_gdf(selected_farm_gdf)

    m.zoom_to_gdf(buffered_selected_farm_gdf)
    m.add_ee_layer(ee_image,
                    visparams= true_color_visparams,
                    name= 'True Color')
    
    if index_image is None or selected_index is None or index_visparams is None:
        pass
    else:
        m.add_ee_layer(index_image,
                    visparams= index_visparams,
                    name= selected_index)
    
    m.add_text(selected_date,
                    position="topright",
                    fontsize= 12, bold=True)
    m.add_gdf(selected_farm_gdf, layer_name="Farm")
    m.to_streamlit(height=300)

def add_all_maps(images_list, index_image_list, selected_index, image_dates, selected_farm_gdf):
    true_color_visparams = get_vis_params("True Color")

    if index_image_list is None or selected_index is None:
        index_visparams = None
        index_image = [None, None, None, None]
    else:
        index_visparams = get_vis_params(selected_index)
        index_image = [index_image_list[0], index_image_list[1], index_image_list[2], index_image_list[3]]


    map_col1, map_col2 = st.columns([3,3])
    with map_col1:
        with st.spinner(f"Adding first image...", show_time=True):
            add_specific_map(
                selected_farm_gdf,
                image_dates[0],
                images_list[0],
                index_image[0],
                selected_index,
                true_color_visparams,
                index_visparams
                )

    with map_col2:
        with st.spinner(f"Adding second image...", show_time=True):
            add_specific_map(
                selected_farm_gdf,
                image_dates[1],
                images_list[1],
                index_image[1],
                selected_index,
                true_color_visparams,
                index_visparams
                )

    if len(images_list) > 3:
        map_col3, map_col4 = st.columns([3,3])
        with map_col3:
            with st.spinner(f"Adding third image...", show_time=True):
                add_specific_map(
                    selected_farm_gdf,
                    image_dates[2],
                    images_list[2],
                    index_image[2],
                    selected_index,
                    true_color_visparams,
                    index_visparams
                    )

        with map_col4:
            with st.spinner(f"Adding fourth image...", show_time=True):
                add_specific_map(
                    selected_farm_gdf,
                    image_dates[3],
                    images_list[3],
                    index_image[3],
                    selected_index,
                    true_color_visparams,
                    index_visparams
                    )
