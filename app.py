import streamlit as st
import matplotlib.pyplot as plt
import xarray as xr
import s3fs
import numpy as np
from datetime import datetime

# --- Configuración ---
st.set_page_config(page_title="Satélite Lite", layout="centered", initial_sidebar_state="expanded")
st.title("🛰️ Satélite GOES-16 (Conectado)")

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

# Si no es manual, usamos AHORA
if use_manual:
    date_input = st.sidebar.date_input("Fecha", datetime.utcnow())
    hour_input = st.sidebar.slider("Hora (UTC)", 0, 23, 16) # Por defecto 16 UTC
else:
    st.sidebar.info("Modo: Tiempo Real (Última hora)")
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
    # NOTA: Agregamos client_kwargs para asegurar conexión anónima
    fs = s3fs.S3FileSystem(anon=True)
    
    bucket = "noaa-goes16/ABI-L2-CMIPF"
    
    year = target_date.year
    day_of_year = target_date.timetuple().tm_yday
    
    # --- CORRECCIÓN CLAVE: Agregamos 's3://' al principio ---
    path = f"s3://{bucket}/{year}/{day_of_year:03d}/{target_hour:02d}/"
    
    try:
        # Intentamos listar los archivos
        files = fs.ls(path)
    except Exception as e:
        return None, f"No se pudo conectar a la carpeta: {path}. Error: {e}"
        
    if not files:
        return None, f"La carpeta existe pero está vacía: {path}"

    # Buscar el archivo del canal correcto
    c_files = [f for f in files if f"M6{selected_channel}" in f or f"M3{selected_channel}" in f]
    
    if not c_files:
        return None, f"No hay imágenes del canal {selected_channel} en la hora {target_hour} UTC."
    
    # Tomamos el último archivo
    file_to_open = c_files[-1]
    
    try:
        # Abrimos también con s3:// explícito por seguridad
        if not file_to_open.startswith("noaa-goes16"): 
            # A veces fs.ls devuelve rutas relativas, a veces absolutas
            file_to_open = file_to_open
        
        # Truco: fs.open maneja s3:// automático si el fs se creó con s3fs
        f = fs.open(f"s3://{file_to_open}" if not file_to_open.startswith("s3://") else file_to_open)
        
        ds = xr.open_dataset(f, engine='h5netcdf')
        data = ds['CMI'].values
        
        # Recorte para Sudamérica (Indices aproximados para Full Disk)
        # Full Disk es 5424x5424 pixeles aprox en IR
        if selected_channel == "C02": 
             # Visible es mas grande, recortamos diferente
             data = data[6000:9000, 3000:6000] if data.shape[0] > 6000 else data
        else:
             # IR/WV
             data = data[3000:4800, 1500:3500]
             
        return data, file_to_open
    except Exception as e:
        return None, f"Error leyendo archivo: {e}"

# --- Visualización ---
if st.button("🔄 Actualizar Imagen", use_container_width=True):
    st.rerun()

# Texto de estado
st.caption(f"Buscando: {date_input} | Hora: {hour_input}:00 UTC")

with st.spinner("Descargando desde la nube de NOAA..."):
    img_data, msg = get_image(channel_id, date_input, hour_input)
    
    if img_data is None:
        st.error(f"❌ {msg}")
        if use_manual:
             st.warning("Prueba con una hora anterior (recuerda que es hora UTC, +3 horas respecto a Argentina).")
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
        
        # Limpiamos el nombre del archivo para el título
        clean_name = msg.split('/')[-1] if isinstance(msg, str) else "Imagen"
        ax.set_title(f"GOES-16 {channel}\n{clean_name}", fontsize=8)
        
        st.pyplot(fig, use_container_width=True)
        st.success("✅ Imagen cargada")
