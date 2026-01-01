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
st.title("🛰️ Visor Satelital (Modo Todoterreno)")

# --- Barra Lateral ---
st.sidebar.header("Opciones")
channel = st.sidebar.selectbox(
    "Canal", 
    ["13 (Infrarrojo)", "02 (Visible)", "09 (Vapor de Agua)"], 
    index=0
)

st.sidebar.markdown("---")
st.sidebar.header("Fecha y Hora (UTC)")
use_manual = st.sidebar.checkbox("Usar fecha específica", value=True)

if use_manual:
    # Usamos 31 Dic 2025 por defecto para asegurar datos históricos
    date_input = st.sidebar.date_input("Fecha", datetime(2025, 12, 31))
    hour_input = st.sidebar.slider("Hora UTC", 0, 23, 16)
else:
    now = datetime.utcnow()
    date_input = now
    hour_input = now.hour
    st.sidebar.info("Modo Tiempo Real")

channel_id = {"13 (Infrarrojo)": "C13", "02 (Visible)": "C02", "09 (Vapor de Agua)": "C09"}[channel]

# --- NUEVA FUNCIÓN DE BÚSQUEDA (MODO TODOTERRENO) ---
def find_file_via_http_bruteforce(bucket, year, doy, hour, ch_id):
    # Construir URL del índice
    prefix = f"ABI-L2-CMIPF/{year}/{doy:03d}/{hour:02d}/"
    url = f"https://{bucket}.s3.amazonaws.com/?list-type=2&prefix={prefix}"
    
    try:
        # Descargar XML
        response = urlopen(url, timeout=10) # Timeout para que no se cuelgue
        xml_content = response.read()
        
        # Leer XML
        root = ET.fromstring(xml_content)
        
        files = []
        # BÚSQUEDA MANUAL SIN NAMESPACES (Esto soluciona el error anterior)
        # Recorremos cada elemento del XML sin importar cómo se llame
        for child in root:
            # Buscamos los bloques que contienen archivos (suelen terminar en 'Contents')
            if child.tag.endswith('Contents'):
                # Dentro del bloque, buscamos la llave (Key)
                for item in child:
                    if item.tag.endswith('Key'):
                        filename = item.text
                        # Filtramos si es del canal que queremos
                        if f"M6{ch_id}" in filename or f"M3{ch_id}" in filename:
                            files.append(filename)
        
        if not files:
            return None
        
        # Devolver el último (el más reciente de esa hora)
        return files[-1]
        
    except Exception as e:
        st.error(f"Error leyendo índice NOAA: {e}")
        return None

# --- Función de Descarga ---
@st.cache_data(ttl=600)
def get_satellite_data(tgt_date, tgt_hour, ch_id):
    bucket_name = "noaa-goes16"
    year = tgt_date.year
    doy = tgt_date.timetuple().tm_yday
    
    # 1. Encontrar archivo con el método nuevo
    file_key = find_file_via_http_bruteforce(bucket_name, year, doy, tgt_hour, ch_id)
    
    if not file_key:
        return None, "No se encontraron archivos (índice vacío)."

    # 2. Descargar
    fs = s3fs.S3FileSystem(anon=True)
    full_path = f"s3://{bucket_name}/{file_key}"
    
    try:
        # Abrimos directo el archivo conocido
        remote_file = fs.open(full_path)
        ds = xr.open_dataset(remote_file, engine='h5netcdf')
        data = ds['CMI'].values
        
        # Recorte (Zoom Cono Sur aproximado)
        if ch_id == "C02": # Visible
            h, w = data.shape
            # Recorte más centrado
            data = data[int(h*0.55):int(h*0.85), int(w*0.35):int(w*0.65)]
        else: # IR / Vapor
            data = data[3200:4800, 1800:3200]
            
        return data, file_key
        
    except Exception as e:
        return None, f"Error al abrir el archivo: {e}"

# --- Visualización ---
if st.button("🔄 Cargar Imagen", use_container_width=True):
    st.rerun()

st.caption(f"Consultando: {date_input} | {hour_input}:00 UTC")

with st.spinner("Conectando..."):
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
            # Aumentar contraste en visible
            img = np.power(img, 0.7) 
        else:
            cmap = 'coolwarm'
            vmin, vmax = 200, 270

        ax.imshow(img, cmap=cmap, vmin=vmin, vmax=vmax)
        
        fname = msg.split('/')[-1] if msg else "Imagen"
        ax.set_title(f"GOES-16 {channel}\n{fname}", fontsize=8)
        ax.axis('off')
        
        st.pyplot(fig, use_container_width=True)
        st.success("✅ ¡Imagen cargada!")
