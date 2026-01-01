import streamlit as st
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import xarray as xr
import s3fs
import numpy as np
from datetime import datetime
from metpy.plots import colortables
import matplotlib.patheffects as PathEffects

# --- Configuración de la Página (Mobile Friendly) ---
st.set_page_config(
    page_title="Satélite ARG", 
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed" # Arranca con el menú cerrado en el celular para ver el mapa directo
)

st.title("🛰️ Satélite Tiempo Real")

# --- DEFINICIÓN DE REGIONES ---
REGIONES = {
    "Argentina Centro": [-66.0, -56.5, -36.0, -29.0],
    "Buenos Aires (PBA)": [-64.0, -56.0, -41.5, -33.0],
    "Cuyo": [-71.0, -66.0, -38.0, -31.0],
    "NOA": [-69.0, -63.0, -28.0, -21.0],
    "NEA": [-63.0, -53.0, -31.0, -22.0],
    "Patagonia N": [-72.0, -62.0, -46.0, -36.0],
    "Patagonia S": [-74.0, -65.0, -56.0, -45.0],
    "Cono Sur": [-85.0, -45.0, -60.0, -15.0],
}

# --- BARRA LATERAL (Optimizada para Celular) ---
# 1. Lo más importante arriba
channel = st.sidebar.selectbox(
    "📡 Canal / Banda", 
    ["13 (Infrarrojo - Nubes)", "02 (Visible - Día)", "09 (Vapor de Agua)", "07 (IR Corto - Niebla)"], 
    index=0
)

region_name = st.sidebar.selectbox("📍 Zona / Región", list(REGIONES.keys()) + ["Personalizado"])

# Lógica de coordenadas
if region_name == "Personalizado":
    st.sidebar.warning("🛠️ Ajuste Manual de Coordenadas")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        lon_min = st.number_input("Oeste", value=-66.0, step=0.5)
        lat_min = st.number_input("Sur", value=-36.0, step=0.5)
    with col2:
        lon_max = st.number_input("Este", value=-56.5, step=0.5)
        lat_max = st.number_input("Norte", value=-29.0, step=0.5)
    extent = [lon_min, lon_max, lat_min, lat_max]
else:
    extent = REGIONES[region_name]

st.sidebar.markdown("---")

# 2. Opciones secundarias escondidas en un Expander para no ocupar pantalla
with st.sidebar.expander("⚙️ Capas y Detalles (Clic aquí)"):
    st.write("Configuración del Mapa")
    show_provinces = st.checkbox("Mostrar Provincias", value=True)
    show_cities = st.checkbox("Mostrar Ciudades", value=True)
    st.markdown("---")
    st.caption("Ajustar esto puede ralentizar un poco la carga.")

# Mapeo de canales
channel_map = {
    "13 (Infrarrojo - Nubes)": "C13",
    "02 (Visible - Día)": "C02",
    "09 (Vapor de Agua)": "C09",
    "07 (IR Corto - Niebla)": "C07"
}
selected_channel = channel_map[channel]

# --- FUNCIÓN DE DESCARGA ---
@st.cache_data(ttl=300)
def get_latest_goes_data(channel):
    fs = s3fs.S3FileSystem(anon=True)
    bucket_prefix = "noaa-goes16/ABI-L2-CMIPF"
    
    now = datetime.utcnow()
    year = now.year
    day_of_year = now.timetuple().tm_yday
    hour = now.hour
    
    path = f"{bucket_prefix}/{year}/{day_of_year:03d}/{hour:02d}/"
    try:
        files = fs.ls(path)
    except:
        hour = hour - 1 if hour > 0 else 23
        path = f"{bucket_prefix}/{year}/{day_of_year:03d}/{hour:02d}/"
        files = fs.ls(path)

    channel_files = [f for f in files if f"M6{channel}" in f or f"M3{channel}" in f]
    
    if not channel_files:
        return None, None, None
        
    latest_file = channel_files[-1]
    f_obj = fs.open(latest_file)
    ds = xr.open_dataset(f_obj, engine='h5netcdf')
    dat = ds.metpy.parse_cf('CMI')
    proj = dat.metpy.cartopy_crs
    
    return dat, proj, latest_file

# --- INTERFAZ PRINCIPAL ---
# Botón grande y fácil de tocar
if st.button("🔄 ACTUALIZAR IMAGEN", use_container_width=True):
    st.rerun()

with st.spinner("🛰️ Descargando imagen satelital..."):
    try:
        data, projection, filename = get_latest_goes_data(selected_channel)
        
        if data is None:
            st.error("⚠️ Datos no disponibles momentáneamente. Intenta en 5 min.")
        else:
            # Tamaño optimizado para ver en vertical en celular (10x8)
            fig = plt.figure(figsize=(10, 8)) 
            ax = fig.add_subplot(1, 1, 1, projection=projection)
            
            # Colores
            if selected_channel == "C13":
                ct = 'ir_drgb'
                vmin, vmax = 180, 300
            elif selected_channel == "C02":
                ct = 'gray'
                vmin, vmax = 0, 1
            elif selected_channel == "C09":
                ct = 'WVCimss'
                vmin, vmax = 195, 295
            elif selected_channel == "C07":
                ct = 'ir_tv1'
                vmin, vmax = 190, 310
            else:
                ct = 'viridis'
                vmin, vmax = None, None

            try:
                cmap = colortables.get_colortable(ct)
            except:
                cmap = ct

            # Plot
            im = ax.imshow(data, extent=(data.x.min(), data.x.max(), data.y.min(), data.y.max()),
                           origin='upper', cmap=cmap, vmin=vmin, vmax=vmax, transform=projection)

            ax.set_extent(extent, crs=ccrs.PlateCarree())

            # Capas
            ax.coastlines(resolution='10m', color='cyan', linewidth=1.2)
            ax.add_feature(cfeature.BORDERS, linewidth=1.2, edgecolor='cyan')
            
            if show_provinces:
                provinces = cfeature.NaturalEarthFeature(
                    category='cultural', name='admin_1_states_provinces_lines',
                    scale='10m', facecolor='none')
                ax.add_feature(provinces, edgecolor='yellow', linewidth=0.7, alpha=0.6)

            if show_cities:
                # Diccionario extendido de ciudades principales
                cities = {
                    "CABA": (-34.60, -58.38), "Córdoba": (-31.42, -64.18),
                    "Rosario": (-32.94, -60.63), "Mendoza": (-32.88, -68.83),
                    "Tucumán": (-26.80, -65.22), "Salta": (-24.78, -65.42),
                    "Neuquén": (-38.95, -68.05), "Resistencia": (-27.46, -58.98),
                    "Santa Rosa": (-36.61, -64.28)
                }
                for city, (lat, lon) in cities.items():
                    if (extent[0] <= lon <= extent[1]) and (extent[2] <= lat <= extent[3]):
                        # Sombra negra en el texto para que se lea sobre nubes blancas
                        txt = ax.text(lon, lat, f"  {city}", color='white', fontsize=11, 
                                transform=ccrs.PlateCarree(), fontweight='bold', va='center')
                        txt.set_path_effects([PathEffects.withStroke(linewidth=2, foreground='black')])
                        ax.plot(lon, lat, 'wo', markersize=4, transform=ccrs.PlateCarree(),
                                path_effects=[PathEffects.withStroke(linewidth=2, foreground='black')])

            plt.title(f"GOES-16 {channel[:2]} | {region_name}\nUTC: {filename.split('_s')[-1][:11]}", fontsize=10)
            
            # Mostrar gráfico ajustado al ancho de columna
            st.pyplot(fig, use_container_width=True)
            
            # Información pequeña abajo
            st.caption(f"📍 Coordenadas visualizadas: {extent}")

    except Exception as e:
        st.error(f"Error técnico: {e}")
