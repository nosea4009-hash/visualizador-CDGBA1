import streamlit as st
import matplotlib.pyplot as plt
import xarray as xr
import s3fs
import numpy as np
from datetime import datetime

# --- Configuración ---
st.set_page_config(page_title="Satélite Lite", layout="centered", initial_sidebar_state="expanded")
st.title("🛰️ Satélite GOES-16 (Región Fija)")

# --- Sidebar ---
st.sidebar.header("📡 Configuración")
channel = st.sidebar.selectbox(
    "Canal", 
    ["13 (Infrarrojo)", "02 (Visible)", "09 (Vapor de Agua)"], 
    index=0
)

# Selector de Fecha y Hora Manual
st.sidebar.markdown("---")
st.sidebar.header("🕒 Control de Tiempo")
use_manual = st.sidebar.checkbox("Seleccionar fecha manual", value=False)

if use_manual:
    date_input = st.sidebar.date_input("Fecha", datetime.utcnow())
    hour_input = st.sidebar.slider("Hora (UTC)", 0, 23, 16)
else:
    st.sidebar.info("Modo: Tiempo Real (Última hora)")
    now = datetime.utcnow()
    date_input = now
    hour_input = now.hour

channel_id = {
    "13 (Infrarrojo)": "C13",
    "02 (Visible)": "C02",
    "09 (Vapor de Agua)": "C09"
}[channel]

# --- Función de Descarga ---
@st.cache_data(ttl=600)
def get_image(selected_channel, target_date, target_hour):
    # --- CORRECCIÓN IMPORTANTE AQUÍ ABAJO ---
    # Especificamos 'us-east-1' para que no falle al encontrar el bucket público
    fs = s3fs.S3FileSystem(anon=True, client_kwargs={'region_name': 'us-east-1'})
    
    bucket = "noaa-goes16/ABI-L2-CMIPF"
    year = target_date.year
    day_of_year = target_date.timetuple().tm_yday
    
    # Ruta sin s3:// al principio para .ls (s3fs lo prefiere así a veces)
    path = f"{bucket}/{year}/{day_of_year:03d}/{target_hour:02d}/"
    
    try:
        files = fs.ls(path)
    except Exception as e:
        return None, f"No se pudo acceder a la ruta: {path}. Error: {e}"
        
    if not files:
        return None, f"Carpeta vacía o no existe: {path}"

    # Filtrar archivo
    c_files = [f for f in files if f"M6{selected_channel}" in f or f"M3{selected_channel}" in f]
    
    if not c_files:
        return None, f"No hay imágenes del canal {selected_channel} en la hora {target_hour} UTC."
    
    file_to_open = c_files[-1]
    
    try:
        # Aquí sí usamos s3:// para abrirlo
        f = fs.open(f"s3://{file_to_open}")
        ds = xr.open_dataset(f, engine='h5netcdf')
        data = ds['CMI'].values
        
        # Recorte (Zoom aproximado a Sudamérica)
        if selected_channel == "C02": 
             data = data[6000:9000, 3000:6000] if data.shape[0] > 6000 else data
        else:
             data = data[3000:4800, 1500:3500]
             
        return data, file_to_open
    except Exception as e:
        return None, f"Error leyendo archivo: {e}"

# --- Visualización ---
if st.button("🔄 Actualizar Imagen", use_container_width=True):
    st.rerun()

st.caption(f"Buscando: {date_input} | Hora: {hour_input}:00 UTC")

with st.spinner("Conectando con NOAA (US-EAST-1)..."):
    img_data, msg = get_image(channel_id, date_input, hour_input)
    
    if img_data is None:
        st.error(f"❌ {msg}")
        if use_manual:
             st.warning("Intenta probar con una fecha del 2025 (ej. 31 Dic) para verificar.")
    else:
        fig, ax = plt.subplots(figsize=(10, 10))
        
        # Colores
        cmap = 'viridis'
        vmin, vmax = None, None
        
        if channel_id == "C13":
            cmap = 'turbo_r' 
            vmin, vmax = 180, 300
            img_data = np.clip(img_data, vmin, vmax)
        elif channel_id == "C02":
            cmap = 'gray'
            vmin, vmax = 0, 1
        elif channel_id == "C09":
            cmap = 'coolwarm'
            vmin, vmax = 200, 270
        
        ax.imshow(img_data, cmap=cmap, vmin=vmin, vmax=vmax)
        ax.axis('off')
        
        clean_name = msg.split('/')[-1] if isinstance(msg, str) else "Imagen"
        ax.set_title(f"GOES-16 {channel}\n{clean_name}", fontsize=8)
        
        st.pyplot(fig, use_container_width=True)
        st.success("✅ Conexión Exitosa")
