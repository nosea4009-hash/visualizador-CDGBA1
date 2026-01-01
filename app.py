import streamlit as st
import matplotlib.pyplot as plt
import xarray as xr
import s3fs
import numpy as np
from datetime import datetime, timedelta
import requests
import xml.etree.ElementTree as ET

# --- Configuración ---
st.set_page_config(page_title="Satélite Inteligente", layout="centered")
st.title("🛰️ Visor Satelital (Buscador Auto)")

# --- Sidebar ---
st.sidebar.header("Opciones")
channel = st.sidebar.selectbox("Canal", ["13 (Infrarrojo)", "02 (Visible)", "09 (Vapor de Agua)"], index=0)
st.sidebar.info("ℹ️ El sistema buscará automáticamente la imagen más reciente disponible.")

channel_id = {"13 (Infrarrojo)": "C13", "02 (Visible)": "C02", "09 (Vapor de Agua)": "C09"}[channel]
bucket_name = "noaa-goes16"

# --- MOTOR DE BÚSQUEDA INTELIGENTE ---
def find_latest_available_file(ch_id):
    # Empezamos buscando desde AHORA mismo hacia atrás
    now = datetime.utcnow()
    
    # Intentamos buscar hasta 12 horas atrás
    for i in range(12):
        check_time = now - timedelta(hours=i)
        year = check_time.year
        doy = check_time.timetuple().tm_yday
        hour = check_time.hour
        
        # URL del índice XML para esa hora específica
        prefix = f"ABI-L2-CMIPF/{year}/{doy:03d}/{hour:02d}/"
        url = f"https://{bucket_name}.s3.amazonaws.com/?list-type=2&prefix={prefix}"
        
        try:
            # Petición rápida (Timeout corto para no trabar la app)
            r = requests.get(url, timeout=5)
            
            if r.status_code == 200 and "<KeyCount>0</KeyCount>" not in r.text:
                # ¡ENCONTRAMOS UNA CARPETA CON DATOS!
                # Ahora parseamos para sacar el nombre del archivo exacto
                root = ET.fromstring(r.content)
                # Buscamos el último archivo que coincida con nuestro canal
                found_file = None
                
                # Barrido manual del XML para evitar errores de namespace
                files_in_folder = []
                for child in root:
                    if child.tag.endswith('Contents'):
                        for item in child:
                            if item.tag.endswith('Key'):
                                fname = item.text
                                if f"M6{ch_id}" in fname or f"M3{ch_id}" in fname:
                                    files_in_folder.append(fname)
                
                if files_in_folder:
                    # Devolvemos el último (más nuevo) y la hora que funcionó
                    return files_in_folder[-1], check_time
                    
        except Exception:
            continue # Si falla esta hora, pasamos a la siguiente sin llorar
            
    return None, None

# --- Función de Descarga ---
@st.cache_data(ttl=600)
def download_and_plot(file_key):
    fs = s3fs.S3FileSystem(anon=True)
    full_path = f"s3://{bucket_name}/{file_key}"
    
    try:
        remote_file = fs.open(full_path)
        ds = xr.open_dataset(remote_file, engine='h5netcdf')
        data = ds['CMI'].values
        
        # Recorte optimizado
        if "C02" in file_key: # Visible
            h, w = data.shape
            data = data[int(h*0.5):int(h*0.8), int(w*0.3):int(w*0.7)]
        else: # IR
            data = data[3000:4800, 1500:3500]
            
        return data
    except Exception as e:
        return None

# --- INTERFAZ ---
if st.button("🔄 Buscar Nueva Imagen", use_container_width=True):
    st.rerun()

status_text = st.empty()
status_text.text("🔎 Escaneando últimas 12 horas en NOAA...")

# 1. BUSCAR
file_key, timestamp = find_latest_available_file(channel_id)

if file_key:
    time_str = timestamp.strftime("%Y-%m-%d %H:00 UTC")
    status_text.success(f"✅ ¡Encontrado! Mostrando datos de: {time_str}")
    
    # 2. DESCARGAR
    with st.spinner("Descargando imagen..."):
        img = download_and_plot(file_key)
        
        if img is not None:
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
            ax.set_title(f"GOES-16 {channel}\n{file_key}", fontsize=8)
            ax.axis('off')
            st.pyplot(fig, use_container_width=True)
        else:
            st.error("Error al abrir el archivo encontrado.")
else:
    status_text.error("❌ No se encontraron imágenes en las últimas 12 horas (Posible mantenimiento NOAA).")
