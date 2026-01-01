import streamlit as st
import matplotlib.pyplot as plt
import xarray as xr
import s3fs
import numpy as np
import boto3
from botocore import UNSIGNED
from botocore.config import Config
from datetime import datetime
import requests
import xml.etree.ElementTree as ET

# --- Configuración Inicial ---
st.set_page_config(page_title="Diagnóstico GOES-16", layout="centered")
st.title("🕵️‍♂️ Diagnóstico de Conexión NOAA")

# --- Barra Lateral ---
st.sidebar.header("Configuración")
channel = st.sidebar.selectbox("Canal", ["13 (Infrarrojo)", "02 (Visible)"], index=0)

# Fecha y Hora (Por defecto ayer para asegurar datos)
date_input = st.sidebar.date_input("Fecha", datetime(2025, 12, 31))
hour_input = st.sidebar.slider("Hora UTC", 0, 23, 7) # Probamos con las 7 UTC

channel_id = {"13 (Infrarrojo)": "C13", "02 (Visible)": "C02"}[channel]
bucket_name = "noaa-goes16"

# --- ÁREA DE LOGS EN PANTALLA ---
st.subheader("📝 Resultados del Diagnóstico")
log_box = st.empty()
logs = []

def add_log(message):
    logs.append(message)
    log_text = "\n".join(logs)
    log_box.text_area("Log de Sistema:", log_text, height=300)

# --- MÉTODO 1: BOTO3 (Oficial) ---
def try_boto3(year, doy, hour):
    add_log(f"🔵 INTENTO 1: Boto3 (AWS Nativo)...")
    prefix = f"ABI-L2-CMIPF/{year}/{doy:03d}/{hour:02d}/"
    add_log(f"   Buscando en: {prefix}")
    
    try:
        s3 = boto3.client('s3', region_name='us-east-1', config=Config(signature_version=UNSIGNED))
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        
        if 'Contents' in response:
            count = len(response['Contents'])
            add_log(f"   ✅ ÉXITO: Se encontraron {count} archivos.")
            # Buscar nuestro canal
            for obj in response['Contents']:
                if f"M6{channel_id}" in obj['Key'] or f"M3{channel_id}" in obj['Key']:
                    return obj['Key']
            add_log("   ⚠️ Archivos encontrados, pero ninguno de este canal.")
        else:
            add_log("   ❌ ERROR: La carpeta parece vacía (Response sin 'Contents').")
            
    except Exception as e:
        add_log(f"   ❌ EXCEPCIÓN: {str(e)}")
    return None

# --- MÉTODO 2: HTTP XML (Fuerza Bruta) ---
def try_http_xml(year, doy, hour):
    add_log(f"\n🟠 INTENTO 2: HTTP Request (XML)...")
    prefix = f"ABI-L2-CMIPF/{year}/{doy:03d}/{hour:02d}/"
    url = f"https://{bucket_name}.s3.amazonaws.com/?list-type=2&prefix={prefix}"
    add_log(f"   Consultando URL: {url}")
    
    try:
        r = requests.get(url, timeout=10)
        add_log(f"   Status Code: {r.status_code}")
        
        if r.status_code == 200:
            text = r.text[:500] + "..." # Solo mostrar el principio
            add_log(f"   Respuesta del servidor (Primeros 500 chars):\n   {text}")
            
            # Parseo simple
            if f"M6{channel_id}" in r.text:
                # Extraer nombre a lo bruto
                parts = r.text.split(f"M6{channel_id}")
                # Reconstruir un pedazo para encontrar el nombre completo
                # (Esto es simplificado, solo para ver si 'está' ahí)
                add_log("   ✅ ¡El archivo aparece en el texto XML!")
                return "ENCONTRADO_EN_XML"
            elif f"M3{channel_id}" in r.text:
                 add_log("   ✅ ¡El archivo aparece en el texto XML (Modo 3)!")
                 return "ENCONTRADO_EN_XML"
            else:
                add_log("   ⚠️ El XML se descargó pero no veo el archivo del canal.")
        else:
            add_log("   ❌ Falló la petición HTTP.")
            
    except Exception as e:
        add_log(f"   ❌ EXCEPCIÓN HTTP: {str(e)}")
    return None

# --- VISUALIZACIÓN ---
if st.button("🚀 INICIAR DIAGNÓSTICO", use_container_width=True):
    logs = [] # Limpiar
    year = date_input.year
    doy = date_input.timetuple().tm_yday
    
    # 1. Probar Boto3
    file_key = try_boto3(year, doy, hour_input)
    
    # 2. Si falla, probar HTTP
    if not file_key:
        file_key_http = try_http_xml(year, doy, hour_input)
        
    # Si encontramos algo con Boto3, intentamos descargar
    if file_key and file_key != "ENCONTRADO_EN_XML":
        add_log(f"\n🟢 INTENTANDO DESCARGA FINAL: {file_key}")
        try:
            fs = s3fs.S3FileSystem(anon=True)
            f = fs.open(f"s3://{bucket_name}/{file_key}")
            ds = xr.open_dataset(f, engine='h5netcdf')
            data = ds['CMI'].values
            
            # Ploteo rápido
            fig, ax = plt.subplots()
            ax.imshow(data[3000:4000, 1500:2500], cmap='gray') # Recorte pequeño
            ax.set_title("¡SI SE VE!", color='green')
            ax.axis('off')
            st.pyplot(fig)
            st.success("¡LO LOGRAMOS! 🎉")
            
        except Exception as e:
            add_log(f"   ❌ ERROR AL ABRIR/PLOTEAR: {e}")

    elif file_key == "ENCONTRADO_EN_XML":
         st.warning("El archivo existe (lo vimos por HTTP) pero Boto3 no pudo listarlo. Es un bloqueo de AWS.")
    else:
         st.error("Ningún método funcionó. Revisa el LOG de arriba.")
