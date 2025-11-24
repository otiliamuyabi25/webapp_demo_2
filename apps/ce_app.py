import datetime
import streamlit as st
import geopandas as gpd
import geemap.foliumap as geemap
from folium.plugins import MeasureControl # Module to add measure control to map
from apps import ee_functions, variables ,  soil_functions 

# Add C&E farms
farms_gdf = variables.get_farms_gdf()
def app():
    """This function adds the app that dispace the C&E crop health and soil properties
    """
    # # Define tabs for app
    # individual_health_tab, compare_tab, soil_tab , individual_health_2_tab = st.tabs(
    #     ["Individual Health", "Compare Health", "Soil Properties", "Individual Health 2"]
    #     )
        # Define tabs for app
    individual_health_tab, compare_tab, soil_tab = st.tabs(
        ["Individual Health", "Compare Health", "Soil Properties"]
        )

    # Start of individual health tab
    with individual_health_tab:
        st.header("View Crop Health") # Tab header

        # Define columns to hold dropdowns
        # initial_col holds all the dropdowns except the available images dropdown
        initial_col, available_images_col = st.columns([5, 1])

        # Add dropdowns for the first column
        with initial_col:
            selected_year, selected_farm_name, selected_index, selected_range_start_date, selected_range_end_date, max_cloud_cover = variables.add_selectors_crop_health()

            # st.write(f"selected available image date : {selected_range_start_date} to {selected_range_end_date}")

        with initial_col:
            # Filter farms by year for downstream widgets and maps
            if selected_year is not None:
                farms_filtered_by_year = farms_gdf[farms_gdf["year"] == selected_year]
                if farms_filtered_by_year.empty:
                    farms_filtered_by_year = farms_gdf
            else:
                farms_filtered_by_year = farms_gdf

            # Helper to get the selected farm while respecting the year filter first
            def get_selected_farm_gdf():
                if selected_farm_name is None:
                    return None
                if selected_year is not None:
                    filtered = farms_gdf[
                        (farms_gdf["farmer"] == selected_farm_name)
                        & (farms_gdf["year"] == selected_year)
                    ]
                    if not filtered.empty:
                        return filtered
                fallback = farms_gdf[farms_gdf["farmer"] == selected_farm_name]
                return fallback if not fallback.empty else None

            selected_farm_gdf = get_selected_farm_gdf()

        available_image_dates_list = []

        with st.spinner(f"Getting available images for {selected_farm_name}...", show_time=True): # Display spinner while this block of code is being executed
            # Add dropdown for the second column
            with available_images_col:
                if selected_farm_name is None: 
                    selected_available_image_date = st.selectbox(
                    "Select the specific date", # Dropdown description
                    ["Select farm"], # Dropdown option
                    index=None, # No default value
                    placeholder="Select date...", # Dropdown placeholder
                    key=15 # Unique dropwdown  id
                    )

                # Populate available images date dropdown when farm name is selected
                else:
                    # Get image collection for selected farm within the default date range
                    image_collection = ee_functions.get_available_images(
                        selected_farm_gdf,
                        selected_range_start_date,
                        selected_range_end_date,
                        max_cloud_cover
                        )

                    # Get list of available images from the image collection
                    available_image_dates_list = ee_functions.available_imagery_dates_list(image_collection)

                    if not available_image_dates_list:
                        st.info("No imagery available for the selected filters yet.")
                        selected_available_image_date = None
                    else:
                        # Add available image 
                        selected_available_image_date = st.selectbox(
                            "Select the image date",
                            available_image_dates_list,
                            index=0 # Selects the first image date from the list
                            )

        if selected_farm_name is not None and selected_available_image_date is None:
            st.info("Select a different year, farm, or date range to see available imagery.")

        # Display basic map if farm name and metric/index is not selected
        if (selected_farm_name is None and selected_index is None) or (selected_farm_name is None and selected_index is not None):
            # Add map to display
            m = geemap.Map(
                control_scale=True, # Add scale (control) in map
                draw_control=False,
                layer_control=False
                )

            # Add map button to measure distance and area
            m.add_child(MeasureControl(
                primary_length_unit='kilometers',
                secondary_length_unit='meters',
                primary_area_unit='sqmeters',
                secondary_area_unit='hectares'
            ))

            m.zoom_to_gdf(farms_filtered_by_year) # Zoom to extents of filtered farms
            m.add_gdf(farms_filtered_by_year, layer_name="Farms") # Add filtered farms to the map
            m.to_streamlit(height=550) # Show map on display with height of 550

        # Add functionalities when the farm is selected and imagery is available
        elif selected_farm_name is not None and selected_available_image_date is not None:
            # Buffer the gdf for the selected farm
            buffered_selected_farm_gdf = ee_functions.get_buffered_farm_gdf(selected_farm_gdf)

            # Get the start and end dates around the selected image date
            selected_start_date, selected_end_date = ee_functions.selected_date_range(selected_available_image_date)

            # Get true color image
            true_color_image = ee_functions.get_available_image(
                selected_farm_gdf,
                selected_start_date,
                selected_end_date,
                max_cloud_cover
                )

            # Get true color visparams
            true_color_visparams = ee_functions.get_vis_params("True Color")

            # Get date for true color image
            image_date = ee_functions.get_imagery_date(true_color_image)

            # Add map to the display
            m = geemap.Map(control_scale=True, draw_control=False, layer_control=False)

            # Redefine function to add ee layer to map
            m.add_ee_layer = ee_functions.add_ee_layer.__get__(m)

            # Add button to measure distances and areas on the map
            m.add_child(MeasureControl(
                primary_length_unit='kilometers',
                secondary_length_unit='meters',
                primary_area_unit='hectares',
                secondary_area_unit='sqmeters'
            ))

            # Add true color image to the map
            m.add_ee_layer(
                true_color_image, 
                visparams=true_color_visparams,
                name='True Color'
                )

            # Add functionalities when both the farm and metric/index is selected
            if selected_farm_name is not None and selected_index is not None:
                with st.spinner(f"Calculating {selected_index.lower()}...", show_time=True):
                    # Get image with calculated index from true color image
                    calculated_index_image = ee_functions.calculate_index(
                        selected_index,
                        true_color_image
                        )

                    # Classify/group the calculated index based on the index values
                    classified_index_image = ee_functions.classifiy_index_values(
                        selected_farm_gdf,
                        calculated_index_image,
                        selected_index
                        )

                # Get visualisation parameters for the classified image
                selected_index_visparams = ee_functions.get_vis_params(selected_index)

                # Get the labels and colors for the legend
                legend_labels, legend_colors = ee_functions.legend_params(selected_index)

                # Get the df with the chart metrics for the selected index
                fig_df = ee_functions.area_chart_df(
                    selected_farm_gdf,
                    classified_index_image,
                    selected_index
                    )

                # Get chart to display crop metrics from the df
                chart = ee_functions.altair_chart(fig_df, selected_index)

                # Expander that holds the chart
                with st.expander(f"View {selected_index} metrics..."):
                    with st.spinner("Calculating metrics...", show_time=True):
                        # Define column containers to hold the charts
                        bar_chart_col, col2 = st.columns([4,1]) # [4,1] is the ratio for the column sizes

                        # Add the chart to column 1
                        with bar_chart_col:
                            # Display chart to display crop metrics
                            st.altair_chart(chart)

                        # Column 2 can be used to add addtional charts 
                        # (e.g. trends) if necessary

                with st.spinner(f"Adding {selected_index.lower()} to map...", show_time=True):
                    # Add the classified image to the map
                    m.add_ee_layer(
                        classified_index_image,
                        visparams= selected_index_visparams,
                        name= selected_index
                        )

                # Dictionary that pairs the legend color to the corresponding label
                legend_dict = dict(zip(legend_labels, legend_colors))

                # Add legend to the map
                soil_functions.add_categorical_legend(
                    m, selected_index,
                    list(legend_dict.values()),
                    list(legend_dict.keys())
                    )

                # Easier way to add legend but gives error sometimes
                # m.add_legend(
                #     labels=legend_labels,
                #     colors=legend_colors,
                #     position="bottomright",
                #     title= selected_index,
                #     draggable=True
                #     )

            # Display the selected farm boundary on the map
            m.add_gdf(selected_farm_gdf, layer_name="Farm")

            # Zoom to the buffered farm to the map
            m.zoom_to_gdf(buffered_selected_farm_gdf)

            # Add date for the selected image to the map
            m.add_text(image_date, position="topright", fontsize= 16, bold=True)

            # Display the map in streamlit
            m.to_streamlit(height=550)

    # Start of compare health tab
    with compare_tab:
        st.header("Compare Crop Health") # Tab header

        # Add dropdowns and filters
        selected_year, selected_farm_name, selected_index, selected_start_date, selected_end_date, max_cloud_cover = variables.add_selectors_crop_monitor(backtrack_days=60)

        # Get gdf for the selected farm
        selected_farm_gdf = farms_gdf[farms_gdf["farmer"] == selected_farm_name]

        # Do nothing no farm is selected
        if selected_farm_name is None:
            pass
        else:
            with st.spinner(f"Get available images for {selected_farm_name}...", show_time=True):
                # Get image collection for farm with selected/default dates and cloud cover
                image_collection = ee_functions.get_available_images(
                    selected_farm_gdf,
                    selected_start_date,
                    selected_end_date,
                    max_cloud_cover
                )

                # List of dates for available images within date range
                available_image_dates = ee_functions.available_imagery_dates_list(image_collection)

                # Only display images if 2 or more images are in the image dates list
                if selected_farm_name and len(available_image_dates) >= 2:
                    # Display 2 images if images dates list has less the 4 images
                    if len(available_image_dates) < 4:
                        image1_date, image2_date = ee_functions.add_crop_monitor_image_date_selectors(available_image_dates)
                        image_dates = [image1_date, image2_date]
                    # Display 4 images if image dates list has 4 or more images
                    else:
                        image1_date, image2_date, image3_date, image4_date = ee_functions.add_crop_monitor_image_date_selectors(available_image_dates)
                        image_dates = [image1_date, image2_date, image3_date, image4_date]

                    # Get selected true color images as a list
                    images = ee_functions.get_images_list(image_dates, image_collection, selected_farm_gdf)
                    
                    if selected_index is None:
                        index_images_list = None

                    else:
                        # Get index images from the true color as a list
                        index_images_list = ee_functions.get_index_images_list(images, selected_index, selected_farm_gdf)

                    # Display all the maps
                    ee_functions.add_all_maps(images, index_images_list, selected_index, image_dates, selected_farm_gdf)

    with soil_tab:
        st.header("View Soil Properties") # Tab header

        # Define columns for the farm and dataset dropdowns
        farm_col, dataset_col, = st.columns(2)

        # Add farm names dropdown to the farm column
        with farm_col:
            selected_farm_name = st.selectbox(
                "Select farm",
                options=variables.farm_names_list(),
                index = None,
                key = 50,
                placeholder="Select farm"
            )

        # Add datasets dropdown to the datasets column
        with dataset_col:
            selected_dataset_name = st.selectbox(
                "Select soil dataset",
                options=soil_functions.get_soil_dataset(selected_aoi_gdf=None),
                index = None,
                key = 51,
                placeholder="Select soil dataset"
            )

        if selected_farm_name is None:
            selected_farm = gpd.read_file(r"data/vector/zambia_aoi.gpkg")

            # Show dataset on whole country if farm not selected
            if selected_dataset_name is not None:
                selected_dataset = soil_functions.get_soil_dataset(selected_farm)[selected_dataset_name]
        else:
            # Get gdf for the selected farm
            selected_farm = farms_gdf[farms_gdf["farmer"] == selected_farm_name]

            # Buffer selected farm gdf
            buffered_selected_farm = ee_functions.get_buffered_farm_gdf(selected_farm)

            # Get true color image for selected farm
            true_color_image = ee_functions.get_available_image(
                    buffered_selected_farm, 
                    selected_start_date=str(datetime.date.today() - datetime.timedelta(days=100)),
                    selected_end_date=str(datetime.date.today()), max_cloud_cover=10
                    )

            # Define visualisation parameters for the selected farm
            true_color_visparams = ee_functions.get_vis_params("True Color")

            # Get selected dataset
            if selected_dataset_name is not None:
                selected_dataset = soil_functions.get_soil_dataset(buffered_selected_farm)[selected_dataset_name]

        # Define visualisation parameters for the selected dataset
        if selected_dataset_name is not None:
            # Visualisation parameters if soil texture dataset is selected
            if selected_dataset_name == 'Texture Class':
                soil_visparams, soil_texture_names, soil_texture_palette = soil_functions.get_soil_dataset_visparams(selected_dataset_name, selected_dataset)

            # Visualisation parameters if other datasets selected
            else:
                soil_visparams = soil_functions.get_soil_dataset_visparams(selected_dataset_name, selected_dataset)

        # Call mapping module
        m = geemap.Map(
            control_scale=True, # Add scale map
            draw_control=False,
            layer_control=False)

        # Redefine function too add Earth Engine layers to the map
        m.add_ee_layer = ee_functions.add_ee_layer.__get__(m)

        # Add distance and area measure control to the map
        m.add_child(MeasureControl(
                primary_length_unit='kilometers',
                secondary_length_unit='meters',
                primary_area_unit='sqmeters',
                secondary_area_unit='hectares'
            ))        

        # Display true color image of the selected farm if dataset is not selected
        if selected_farm_name is not None and selected_dataset_name is None:
            # Add true color image to the map
            m.add_ee_layer(
                true_color_image, visparams= true_color_visparams, name= 'True Color'
                )

            # Add farm boundary to the map
            m.add_gdf(selected_farm, layer_name="Farm")
        
        # Display selected dataset on whole country if farm not selected
        elif selected_farm_name is None and selected_dataset_name is not None:
            # Add country boundary to the map
            m.add_gdf(selected_farm, layer_name="Country")

            # Add selected dataset to the map
            m.add_ee_layer(
                selected_dataset, visparams=soil_visparams, name=selected_dataset_name
                )
            # m.add_text(selected_dataset_name, position="topright", fontsize= 16, bold=True)

        # Add selected dataset to the selected farm if both are defined as well as true colour image
        elif selected_farm_name is not None and selected_dataset_name is not None:
            # Add the true color image to the map
            m.add_ee_layer(
                    true_color_image, visparams= true_color_visparams, name= 'True Color'
                    )
            
            # Add the selected dataset to the map
            m.add_ee_layer(
                selected_dataset, visparams=soil_visparams, name=selected_dataset_name
                )
            # Add the slected farm boundary to the map
            m.add_gdf(selected_farm, layer_name="Farm")
            # m.add_text(selected_dataset_name, position="topright", fontsize= 16, bold=True)

        # Add categorical legend if texture class dataset is selected
        if selected_dataset_name == 'Texture Class':
            legend_dict = dict(zip(soil_texture_names, soil_texture_palette))
            soil_functions.add_categorical_legend(
                m, f"Soil {selected_dataset_name}",
                list(legend_dict.values()), # Soil texture colours
                list(legend_dict.keys()) # Soil texture names
                )
            # m.add_legend(
            #             labels=soil_texture_names,
            #             colors=soil_texture_palette,
            #             position="bottomright",
            #             title= f"Soil {selected_dataset_name}",
            #             draggable=True
            #             )

        # Add the colorbar if other datasets are selected
        elif selected_dataset_name is not None:
            soil_functions.add_vertical_colorbar(
                m, f"Soil {selected_dataset_name}",
                soil_visparams['min'],
                soil_visparams['max'],
                soil_visparams['palette']
                )
            # m.add_colorbar(soil_visparams, label=selected_dataset_name, orientation='vertical')

        # Zoom map to boundary of all farms is no farm and dataset is selected
        if selected_dataset_name is None and selected_dataset_name is None:
            m.zoom_to_gdf(farms_gdf)

        # Zoom to boundary of selected farm 
        # Zooms to boundary of Country if farm name not selected but dataset is 
        else:
            m.zoom_to_gdf(selected_farm)

        # Display map in streamlit
        m.to_streamlit(height=550)
