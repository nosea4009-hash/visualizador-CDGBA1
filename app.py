import streamlit as st
import matplotlib.pyplot as plt
import xarray as xr
import s3fs
import numpy as np
import boto3
from botocore import UNSIGNED
from botocore.config import Config
from datetime import datetime

# --- Configuración Inicial ---
st.set_page_config(page_title="Satélite GOES-16", layout="centered")
st.title("🛰️ Visor Satelital (Vía Boto3)")

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
    # Usamos ayer (31 Dic) por seguridad para la prueba
    date_input = st.sidebar.date_input("Fecha", datetime(2025, 12, 31))
    hour_input = st.sidebar.slider("Hora UTC", 0, 23, 18)
else:
    now = datetime.utcnow()
    date_input = now
    hour_input = now.hour
    st.sidebar.info("Modo Tiempo Real")

channel_id = {"13 (Infrarrojo)": "C13", "02 (Visible)": "C02", "09 (Vapor de Agua)": "C09"}[channel]

# --- FUNCIÓN DE BÚSQUEDA PROFESIONAL (Boto3) ---
def find_file_with_boto3(bucket, year, doy, hour, ch_id):
    # Conectamos a AWS como usuario ANÓNIMO (sin contraseña)
    # Esto es clave: NOAA permite acceso público si te identificas como 'UNSIGNED'
    s3 = boto3.client('s3', region_name='us-east-1', config=Config(signature_version=UNSIGNED))
    
    prefix = f"ABI-L2-CMIPF/{year}/{doy:03d}/{hour:02d}/"
    
    try:
        # Pedimos la lista oficial de objetos
        response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        
        if 'Contents' not in response:
            return None # La carpeta existe pero está vacía
            
        # Filtramos buscando nuestro canal
        files = []
        for obj in response['Contents']:
            key = obj['Key']
            if f"M6{ch_id}" in key or f"M3{ch_id}" in key:
                files.append(key)
                
        if not files:
            return None
            
        # Devolvemos el último (más reciente)
        return files[-1]
        
    except Exception as e:
        st.error(f"Error de Boto3: {e}")
        return None

# --- Función de Descarga ---
@st.cache_data(ttl=600)
def get_satellite_data(tgt_date, tgt_hour, ch_id):
    bucket_name = "noaa-goes16"
    year = tgt_date.year
    doy = tgt_date.timetuple().tm_yday
    
    # 1. BUSCAR (Usando Boto3 - Infalible)
    file_key = find_file_with_boto3(bucket_name, year, doy, tgt_hour, ch_id)
    
    if not file_key:
        return None, "Boto3 no encontró archivos. Verifica la fecha/hora."

    # 2. DESCARGAR (Usando s3fs)
    # Una vez que tenemos la 'key' exacta, s3fs no falla.
    fs = s3fs.S3FileSystem(anon=True)
    full_path = f"s3://{bucket_name}/{file_key}"
    
    try:
        remote_file = fs.open(full_path)
        ds = xr.open_dataset(remote_file, engine='h5netcdf')
        data = ds['CMI'].values
        
        # Recorte optimizado
        if ch_id == "C02": # Visible
            h, w = data.shape
            data = data[int(h*0.55):int(h*0.85), int(w*0.35):int(w*0.65)]
        else: # IR
            data = data[3000:4800, 1500:3500]
            
        return data, file_key
        
    except Exception as e:
        return None, f"Error abriendo archivo: {e}"

# --- Visualización ---
if st.button("🔄 Cargar Imagen", use_container_width=True):
    st.rerun()

st.caption(f"Consultando: {date_input} | {hour_input}:00 UTC")

with st.spinner("Conectando con Amazon AWS (Boto3)..."):
    img, msg = get_satellite_data(date_input, hour_input, channel_id)
    
    if img is None:
        st.error(f"❌ {msg}")
    else:
        fig, ax = plt.subplots(figsize=(10, 10))
        
        if channel_id == "C13":
            cmap = 'turbo_r' 
            vmin, vmax = 180, 300
            img = np.clip(img, vmin, vmax)
        elif channel_id == "C02":
            cmap = 'gray'
            vmin, vmax = 0, 1
            img = np.power(img, 0.7) 
        else:
            cmap = 'coolwarm'
            vmin, vmax = 200, 270

        ax.imshow(img, cmap=cmap, vmin=vmin, vmax=vmax)
        
        fname = msg.split('/')[-1] if msg else "Imagen"
        ax.set_title(f"GOES-16 {channel}\n{fname}", fontsize=8)
        ax.axis('off')
        
        st.pyplot(fig, use_container_width=True)
        st.success("✅ ¡Conexión Establecida!")
