import streamlit as st
import matplotlib.pyplot as plt
import xarray as xr
import s3fs
import numpy as np
from datetime import datetime, timedelta

# --- Configuración ---
st.set_page_config(page_title="Satélite Lite", layout="centered", initial_sidebar_state="expanded")
st.title("🛰️ Satélite GOES-16 (Modo Manual)")

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
    hour_input = st.sidebar.slider("Hora (UTC)", 0, 23, datetime.utcnow().hour)
else:
    st.sidebar.info("Modo: Tiempo Real (Última hora)")
    # Fecha actual automática
    now = datetime.utcnow()
    date_input = now
    hour_input = now.hour

# Mapeo de canales
channel_id = {
    "13 (Infrarrojo)": "C13",
    "02 (Visible)": "C02",
    "09 (Vapor de Agua)": "C09"
}[channel]

# --- Función de Descarga ---
@st.cache_data(ttl=600)
def get_image(selected_channel, target_date, target_hour):
    fs = s3fs.S3FileSystem(anon=True)
    bucket = "noaa-goes16/ABI-L2-CMIPF"
    
    # Calcular día del año (Day of Year)
    year = target_date.year
    day_of_year = target_date.timetuple().tm_yday
    
    # Construir ruta
    path = f"{bucket}/{year}/{day_of_year:03d}/{target_hour:02d}/"
    
    # Listar archivos
    try:
        files = fs.ls(path)
    except Exception as e:
        return None, f"No se encontró la carpeta: {path}"
        
    if not files:
        return None, f"Carpeta vacía: {path}"

    # Buscar el archivo del canal correcto
    c_files = [f for f in files if f"M6{selected_channel}" in f or f"M3{selected_channel}" in f]
    
    if not c_files:
        # Si no hay imagen, intentamos buscar 10 min antes (o un archivo cualquiera de esa hora)
        return None, f"No hay imágenes del canal {selected_channel} en esta hora."
    
    # Tomamos el último archivo disponible de esa hora
    file_to_open = c_files[-1]
    
    try:
        f = fs.open(file_to_open)
        ds = xr.open_dataset(f, engine='h5netcdf')
        data = ds['CMI'].values
        
        # Recorte simple para Sudamérica (Aprox)
        # Full Disk es 5424x5424.
        if selected_channel == "C02": # Visible tiene más resolución (aprox 10000x10000 o más según modo)
             # Recorte proporcional seguro para evitar error de indices
             data = data[6000:9000, 3000:6000] if data.shape[0] > 6000 else data
        else:
             # IR/WV (5424x5424) -> Recorte Cono Sur aprox
             data = data[3000:4800, 1500:3500]
             
        return data, file_to_open
    except Exception as e:
        return None, f"Error leyendo archivo: {e}"

# --- Visualización ---
if st.button("🔄 Actualizar Imagen", use_container_width=True):
    st.rerun()

with st.spinner(f"Buscando imagen: {date_input} - {hour_input}:00 UTC..."):
    img_data, msg = get_image(channel_id, date_input, hour_input)
    
    if img_data is None:
        st.error(f"❌ Error: {msg}")
        if not use_manual:
            st.warning("💡 Prueba activando 'Seleccionar fecha manual' y buscando una hora anterior.")
    else:
        fig, ax = plt.subplots(figsize=(10, 10))
        
        # Colores
        cmap = 'viridis'
        vmin, vmax = None, None
        
        if channel_id == "C13":
            cmap = 'turbo_r' # Invertido para nubes frías
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
        ax.set_title(f"GOES-16 {channel}\n{msg.split('/')[-1]}", fontsize=8)
        
        st.pyplot(fig, use_container_width=True)
        st.success("✅ Imagen cargada correctamente") 
