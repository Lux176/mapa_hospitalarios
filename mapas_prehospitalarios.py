# --- IMPORTS NECESARIOS ---
import streamlit as st
import pandas as pd
import numpy as np
import json
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from io import BytesIO
import unicodedata
import base64
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from PIL import Image
import tempfile
import time

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Mapa de Atenciones Prehospitalarias",
    page_icon="🚑",
    layout="wide"
)

# --- FUNCIONES DE PROCESAMIENTO (SIN CAMBIOS EN SU LÓGICA INTERNA) ---

def limpiar_texto(texto):
    """Normaliza un texto a minúsculas y sin acentos."""
    if not isinstance(texto, str): return texto
    return unicodedata.normalize('NFD', texto).encode('ascii', 'ignore').decode('utf-8').lower().strip()

def obtener_centroide(feature):
    """Calcula el centroide del polígono más grande en una features GeoJSON."""
    geom = feature.get("geometry", {})
    gtype, coords = geom.get("type"), geom.get("coordinates", [])
    if gtype == "Polygon": polygon_coords = coords[0]
    elif gtype == "MultiPolygon": polygon_coords = max([poly[0] for poly in coords], key=len)
    else: return None
    if not polygon_coords: return None
    longitudes, latitudes = zip(*polygon_coords)
    return (sum(latitudes) / len(latitudes), sum(longitudes) / len(longitudes))

def crear_mapa(df, gj_data, campo_geojson, col_lat, col_lon, col_colonia):
    """Crea y configura el mapa Folium con todas sus capas."""
    # st.info("🗺️ Creando mapa base...")
    centro = [df[col_lat].mean(), df[col_lon].mean()]
    mapa = folium.Map(location=centro, zoom_start=13, tiles="CartoDB positron")
    color_map = {'Protección Civil': '#007bff', 'Servicios Médicos': '#800000'}

    # CAPA DE COLONIAS
    nombres_originales = {}
    for feature in gj_data['features']:
        if campo_geojson in feature['properties']:
            original = feature['properties'][campo_geojson]
            limpio = limpiar_texto(original)
            feature['properties'][campo_geojson] = limpio
            nombres_originales[limpio] = original

    folium.GeoJson(
        gj_data, name='Colonias',
        style_function=lambda x: {'fillColor': '#ffffff', 'color': '#808080', 'weight': 1, 'fillOpacity': 0.1},
        tooltip=folium.GeoJsonTooltip(fields=[campo_geojson], aliases=['Colonia:'])
    ).add_to(mapa)

    # CAPA DE NOMBRES
    capa_nombres = folium.FeatureGroup(name="Nombres de Colonias", show=True).add_to(mapa)
    for feature in gj_data['features']:
        centro_colonia = obtener_centroide(feature)
        nombre_limpio = feature['properties'].get(campo_geojson)
        if centro_colonia and nombre_limpio:
            nombre_display = nombres_originales.get(nombre_limpio, nombre_limpio).title()
            folium.Marker(
                location=centro_colonia,
                icon=folium.DivIcon(html=f'<div style="font-family: Arial; font-size: 11px; font-weight: bold; color: #333; text-shadow: 1px 1px 1px #FFF; white-space: nowrap;">{nombre_display}</div>')
            ).add_to(capa_nombres)

    # CAPAS DE PUNTOS Y CALOR
    puntos_pc = folium.FeatureGroup(name="Puntos: Protección Civil (Azul)", show=True).add_to(mapa)
    puntos_sm = folium.FeatureGroup(name="Puntos: Servicios Médicos (Vino)", show=True).add_to(mapa)
    calor_pc = folium.FeatureGroup(name="Calor: Protección Civil", show=True).add_to(mapa)
    calor_sm = folium.FeatureGroup(name="Calor: Servicios Médicos", show=False).add_to(mapa)

    df_pc = df[df['Fuente de Atención'] == 'Protección Civil']
    df_sm = df[df['Fuente de Atención'] == 'Servicios Médicos']

    for _, row in df_pc.iterrows():
        popup_html = f"<b>Fecha:</b> {row[col_fecha].date()}<br><b>Colonia:</b> {row[col_colonia].title()}<br><b>Atendido por:</b> Protección Civil"
        folium.CircleMarker(location=[row[col_lat], row[col_lon]], radius=5, color=color_map['Protección Civil'], fill=True, fill_color=color_map['Protección Civil'], fill_opacity=0.8, popup=folium.Popup(popup_html, max_width=300), tooltip="Protección Civil").add_to(puntos_pc)
    
    for _, row in df_sm.iterrows():
        popup_html = f"<b>Fecha:</b> {row[col_fecha].date()}<br><b>Colonia:</b> {row[col_colonia].title()}<br><b>Atendido por:</b> Servicios Médicos"
        folium.CircleMarker(location=[row[col_lat], row[col_lon]], radius=5, color=color_map['Servicios Médicos'], fill=True, fill_color=color_map['Servicios Médicos'], fill_opacity=0.8, popup=folium.Popup(popup_html, max_width=300), tooltip="Servicios Médicos").add_to(puntos_sm)
    
    if not df_pc.empty: HeatMap(df_pc[[col_lat, col_lon]].values, radius=15).add_to(calor_pc)
    if not df_sm.empty: HeatMap(df_sm[[col_lat, col_lon]].values, radius=15).add_to(calor_sm)

    folium.LayerControl(collapsed=False).add_to(mapa)
    return mapa

# --- FUNCIONES DE DESCARGA AGREGADAS ---
def guardar_mapa_html(mapa):
    """Guarda el mapa como archivo HTML temporal y devuelve los datos para descarga"""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.html') as tmp_file:
        mapa.save(tmp_file.name)
        with open(tmp_file.name, 'r', encoding='utf-8') as f:
            html_content = f.read()
    return html_content

def generar_imagen_mapa(mapa):
    """Genera una imagen PNG del mapa usando Selenium"""
    try:
        # Guardar mapa temporalmente como HTML
        with tempfile.NamedTemporaryFile(delete=False, suffix='.html') as tmp_html:
            mapa.save(tmp_html.name)
        
        # Configurar Selenium para captura de pantalla
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1200,800")
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(f"file://{tmp_html.name}")
        time.sleep(3)  # Esperar a que cargue el mapa
        
        # Capturar screenshot
        screenshot = driver.get_screenshot_as_png()
        driver.quit()
        
        return screenshot
    except Exception as e:
        st.error(f"Error al generar imagen: {e}")
        return None

def crear_boton_descarga(data, nombre_archivo, tipo_descarga):
    """Crea un botón de descarga para el archivo"""
    b64 = base64.b64encode(data).decode()
    href = f'data:application/octet-stream;base64,{b64}'
    st.download_button(
        label=f"📥 Descargar {tipo_descarga}",
        data=data,
        file_name=nombre_archivo,
        mime="application/octet-stream",
        key=f"download_{tipo_descarga}_{hash(nombre_archivo)}"
    )

# --- INTERFAZ DE STREAMLIT ---

st.title("🚑 Generador de Mapas de Atenciones Prehospitalarias")
st.markdown("Esta herramienta te permite visualizar en un mapa interactivo los reportes de atenciones médicas.")

# --- BARRA LATERAL CON CONTROLES ---
with st.sidebar:
    st.header("⚙️ Configuración del Mapa")
    
    # PASO 1: Cargar archivos
    st.subheader("1. Carga tus archivos")
    uploaded_data_file = st.file_uploader(
        "Sube el archivo de atenciones (Excel o CSV)",
        type=['xlsx', 'csv']
    )
    uploaded_geojson_file = st.file_uploader(
        "Sube el archivo de colonias (GeoJSON)",
        type=['geojson', 'json']
    )

    # Variables para almacenar selecciones
    df = None
    gj_data = None
    
    if uploaded_data_file and uploaded_geojson_file:
        # Cargar DataFrames
        try:
            if uploaded_data_file.name.endswith('.xlsx'):
                df = pd.read_excel(uploaded_data_file)
            else:
                df = pd.read_csv(uploaded_data_file)
            
            gj_data = json.load(uploaded_geojson_file)
            st.success("✅ ¡Archivos cargados correctamente!")
        except Exception as e:
            st.error(f"Error al leer los archivos: {e}")
            st.stop()
            
        # PASO 2: Mapeo de columnas
        st.subheader("2. Asigna las columnas")
        
        columnas_disponibles = df.columns.tolist()
        
        col_lat = st.selectbox("Columna de LATITUD:", columnas_disponibles, index=None, placeholder="Selecciona una opción")
        col_lon = st.selectbox("Columna de LONGITUD:", columnas_disponibles, index=None, placeholder="Selecciona una opción")
        col_colonia = st.selectbox("Columna de COLONIA:", columnas_disponibles, index=None, placeholder="Selecciona una opción")
        col_fecha = st.selectbox("Columna de FECHA:", columnas_disponibles, index=None, placeholder="Selecciona una opción")
        col_sm = st.selectbox("Columna de SERVICIOS MÉDICOS (SM):", columnas_disponibles, index=None, placeholder="Selecciona una opción")
        
        # Selección del campo del GeoJSON
        try:
            campos_geojson = list(gj_data['features'][0]['properties'].keys())
            campo_geojson_seleccionado = st.selectbox("Campo con nombre de la colonia en GeoJSON:", campos_geojson, index=None, placeholder="Selecciona una opción")
        except (IndexError, KeyError):
            st.error("El archivo GeoJSON no tiene un formato válido o está vacío.")
            st.stop()

        # Validar que todas las columnas necesarias han sido seleccionadas
        columnas_esenciales = [col_lat, col_lon, col_colonia, col_fecha, col_sm, campo_geojson_seleccionado]
        
        if all(columnas_esenciales):
            # PROCESAMIENTO DE DATOS
            df['Fuente de Atención'] = np.where(df[col_sm].apply(limpiar_texto) == 'sm', 'Servicios Médicos', 'Protección Civil')
            df[col_colonia] = df[col_colonia].apply(limpiar_texto)
            df[col_lat] = pd.to_numeric(df[col_lat], errors='coerce')
            df[col_lon] = pd.to_numeric(df[col_lon], errors='coerce')
            df[col_fecha] = pd.to_datetime(df[col_fecha], errors='coerce')
            df_limpio = df.dropna(subset=[col_lat, col_lon, col_fecha, col_colonia])
            
            st.subheader("3. Filtra por fecha")
            
            fecha_min = df_limpio[col_fecha].min().date()
            fecha_max = df_limpio[col_fecha].max().date()
            
            fecha_inicio, fecha_fin = st.date_input(
                "Selecciona el rango de fechas:",
                value=(fecha_min, fecha_max),
                min_value=fecha_min,
                max_value=fecha_max
            )
            
            if fecha_inicio and fecha_fin:
                # Filtrar el DataFrame
                df_filtrado = df_limpio[
                    (df_limpio[col_fecha].dt.date >= fecha_inicio) &
                    (df_limpio[col_fecha].dt.date <= fecha_fin)
                ]

# --- ÁREA PRINCIPAL PARA MOSTRAR EL MAPA ---
if 'df_filtrado' in locals() and not df_filtrado.empty:
    st.success(f"Mostrando {len(df_filtrado)} atenciones en el mapa.")
    
    # Mostrar métricas
    conteo_pc = (df_filtrado['Fuente de Atención'] == 'Protección Civil').sum()
    conteo_sm = (df_filtrado['Fuente de Atención'] == 'Servicios Médicos').sum()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Atenciones", f"{conteo_pc + conteo_sm}")
    col2.metric("Atenciones Protección Civil", f"{conteo_pc}")
    col3.metric("Atenciones Servicios Médicos", f"{conteo_sm}")
    
    # Crear y mostrar el mapa
    mapa_final = crear_mapa(df_filtrado, gj_data, campo_geojson_seleccionado, col_lat, col_lon, col_colonia)
    
    # Mostrar el mapa
    st_folium(mapa_final, width=1200, height=600, returned_objects=[])
    
    # --- BOTONES DE DESCARGA AGREGADOS ---
    st.markdown("---")
    st.subheader("📥 Descargar Mapa")
    
    col_download1, col_download2 = st.columns(2)
    
    with col_download1:
        # Botón para descargar HTML
        if st.button("💾 Descargar como HTML", use_container_width=True):
            with st.spinner("Generando archivo HTML..."):
                html_content = guardar_mapa_html(mapa_final)
                crear_boton_descarga(
                    html_content.encode('utf-8'),
                    "mapa_atenciones_prehospitalarias.html",
                    "HTML"
                )
                st.success("✅ Archivo HTML listo para descargar")
    
    with col_download2:
        # Botón para descargar imagen
        if st.button("🖼️ Descargar como Imagen (PNG)", use_container_width=True):
            with st.spinner("Generando imagen del mapa... Esto puede tomar unos segundos"):
                screenshot = generar_imagen_mapa(mapa_final)
                if screenshot:
                    crear_boton_descarga(
                        screenshot,
                        "mapa_atenciones_prehospitalarias.png",
                        "Imagen PNG"
                    )
                    st.success("✅ Imagen PNG lista para descargar")
                else:
                    st.error("❌ No se pudo generar la imagen. Asegúrate de tener Chrome instalado.")

elif 'uploaded_data_file' in locals() and uploaded_data_file and 'uploaded_geojson_file' in locals() and uploaded_geojson_file:
    st.warning("⚠️ No se encontraron datos para el rango de fechas seleccionado o faltan asignaciones de columnas. Por favor, ajusta los filtros.")
else:
    st.info("👋 ¡Bienvenido! Por favor, sube tus archivos y configura las opciones en la barra lateral para generar el mapa.")
