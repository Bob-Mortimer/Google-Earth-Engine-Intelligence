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

default_lat, default_lon = -35.2809, 149.1300
display_name = "Canberra, Australia" 

if location_query:
    lat_res, lon_res = get_coordinates_opencage(location_query)
    if lat_res:
        default_lat, default_lon = lat_res, lon_res
        display_name = location_query.title()
        st.sidebar.success(f"Found: {display_name}")

# 3. Dynamic Location Display
st.subheader(f"📍 Location: {display_name}")

lat_val = st.sidebar.number_input("Latitude", value=float(default_lat), format="%.6f")
lon_val = st.sidebar.number_input("Longitude", value=float(default_lon), format="%.6f")
threshold_val = st.sidebar.slider("Change Threshold", 0.0, 0.5, 0.10)
d1_val = st.sidebar.date_input("Date 1 (Baseline)", value=date(2025, 6, 1))
d2_val = st.sidebar.date_input("Date 2 (Comparison)", value=date(2026, 6, 1))

if st.sidebar.button("Generate Intelligence Maps", type="primary", use_container_width=True):
    start1, end1 = (d1_val - timedelta(90)).strftime('%Y-%m-%d'), (d1_val + timedelta(90)).strftime('%Y-%m-%d')
    start2, end2 = (d2_val - timedelta(90)).strftime('%Y-%m-%d'), (d2_val + timedelta(90)).strftime('%Y-%m-%d')
    
    with st.spinner("Generating imagery via Google Earth Engine..."):
        maps = create_maps(lat_val, lon_val, start1, end1, start2, end2, threshold_val)
    
    st.write("---") 

    # THE LAYOUT FIX: Single HTML block renderer to bypass all Streamlit spacing issues
    def render_map_card(title, map_obj, sensor, height=450):
        # .get_root().render() extracts raw HTML, avoiding Streamlit's double-iframe trap
        map_html = map_obj.get_root().render()
        url = f"https://sentiwiki.copernicus.eu/web/{sensor.lower()}"
        
        # HTML/CSS packaging for pixel-perfect spacing and dark-theme matching
        custom_html = f"""
        <html>
        <head>
            <style>
                body {{
                    margin: 0; padding: 0;
                    font-family: 'Source Sans Pro', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background-color: #0E1117; /* Matches Streamlit's dark mode background */
                    color: rgb(250, 250, 250);
                }}
                .card-container {{
                    display: flex; flex-direction: column; gap: 8px; /* Tightly controls gap between text and map */
                }}
                h4 {{ margin: 0; font-size: 1.1rem; font-weight: 600; padding-top: 5px;}}
                p {{ margin: 0; color: #9e9e9e; font-style: italic; font-size: 0.85rem; padding-bottom: 5px;}}
                a {{ color: #4da6ff; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <div class="card-container">
                <h4>{title}</h4>
                <div style="width: 100%; height: {height}px; border-radius: 5px; overflow: hidden; border: 1px solid #333;">
                    {map_html}
                </div>
                <p>{display_name}. Image captured via Copernicus {sensor}. For further information, see: <a href="{url}" target="_blank">{url}</a></p>
            </div>
        </body>
        </html>
        """
        # Height is map height + text buffer. scrolling=False kills the scroll wheels.
        components.html(custom_html, height=height + 80, scrolling=False)

    # ---------------------------------------------------------
    # RENDER THE UI
    # ---------------------------------------------------------
    r1_col1, r1_col2 = st.columns(2)
    with r1_col1:
        render_map_card("Image 1: Baseline via Sentinel-2", maps[0], "Sentinel-2")
    with r1_col2:
        render_map_card("Image 2: Comparison via Sentinel-2", maps[1], "Sentinel-2")

    r2_col1, r2_col2 = st.columns(2)
    with r2_col1:
        render_map_card("Image 3: Differences", maps[2], "Sentinel-2")
    with r2_col2:
        render_map_card("Image 4: SAR via Sentinel-1", maps[3], "Sentinel-1")
