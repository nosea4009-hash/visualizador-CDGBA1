import streamlit as st
import matplotlib.pyplot as plt
import xarray as xr
import s3fs
import numpy as np
from datetime import datetime

# --- Configuración ---
st.set_page_config(page_title="Satélite Lite", layout="centered", initial_sidebar_state="collapsed")
st.title("🛰️ Satélite GOES-16 (Modo Rápido)")

# --- Sidebar ---
st.sidebar.header("Opciones")
channel = st.sidebar.selectbox(
    "Canal", 
    ["13 (Infrarrojo)", "02 (Visible)", "09 (Vapor de Agua)"], 
    index=0
)

# Mapeo
channel_id = {
    "13 (Infrarrojo)": "C13",
    "02 (Visible)": "C02",
    "09 (Vapor de Agua)": "C09"
}[channel]

# --- Función de Descarga ---
@st.cache_data(ttl=300)
def get_image(selected_channel):
    fs = s3fs.S3FileSystem(anon=True)
    # Usamos CONUS (Continental US) o Full Disk. 
    # Full Disk es muy pesado para procesar sin Cartopy en modo simple, 
    # así que intentaremos recortar o usar una visualización directa.
    bucket = "noaa-goes16/ABI-L2-CMIPF" # Full Disk
    
    now = datetime.utcnow()
    year = now.year
    day = now.timetuple().tm_yday
    hour = now.hour
    
    # Intentar hora actual o anterior
    path = f"{bucket}/{year}/{day:03d}/{hour:02d}/"
    try:
        files = fs.ls(path)
    except:
        hour = hour - 1 if hour > 0 else 23
        path = f"{bucket}/{year}/{day:03d}/{hour:02d}/"
        files = fs.ls(path)
        
    # Buscar archivo
    c_files = [f for f in files if f"M6{selected_channel}" in f or f"M3{selected_channel}" in f]
    if not c_files: return None, None
    
    # Abrir
    f = fs.open(c_files[-1])
    ds = xr.open_dataset(f, engine='h5netcdf')
    
    # Extraer datos puros (CMI = Cloud Moisture Imagery)
    # Recortamos para enfocar aproximadamente en Sudamérica
    # El disco completo es aprox 5424x5424 pixeles.
    # Sudamérica está "abajo a la derecha" más o menos en los índices.
    # Estos indices son aproximados para hacer zoom en el Cono Sur
    
    data = ds['CMI'].values
    
    # Recorte manual de matriz (Slicing) para enfocar Argentina
    # GOES Full Disk: Y (Norte-Sur) 0 a 5424, X (Oeste-Este) 0 a 5424
    # Argentina está aprox en el cuadrante inferior.
    if selected_channel == "C02": # El visible tiene mas resolucion (más pixeles)
        recorte = data[3000:4500, 1500:3500] 
    else:
        recorte = data[3000:4500, 1500:3500]
        
    return recorte, c_files[-1]

# --- Visualización ---
if st.button("🔄 Actualizar", use_container_width=True):
    st.rerun()

with st.spinner("Descargando imagen satelital..."):
    try:
        img_data, filename = get_image(channel_id)
        
        if img_data is None:
            st.error("No hay datos disponibles.")
        else:
            fig, ax = plt.subplots(figsize=(10, 10))
            
            # Colores manuales simples
            cmap = 'viridis'
            vmin, vmax = None, None
            
            if channel_id == "C13":
                cmap = 'turbo' # Parecido a IR
                vmin, vmax = 180, 300
                img_data = np.clip(img_data, vmin, vmax) # Limpiar ruido
            elif channel_id == "C02":
                cmap = 'gray'
                vmin, vmax = 0, 1
            elif channel_id == "C09":
                cmap = 'coolwarm'
            
            # Mostrar imagen pura (como una foto)
            ax.imshow(img_data, cmap=cmap, vmin=vmin, vmax=vmax)
            ax.axis('off') # Quitar ejes X/Y con números de pixel
            
            st.pyplot(fig, use_container_width=True)
            st.caption(f"Archivo: {filename}")
            st.info("ℹ️ Modo Lite: Sin fronteras políticas para máxima velocidad.")

    except Exception as e:
        st.error(f"Error: {e}")
