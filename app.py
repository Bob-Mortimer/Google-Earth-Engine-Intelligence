import streamlit as st
import ee
import folium
import streamlit.components.v1 as components
from datetime import date, timedelta
import requests
import json
import os

# =========================================================================
# 1. PAGE CONFIGURATION & INITIALIZATION
# =========================================================================
st.set_page_config(layout="wide", page_title="Geospatial Intelligence Dashboard")

@st.cache_resource
def initialize_ee():
    try:
        # Retrieve secrets
        client_email = st.secrets["ee_client_email"]
        project_id = st.secrets["ee_project_id"]
        
        # Access the private key string
        raw_key = st.secrets["ee_private_key"]
        
        # Ensure the key is properly formatted as a string with newlines
        # We strip potential surrounding quotes and replace escaped newlines
        private_key = raw_key.strip('"').replace('\\n', '\n')
        
        # Use a service account dict approach which is more reliable for Cloud
        service_account_info = {
            "client_email": client_email,
            "private_key": private_key,
            "project_id": project_id
        }
        
        # Authenticate using the dictionary-based service account info
        credentials = ee.ServiceAccountCredentials(
            client_email,
            key_data=private_key
        )
        ee.Initialize(credentials, project=project_id)
        
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
    center_point = ee.Geometry.Point([lon, lat])
    s2_col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(center_point).map(mask_s2_clouds)
    s2_2025 = s2_col.filterDate(start1, end1).median().divide(10000)
    s2_2026 = s2_col.filterDate(start2, end2).median().divide(10000)
    urban_expansion = s2_2026.normalizedDifference(['B11', 'B8']).subtract(s2_2025.normalizedDifference(['B11', 'B8'])).gt(threshold).selfMask()
    sar_2026 = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(center_point).filterDate(start2, end2).filter(ee.Filter.eq('instrumentMode', 'IW')).select('VV').median()

    maps = []
    for _ in range(4):
        maps.append(folium.Map(location=[lat, lon], zoom_start=13, tiles='CartoDB dark_matter', height=600))
    add_ee_layer(maps[0], s2_2025, {'bands': ['B4', 'B3', 'B2'], 'min': 0.0, 'max': 0.3}, 'Date 1 Optical')
    add_ee_layer(maps[1], s2_2026, {'bands': ['B4', 'B3', 'B2'], 'min': 0.0, 'max': 0.3}, 'Date 2 Optical')
    add_ee_layer(maps[2], s2_2026, {'bands': ['B4', 'B3', 'B2'], 'min': 0.0, 'max': 0.3}, 'Background')
    add_ee_layer(maps[2], urban_expansion, {'palette': ['FF0000']}, 'Change Overlay')
    add_ee_layer(maps[3], sar_2026, {'bands': ['VV'], 'min': -20.0, 'max': 0.0}, 'Date 2 SAR')
    return maps

# =========================================================================
# 3. STREAMLIT UI
# =========================================================================
st.title("🛰️ Geospatial Intelligence Dashboard")
location_query = st.sidebar.text_input("Enter a city, base, or island name:")

default_lat, default_lon = -35.2809, 149.1300
if location_query:
    lat_res, lon_res = get_coordinates_opencage(location_query)
    if lat_res:
        default_lat, default_lon = lat_res, lon_res
        st.sidebar.success(f"Found: {location_query}")

lat_val = st.sidebar.number_input("Latitude", value=float(default_lat), format="%.6f")
lon_val = st.sidebar.number_input("Longitude", value=float(default_lon), format="%.6f")
threshold_val = st.sidebar.slider("Change Threshold", 0.0, 0.5, 0.10)
d1_val = st.sidebar.date_input("Date 1 (Baseline)", value=date(2025, 6, 1))
d2_val = st.sidebar.date_input("Date 2 (Comparison)", value=date(2026, 6, 1))

if st.sidebar.button("Generate Intelligence Maps", type="primary", use_container_width=True):
    start1, end1 = (d1_val - timedelta(30)).strftime('%Y-%m-%d'), (d1_val + timedelta(30)).strftime('%Y-%m-%d')
    start2, end2 = (d2_val - timedelta(30)).strftime('%Y-%m-%d'), (d2_val + timedelta(30)).strftime('%Y-%m-%d')
    maps = create_maps(lat_val, lon_val, start1, end1, start2, end2, threshold_val)
    c1, c2 = st.columns(2)
    with c1:
        components.html(maps[0]._repr_html_(), height=610)
        components.html(maps[2]._repr_html_(), height=610)
    with c2:
        components.html(maps[1]._repr_html_(), height=610)
        components.html(maps[3]._repr_html_(), height=610)
