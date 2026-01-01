import streamlit as st
import matplotlib.pyplot as plt
import xarray as xr
import s3fs
import numpy as np
from datetime import datetime

# --- Configuración Inicial ---
st.set_page_config(page_title="Satélite GOES", layout="centered")
st.title("🛰️ Visor Satelital GOES-16")

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
    date_input = st.sidebar.date_input("Fecha", datetime(2025, 12, 31)) # Default 31 Dic 2025 (Seguro)
    hour_input = st.sidebar.slider("Hora UTC", 0, 23, 18)
else:
    now = datetime.utcnow()
    date_input = now
    hour_input = now.hour
    st.sidebar.info("Modo Tiempo Real")

# Botón de prueba técnica
st.sidebar.markdown("---")
test_mode = st.sidebar.checkbox("🛠️ Modo Prueba (Sin Internet)", value=False)

# Mapeo de canales
channel_id = {"13 (Infrarrojo)": "C13", "02 (Visible)": "C02", "09 (Vapor de Agua)": "C09"}[channel]

# --- Función Principal ---
@st.cache_data(ttl=600)
def get_satellite_data(tgt_date, tgt_hour, ch_id):
    # 1. Conexión Anónima
    fs = s3fs.S3FileSystem(anon=True)
    
    # 2. Construir ruta CON el prefijo s3:// (Esto era lo que fallaba antes)
    bucket = "noaa-goes16/ABI-L2-CMIPF"
    year = tgt_date.year
    doy = tgt_date.timetuple().tm_yday
    
    # Ruta de la CARPETA
    folder_path = f"s3://{bucket}/{year}/{doy:03d}/{tgt_hour:02d}/"
    
    try:
        # Listar archivos en la nube
        files = fs.ls(folder_path)
    except Exception as e:
        return None, f"Error de conexión: {e}"
        
    if not files:
        return None, "La carpeta existe pero está vacía."

    # Filtrar por el canal seleccionado (M6 o M3)
    target_files = [f for f in files if f"M6{ch_id}" in f or f"M3{ch_id}" in f]
    
    if not target_files:
        return None, "No hay imágenes para este canal en esta hora."
        
    # Tomar el último archivo
    file_path = target_files[-1]
    
    # Asegurarnos de que tenga s3:// para abrirlo
    if not file_path.startswith("s3://"):
        file_path = "s3://" + file_path
        
    try:
        # Abrir archivo remoto
        remote_file = fs.open(file_path)
        ds = xr.open_dataset(remote_file, engine='h5netcdf')
        data = ds['CMI'].values
        
        # Recorte simple para centrar en Sudamérica y reducir memoria
        # (Los índices dependen de si es canal visible o IR)
        if ch_id == "C02": # Visible (matriz gigante)
            # Recorte seguro
            h, w = data.shape
            data = data[int(h*0.5):int(h*0.9), int(w*0.3):int(w*0.7)]
        else: # IR (5424x5424)
            data = data[3000:4800, 1500:3500]
            
        return data, file_path
        
    except Exception as e:
        return None, f"Error al descargar la imagen: {e}"

# --- Visualización ---
if test_mode:
    # --- MODO PRUEBA (Para verificar que tu código plotea bien) ---
    st.warning("⚠️ MODO PRUEBA: Esto es un gráfico generado, no es real.")
    fig, ax = plt.subplots(figsize=(10, 10))
    # Generar ruido aleatorio que parece nubes
    fake_data = np.random.rand(500, 500)
    ax.imshow(fake_data, cmap='gray')
    ax.set_title("PRUEBA DE GRÁFICO: El sistema visual funciona", color='red')
    ax.axis('off')
    st.pyplot(fig)
    
else:
    # --- MODO REAL ---
    if st.button("🔄 Cargar Satélite", use_container_width=True):
        st.rerun()

    st.caption(f"Buscando en: {date_input} a las {hour_input}:00 UTC")
    
    with st.spinner("Conectando con NOAA..."):
        img, msg = get_satellite_data(date_input, hour_input, channel_id)
        
        if img is None:
            st.error(f"❌ {msg}")
            st.info("Intenta cambiar la hora o la fecha en el menú lateral.")
        else:
            fig, ax = plt.subplots(figsize=(10, 10))
            
            # Paletas de color básicas
            if channel_id == "C13":
                cmap = 'turbo_r' # Infrarrojo
                vmin, vmax = 180, 300
                img = np.clip(img, vmin, vmax)
            elif channel_id == "C02":
                cmap = 'gray'
                vmin, vmax = 0, 1
            else:
                cmap = 'coolwarm' # Vapor
                vmin, vmax = 200, 270

            ax.imshow(img, cmap=cmap, vmin=vmin, vmax=vmax)
            ax.set_title(f"GOES-16 {channel}\n{msg.split('/')[-1]}", fontsize=8)
            ax.axis('off')
            st.pyplot(fig)
            st.success("✅ Imagen descargada con éxito")
