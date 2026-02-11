import streamlit as st
from streamlit_option_menu import option_menu
from apps import ce_app, access, sh_app, soil_app , ff_app, hb_app

access.ee_to_st()
st.set_page_config(page_title="Streamlit Geospatial", layout="wide")

apps = [
    {"func": ce_app.app, "title": "C&E", "icon": ":seedling:"},
    {"func": sh_app.app, "title": "Small Holder", "icon": ":seedling:"},
    {"func": soil_app.app, "title": "Analysis", "icon": ":seedling:"},
    {"func": ff_app.app, "title": "Foundation Farm", "icon": ":leaf:"},
    {"func": hb_app.app, "title": "Hub Definition", "icon": ":seedling:"},
]

titles = [app["title"] for app in apps]
titles_lower = [title.lower() for title in titles]
icons = [app["icon"] for app in apps]

with st.sidebar:
    st.logo(r"data/images/logo_white_no_bg.png", size="large")

    selected = option_menu(
        "Menu",
        options=titles,
        icons=icons,
        menu_icon="globe-europe-africa",
        # default_index=default_index,
    )

    st.sidebar.title("Info")
    st.sidebar.info(
        """
        This web [app](https://crop-monitor-app-yyhg7vyflyu7dwisr8hihf.streamlit.app/)
        is maintained by [Good Nature Agro](https://goodnatureagro.com/).
    """
    )

for app in apps:
    if app["title"] == selected:
        app["func"]()
        break
