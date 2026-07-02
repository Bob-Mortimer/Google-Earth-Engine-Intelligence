import streamlit as st
import ee
import folium
import streamlit.components.v1 as components
from datetime import date, timedelta
import requests
import json
from google.oauth2 import service_account

# =========================================================================
# 1. PAGE CONFIGURATION & INITIALIZATION
# =========================================================================
st.set_page_config(layout="wide", page_title="Geospatial Intelligence Dashboard")

@st.cache_resource
def initialize_ee():
    try:
        # Streamlit automatically parses the TOML section into a dictionary
        service_account_info = st.secrets["gcp_service_account"]
        
        # Pass the dictionary directly to the credentials builder
        credentials = service_account.Credentials.from_service_account_info(service_account_info)
        scoped_credentials = credentials.with_scopes(['https://www.googleapis.com/auth/earthengine'])
        
        # Initialize Earth Engine
        ee.Initialize(credentials=scoped_credentials, project=service_account_info["project_id"])
        
    except Exception as e:
        st.error(f"Authentication failed: {e}")
        st.stop()

initialize_ee()

# =========================================================================
# 2. CORE LOGIC (OpenCage + Earth Engine)
# =========================================================================
@st.cache_data(ttl=3600)
def get_coordinates_opencage(query):
    api_key = st.secrets["opencage_api_key"]
    url = f"https://api.opencagedata.com/geocode/v1/json?q={query}&key={api_key}&limit=1"
    try:
        response = requests.get(url).json()
        if response.get('results'):
            lat = response['results'][0]['geometry']['lat']
            lon = response['results'][0]['geometry']['lng']
            return lat, lon
    except Exception as e:
        st.error(f"Geocoding error: {e}")
    return None, None

def mask_s2_clouds(image):
    qa = image.select('QA60')
    cloud_bit_mask = 1 << 10
    cirrus_bit_mask = 1 << 11
    mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
    return image.updateMask(mask)

def add_ee_layer(m, ee_image_object, vis_params, name):
    map_id_dict = ee.Image(ee_image_object).getMapId(vis_params)
    folium.raster_layers.TileLayer(
        tiles=map_id_dict['tile_fetcher'].url_format,
        attr='Google Earth Engine',
        name=name,
        overlay=True,
        control=True
    ).add_to(m)

def create_maps(lat, lon, start1, end1, start2, end2, threshold):
    # ... [Keep the ee logic exactly as it is] ...

    maps = []
    for _ in range(4):
        # Update: Changed height to 450 to fix padding and vertical scrolling
        maps.append(folium.Map(location=[lat, lon], zoom_start=13, tiles='CartoDB dark_matter', height=450))
        
    # ... [Keep the add_ee_layer logic exactly as it is] ...
    return maps

# =========================================================================
# 3. STREAMLIT UI
# =========================================================================

# 6. Security Classification (Centered, Red)
st.markdown("<h3 style='text-align: center; color: red; margin-bottom: 0px;'>UNOFFICIAL</h3>", unsafe_allow_html=True)

# Main Title & 7. Description
st.title("🛰️ Geospatial Intelligence Dashboard")
st.markdown("This dashboard leverages the European Space Agency's Copernicus Programme, specifically the Sentinel-1 and Sentinel-2 missions, to provide a comparison imagery of selected locations across the globe.")

location_query = st.sidebar.text_input("Enter a city, base, or island name:")

# Set default location values
default_lat, default_lon = -35.2809, 149.1300
display_name = "Canberra, Australia" # Default text if no query is made

if location_query:
    lat_res, lon_res = get_coordinates_opencage(location_query)
    if lat_res:
        default_lat, default_lon = lat_res, lon_res
        display_name = location_query.title() # Formats the search query nicely
        st.sidebar.success(f"Found: {display_name}")

# 3. Dynamic Location Display
st.subheader(f"📍 Location: {display_name}")

lat_val = st.sidebar.number_input("Latitude", value=float(default_lat), format="%.6f")
lon_val = st.sidebar.number_input("Longitude", value=float(default_lon), format="%.6f")
threshold_val = st.sidebar.slider("Change Threshold", 0.0, 0.5, 0.10)
d1_val = st.sidebar.date_input("Date 1 (Baseline)", value=date(2025, 6, 1))
d2_val = st.sidebar.date_input("Date 2 (Comparison)", value=date(2026, 6, 1))

if st.sidebar.button("Generate Intelligence Maps", type="primary", use_container_width=True):
    start1, end1 = (d1_val - timedelta(30)).strftime('%Y-%m-%d'), (d1_val + timedelta(30)).strftime('%Y-%m-%d')
    start2, end2 = (d2_val - timedelta(30)).strftime('%Y-%m-%d'), (d2_val + timedelta(30)).strftime('%Y-%m-%d')
    
    with st.spinner("Generating imagery via Google Earth Engine..."):
        maps = create_maps(lat_val, lon_val, start1, end1, start2, end2, threshold_val)
    
    # 5. Helper function for the grey italic captions
    def get_caption(sensor):
        url = f"https://sentiwiki.copernicus.eu/web/{sensor.lower()}"
        return f"<p style='color: grey; font-style: italic; font-size: 0.9em; margin-top: 5px;'>{display_name}. Image captured via Copernicus {sensor}. For further information, see: <a href='{url}' target='_blank'>{url}</a></p>"

    st.write("---") # Adds a subtle divider line before the maps

    # ROW 1 (Maps 1 & 2)
    r1_col1, r1_col2 = st.columns(2)
    
    with r1_col1:
        st.markdown("**Image 1: Baseline via Sentinel-2**")
        # 4. scrolling=False removes the window scrollbars
        components.html(maps[0]._repr_html_(), height=450, scrolling=False) 
        st.markdown(get_caption("Sentinel-2"), unsafe_allow_html=True)
        
    with r1_col2:
        st.markdown("**Image 2: Comparison via Sentinel-2**")
        components.html(maps[1]._repr_html_(), height=450, scrolling=False)
        st.markdown(get_caption("Sentinel-2"), unsafe_allow_html=True)

    st.write("") # Adds a tiny bit of vertical padding between rows

    # ROW 2 (Maps 3 & 4)
    r2_col1, r2_col2 = st.columns(2)
    
    with r2_col1:
        st.markdown("**Image 3: Differences**")
        components.html(maps[2]._repr_html_(), height=450, scrolling=False)
        st.markdown(get_caption("Sentinel-2"), unsafe_allow_html=True)
        
    with r2_col2:
        st.markdown("**Image 4: SAR via Sentinel-1**")
        components.html(maps[3]._repr_html_(), height=450, scrolling=False)
        st.markdown(get_caption("Sentinel-1"), unsafe_allow_html=True)
