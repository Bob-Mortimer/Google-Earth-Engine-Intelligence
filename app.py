import streamlit as st
import ee
import folium
import streamlit.components.v1 as components
from datetime import date, timedelta
from geopy.geocoders import Nominatim

# =========================================================================
# 1. PAGE CONFIGURATION & CUSTOM CSS
# =========================================================================
st.set_page_config(layout="wide", page_title="Geospatial Intelligence Dashboard")

# Inject highly targeted custom CSS to tighten up the dead space without breaking the sidebar
st.markdown("""
    <style>
        /* Reduce the huge default padding at the top of the page */
        .block-container { padding-top: 2rem; padding-bottom: 1rem; }
        
        /* Scope our spacing fixes ONLY to the layout columns (leaving the sidebar and header alone) */
        [data-testid="column"] h3 { 
            padding-bottom: 0rem !important; 
            margin-bottom: -15px !important; 
            padding-top: 0.5rem !important;
        }
        
        /* Aggressively reduce the vertical gap between rows in the map columns */
        [data-testid="column"] [data-testid="stVerticalBlock"] {
            gap: 0rem !important;
        }
        
        /* Squeeze the bottom margin of the map iframe containers */
        [data-testid="column"] .element-container {
            margin-bottom: -25px !important;
        }
    </style>
""", unsafe_allow_html=True)

st.title("🛰️ Geospatial Intelligence Dashboard")
st.markdown("Monitor urban expansion and maritime changes using Sentinel-2 (Optical) and Sentinel-1 (SAR) satellite data.")

# =========================================================================
# 2. EARTH ENGINE INITIALIZATION
# =========================================================================
@st.cache_resource
def initialize_ee():
    try:
        # Streamlit Cloud deployment: Use secrets provided in the Streamlit Dashboard
        credentials = ee.ServiceAccountCredentials(
            st.secrets["ee_client_email"], 
            st.secrets["ee_private_key"]
        )
        ee.Initialize(credentials, project=st.secrets["ee_project_id"])
    except Exception:
        # Local development fallback
        MY_PROJECT_ID = 'YOUR_PROJECT_ID_HERE' 
        try:
            ee.Initialize(project=MY_PROJECT_ID)
        except:
            ee.Authenticate()
            ee.Initialize(project=MY_PROJECT_ID)

initialize_ee()

# =========================================================================
# 3. CORE LOGIC
# =========================================================================
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
    # Force Folium maps to 600px height for maximum real estate
    for _ in range(4):
        maps.append(folium.Map(location=[lat, lon], zoom_start=13, tiles='CartoDB dark_matter', height=600))

    add_ee_layer(maps[0], s2_2025, {'bands': ['B4', 'B3', 'B2'], 'min': 0.0, 'max': 0.3}, 'Date 1 Optical')
    add_ee_layer(maps[1], s2_2026, {'bands': ['B4', 'B3', 'B2'], 'min': 0.0, 'max': 0.3}, 'Date 2 Optical')
    add_ee_layer(maps[2], s2_2026, {'bands': ['B4', 'B3', 'B2'], 'min': 0.0, 'max': 0.3}, 'Background')
    add_ee_layer(maps[2], urban_expansion, {'palette': ['FF0000']}, 'Change Overlay')
    add_ee_layer(maps[3], sar_2026, {'bands': ['VV'], 'min': -20.0, 'max': 0.0}, 'Date 2 SAR')

    return maps

# =========================================================================
# 4. STREAMLIT UI & LAYOUT
# =========================================================================
st.sidebar.header("Dashboard Parameters")

st.sidebar.subheader("1. Location Search")
location_query = st.sidebar.text_input("Enter a city, base, or island name:")

default_lat = -35.2809
default_lon = 149.1300

if location_query:
    geolocator = Nominatim(user_agent="geo_intelligence_dashboard")
    try:
        loc = geolocator.geocode(location_query)
        if loc:
            default_lat = loc.latitude
            default_lon = loc.longitude
            st.sidebar.success(f"Found: {loc.address}")
        else:
            st.sidebar.warning("Location not found. Please check spelling or use coordinates below.")
    except Exception:
        st.sidebar.error("Geocoding service unavailable.")

st.sidebar.subheader("2. Exact Coordinates")
lat_val = st.sidebar.number_input("Latitude", value=float(default_lat), format="%.6f")
lon_val = st.sidebar.number_input("Longitude", value=float(default_lon), format="%.6f")

st.sidebar.markdown("---")
threshold_val = st.sidebar.slider("Change Threshold", min_value=0.0, max_value=0.5, value=0.10, step=0.01)

d1_val = st.sidebar.date_input("Date 1 (Baseline)", value=date(2025, 6, 1))
d2_val = st.sidebar.date_input("Date 2 (Comparison)", value=date(2026, 6, 1))

run_button = st.sidebar.button("Generate Intelligence Maps", type="primary", use_container_width=True)

if run_button:
    with st.spinner('Accessing Copernicus satellites...'):
        start1 = (d1_val - timedelta(days=30)).strftime('%Y-%m-%d')
        end1 = (d1_val + timedelta(days=30)).strftime('%Y-%m-%d')
        start2 = (d2_val - timedelta(days=30)).strftime('%Y-%m-%d')
        end2 = (d2_val + timedelta(days=30)).strftime('%Y-%m-%d')
        
        maps = create_maps(lat_val, lon_val, start1, end1, start2, end2, threshold_val)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader(f"1. Optical ({d1_val.strftime('%b %d, %Y')})")
            components.html(maps[0]._repr_html_(), height=610)
            st.subheader("3. Change Detection Overlay")
            components.html(maps[2]._repr_html_(), height=610)
            
        with col2:
            st.subheader(f"2. Optical ({d2_val.strftime('%b %d, %Y')})")
            components.html(maps[1]._repr_html_(), height=610)
            st.subheader(f"4. SAR VV ({d2_val.strftime('%b %d, %Y')})")
            components.html(maps[3]._repr_html_(), height=610)
else:
    st.info("👈 Adjust parameters and click **Generate Intelligence Maps**.")