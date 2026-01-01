import streamlit as st
import matplotlib.pyplot as plt
import xarray as xr
import s3fs
import numpy as np
from datetime import datetime
import xml.etree.ElementTree as ET
from urllib.request import urlopen

# --- Configuración Inicial ---
st.set_page_config(page_title="Satélite GOES-16", layout="centered")
st.title("🛰️ Visor Satelital (Conexión Directa)")

# --- Barra Lateral ---
st.sidebar.header("Opciones")
channel = st.sidebar.selectbox(
    "Canal", 
    ["13 (Infrarrojo)", "02 (Visible)", "09 (Vapor de Agua)"], 
    index=0
)

# Selección de fecha
st.sidebar.markdown("---")
st.sidebar.header("Fecha y Hora (UTC)")
use_manual = st.sidebar.checkbox("Usar fecha específica", value=True)

if use_manual:
    # Ponemos por defecto el 31 de Diciembre 2025 para asegurar que hay datos
    date_input = st.sidebar.date_input("Fecha", datetime(2025, 12, 31))
    hour_input = st.sidebar.slider("Hora UTC", 0, 23, 18)
else:
    now = datetime.utcnow()
    date_input = now
    hour_input = now.hour
    st.sidebar.info("Modo Tiempo Real")

# Mapeo de canales
channel_id = {"13 (Infrarrojo)": "C13", "02 (Visible)": "C02", "09 (Vapor de Agua)": "C09"}[channel]

# --- NUEVA FUNCIÓN DE BÚSQUEDA (El Truco HTTP) ---
def find_file_via_http(bucket, year, doy, hour, ch_id):
    # En lugar de usar s3fs para listar, usamos la web directa de Amazon
    prefix = f"ABI-L2-CMIPF/{year}/{doy:03d}/{hour:02d}/"
    url = f"https://{bucket}.s3.amazonaws.com/?list-type=2&prefix={prefix}"
    
    try:
        # Descargar el índice XML
        response = urlopen(url)
        xml_content = response.read()
        
        # Leer el XML
        root = ET.fromstring(xml_content)
        # El espacio de nombres de AWS XML
        ns = {'aws': 'http://s3.amazonaws.com/doc/2006-03-01/'}
        
        # Buscar todos los archivos (Keys)
        files = []
        for contents in root.findall('aws:Contents', ns):
            key = contents.find('aws:Key', ns).text
            if f"M6{ch_id}" in key or f"M3{ch_id}" in key:
                files.append(key)
        
        if not files:
            return None
        
        # Devolver el último (el más reciente)
        return files[-1]
        
    except Exception as e:
        st.error(f"Error HTTP: {e}")
        return None

# --- Función de Descarga ---
@st.cache_data(ttl=600)
def get_satellite_data(tgt_date, tgt_hour, ch_id):
    bucket_name = "noaa-goes16"
    year = tgt_date.year
    doy = tgt_date.timetuple().tm_yday
    
    # 1. ENCONTRAR EL NOMBRE DEL ARCHIVO (Usando el método HTTP seguro)
    file_key = find_file_via_http(bucket_name, year, doy, tgt_hour, ch_id)
    
    if not file_key:
        return None, "No se encontraron archivos en el índice web de NOAA."

    # 2. DESCARGAR EL ARCHIVO (Usando s3fs solo para abrir, no para buscar)
    fs = s3fs.S3FileSystem(anon=True)
    full_path = f"s3://{bucket_name}/{file_key}"
    
    try:
        remote_file = fs.open(full_path)
        ds = xr.open_dataset(remote_file, engine='h5netcdf')
        data = ds['CMI'].values
        
        # Recorte para centrar y optimizar memoria
        if ch_id == "C02": # Visible
            h, w = data.shape
            # Recorte aproximado centro-sur
            data = data[int(h*0.5):int(h*0.8), int(w*0.3):int(w*0.7)]
        else: # IR
            data = data[3000:4800, 1500:3500]
            
        return data, file_key
        
    except Exception as e:
        return None, f"Error al abrir el archivo: {e}"

# --- Visualización ---
if st.button("🔄 Cargar Imagen", use_container_width=True):
    st.rerun()

st.caption(f"Consultando: {date_input} | {hour_input}:00 UTC")

with st.spinner("Conectando vía HTTP..."):
    img, msg = get_satellite_data(date_input, hour_input, channel_id)
    
    if img is None:
        st.error(f"❌ {msg}")
    else:
        fig, ax = plt.subplots(figsize=(10, 10))
        
        # Paletas
        if channel_id == "C13":
            cmap = 'turbo_r' 
            vmin, vmax = 180, 300
            img = np.clip(img, vmin, vmax)
        elif channel_id == "C02":
            cmap = 'gray'
            vmin, vmax = 0, 1
        else:
            cmap = 'coolwarm'
            vmin, vmax = 200, 270

        ax.imshow(img, cmap=cmap, vmin=vmin, vmax=vmax)
        
        # Limpiar nombre para el título
        fname = msg.split('/')[-1] if msg else "Imagen"
        ax.set_title(f"GOES-16 {channel}\n{fname}", fontsize=8)
        ax.axis('off')
        
        st.pyplot(fig, use_container_width=True)
        st.success("✅ ¡Conexión Exitosa!")
