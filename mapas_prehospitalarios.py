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
import tempfile

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Mapa de Atenciones Prehospitalarias",
    page_icon="🚑",
    layout="wide"
)

# --- INICIALIZACIÓN DE ESTADO ---
if 'mapa_generado' not in st.session_state:
    st.session_state.mapa_generado = False
if 'mostrar_leyenda' not in st.session_state:
    st.session_state.mostrar_leyenda = True

# --- FUNCIONES DE PROCESAMIENTO MEJORADAS ---

def limpiar_texto(texto):
    """Normaliza un texto a minúsculas y sin acentos."""
    if not isinstance(texto, str): 
        return texto
    try:
        return unicodedata.normalize('NFD', texto).encode('ascii', 'ignore').decode('utf-8').lower().strip()
    except (UnicodeError, AttributeError):
        return str(texto).lower().strip()

def obtener_centroide(feature):
    """Calcula el centroide del polígono más grande en una feature GeoJSON."""
    try:
        geom = feature.get("geometry", {})
        gtype, coords = geom.get("type"), geom.get("coordinates", [])
        
        if gtype == "Polygon": 
            polygon_coords = coords[0]
        elif gtype == "MultiPolygon": 
            polygon_coords = max([poly[0] for poly in coords], key=len)
        else: 
            return None
            
        if not polygon_coords: 
            return None
            
        longitudes, latitudes = zip(*polygon_coords)
        return (sum(latitudes) / len(latitudes), sum(longitudes) / len(longitudes))
    except Exception:
        return None

def crear_leyenda_personalizada(mapa, color_map):
    """Crea una leyenda personalizada para el mapa."""
    legend_html = '''
    <div id="legend" style="
        position: fixed; 
        bottom: 50px; 
        left: 50px; 
        width: 180px; 
        height: auto; 
        background: white; 
        border: 2px solid grey; 
        z-index: 9999; 
        padding: 10px; 
        font-size: 14px;
        border-radius: 5px;
        box-shadow: 0 0 10px rgba(0,0,0,0.2);
        font-family: Arial, sans-serif;
    ">
    <div style="font-weight: bold; margin-bottom: 8px; border-bottom: 1px solid #ccc; padding-bottom: 5px;">
        Fuente de Atención
    </div>
    <div style="margin-bottom: 5px;">
        <span style="background: {color_pc}; width: 15px; height: 15px; display: inline-block; margin-right: 8px; border-radius: 50%; border: 1px solid #333;"></span>
        Protección Civil
    </div>
    <div style="margin-bottom: 5px;">
        <span style="background: {color_sm}; width: 15px; height: 15px; display: inline-block; margin-right: 8px; border-radius: 50%; border: 1px solid #333;"></span>
        Servicios Médicos
    </div>
    </div>
    '''.format(
        color_pc=color_map['Protección Civil'],
        color_sm=color_map['Servicios Médicos']
    )
    
    mapa.get_root().html.add_child(folium.Element(legend_html))

def crear_mapa(df, gj_data, campo_geojson, col_lat, col_lon, col_colonia, col_fecha, mostrar_leyenda=True):
    """Crea y configura el mapa Folium con todas sus capas."""
    try:
        # Calcular centro del mapa
        centro = [df[col_lat].mean(), df[col_lon].mean()]
        mapa = folium.Map(
            location=centro, 
            zoom_start=13, 
            tiles="CartoDB positron",
            control_scale=True
        )
        
        color_map = {
            'Protección Civil': '#007bff', 
            'Servicios Médicos': '#800000'
        }

        # CAPA DE COLONIAS
        nombres_originales = {}
        for feature in gj_data['features']:
            if campo_geojson in feature['properties']:
                original = feature['properties'][campo_geojson]
                limpio = limpiar_texto(original)
                feature['properties'][campo_geojson] = limpio
                nombres_originales[limpio] = original

        folium.GeoJson(
            gj_data, 
            name='Límites de Colonias',
            style_function=lambda x: {
                'fillColor': '#ffffff', 
                'color': '#808080', 
                'weight': 1, 
                'fillOpacity': 0.1
            },
            tooltip=folium.GeoJsonTooltip(
                fields=[campo_geojson], 
                aliases=['Colonia:'],
                style="font-family: Arial; font-size: 12px;"
            )
        ).add_to(mapa)

        # CAPA DE NOMBRES DE COLONIAS
        capa_nombres = folium.FeatureGroup(name="Nombres de Colonias", show=False)
        for feature in gj_data['features']:
            centro_colonia = obtener_centroide(feature)
            nombre_limpio = feature['properties'].get(campo_geojson)
            if centro_colonia and nombre_limpio:
                nombre_display = nombres_originales.get(nombre_limpio, nombre_limpio).title()
                folium.Marker(
                    location=centro_colonia,
                    icon=folium.DivIcon(
                        html=f'''
                        <div style="
                            font-family: Arial; 
                            font-size: 11px; 
                            font-weight: bold; 
                            color: #333; 
                            text-shadow: 1px 1px 2px #FFF, -1px -1px 2px #FFF, 1px -1px 2px #FFF, -1px 1px 2px #FFF;
                            white-space: nowrap;
                            background: rgba(255,255,255,0.7);
                            padding: 2px 5px;
                            border-radius: 3px;
                        ">{nombre_display}</div>
                        '''
                    )
                ).add_to(capa_nombres)
        mapa.add_child(capa_nombres)

        # CAPAS DE PUNTOS
        puntos_pc = folium.FeatureGroup(name="📍 Protección Civil", show=True)
        puntos_sm = folium.FeatureGroup(name="📍 Servicios Médicos", show=True)
        
        # CAPAS DE CALOR
        calor_pc = folium.FeatureGroup(name="🔥 Calor - Protección Civil", show=True)
        calor_sm = folium.FeatureGroup(name="🔥 Calor - Servicios Médicos", show=False)

        # Separar datos por fuente
        df_pc = df[df['Fuente de Atención'] == 'Protección Civil']
        df_sm = df[df['Fuente de Atención'] == 'Servicios Médicos']

        # Agregar puntos de Protección Civil
        for _, row in df_pc.iterrows():
            try:
                fecha_str = row[col_fecha].strftime('%d/%m/%Y') if hasattr(row[col_fecha], 'strftime') else str(row[col_fecha])
                popup_html = f"""
                <div style="font-family: Arial; font-size: 12px;">
                    <b>Fecha:</b> {fecha_str}<br>
                    <b>Colonia:</b> {row[col_colonia].title()}<br>
                    <b>Atendido por:</b> Protección Civil
                </div>
                """
                folium.CircleMarker(
                    location=[row[col_lat], row[col_lon]], 
                    radius=6, 
                    color=color_map['Protección Civil'],
                    fill=True, 
                    fill_color=color_map['Protección Civil'], 
                    fill_opacity=0.8,
                    popup=folium.Popup(popup_html, max_width=300),
                    tooltip="Protección Civil"
                ).add_to(puntos_pc)
            except Exception as e:
                continue

        # Agregar puntos de Servicios Médicos
        for _, row in df_sm.iterrows():
            try:
                fecha_str = row[col_fecha].strftime('%d/%m/%Y') if hasattr(row[col_fecha], 'strftime') else str(row[col_fecha])
                popup_html = f"""
                <div style="font-family: Arial; font-size: 12px;">
                    <b>Fecha:</b> {fecha_str}<br>
                    <b>Colonia:</b> {row[col_colonia].title()}<br>
                    <b>Atendido por:</b> Servicios Médicos
                </div>
                """
                folium.CircleMarker(
                    location=[row[col_lat], row[col_lon]], 
                    radius=6, 
                    color=color_map['Servicios Médicos'],
                    fill=True, 
                    fill_color=color_map['Servicios Médicos'], 
                    fill_opacity=0.8,
                    popup=folium.Popup(popup_html, max_width=300),
                    tooltip="Servicios Médicos"
                ).add_to(puntos_sm)
            except Exception as e:
                continue

        # Agregar mapas de calor
        if not df_pc.empty:
            HeatMap(
                df_pc[[col_lat, col_lon]].values, 
                radius=15,
                gradient={0.4: 'blue', 0.65: 'lime', 1: 'red'}
            ).add_to(calor_pc)
            
        if not df_sm.empty:
            HeatMap(
                df_sm[[col_lat, col_lon]].values, 
                radius=15,
                gradient={0.4: 'blue', 0.65: 'lime', 1: 'red'}
            ).add_to(calor_sm)

        # Agregar todas las capas al mapa
        mapa.add_child(puntos_pc)
        mapa.add_child(puntos_sm)
        mapa.add_child(calor_pc)
        mapa.add_child(calor_sm)

        # Agregar leyenda personalizada si está activada
        if mostrar_leyenda:
            crear_leyenda_personalizada(mapa, color_map)

        # Control de capas
        folium.LayerControl(collapsed=True).add_to(mapa)
        
        return mapa
        
    except Exception as e:
        st.error(f"Error al crear el mapa: {str(e)}")
        return None

def guardar_mapa_html(mapa):
    """Guarda el mapa como archivo HTML temporal."""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.html', mode='w', encoding='utf-8') as tmp_file:
            mapa.save(tmp_file.name)
            with open(tmp_file.name, 'r', encoding='utf-8') as f:
                html_content = f.read()
        return html_content
    except Exception as e:
        st.error(f"Error al guardar el mapa: {str(e)}")
        return None

# --- INTERFAZ DE STREAMLIT MEJORADA ---

st.title("🚑 Generador de Mapas de Atenciones Prehospitalarias")
st.markdown("Esta herramienta te permite visualizar en un mapa interactivo los reportes de atenciones médicas.")

# --- BARRA LATERAL CON CONTROLES MEJORADA ---
with st.sidebar:
    st.header("⚙️ Configuración del Mapa")
    
    # PASO 1: Cargar archivos
    st.subheader("1. Carga tus archivos")
    uploaded_data_file = st.file_uploader(
        "Sube el archivo de atenciones (Excel o CSV)",
        type=['xlsx', 'csv'],
        key="data_uploader"
    )
    uploaded_geojson_file = st.file_uploader(
        "Sube el archivo de colonias (GeoJSON)",
        type=['geojson', 'json'],
        key="geojson_uploader"
    )

    # Opciones de visualización
    st.subheader("🎨 Opciones de Visualización")
    mostrar_leyenda = st.checkbox(
        "Mostrar leyenda de colores", 
        value=st.session_state.mostrar_leyenda,
        key="leyenda_checkbox"
    )
    
    # Actualizar estado
    st.session_state.mostrar_leyenda = mostrar_leyenda

    # Variables para almacenar selecciones
    df = None
    gj_data = None
    
    if uploaded_data_file and uploaded_geojson_file:
        try:
            # Cargar DataFrames
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
        
        col_lat = st.selectbox(
            "Columna de LATITUD:", 
            columnas_disponibles, 
            index=None,
            key="lat_select"
        )
        col_lon = st.selectbox(
            "Columna de LONGITUD:", 
            columnas_disponibles, 
            index=None,
            key="lon_select"
        )
        col_colonia = st.selectbox(
            "Columna de COLONIA:", 
            columnas_disponibles, 
            index=None,
            key="colonia_select"
        )
        col_fecha = st.selectbox(
            "Columna de FECHA:", 
            columnas_disponibles, 
            index=None,
            key="fecha_select"
        )
        col_sm = st.selectbox(
            "Columna de SERVICIOS MÉDICOS (SM):", 
            columnas_disponibles, 
            index=None,
            key="sm_select"
        )
        
        # Selección del campo del GeoJSON
        try:
            campos_geojson = list(gj_data['features'][0]['properties'].keys())
            campo_geojson_seleccionado = st.selectbox(
                "Campo con nombre de la colonia en GeoJSON:", 
                campos_geojson, 
                index=None,
                key="geojson_field_select"
            )
        except (IndexError, KeyError):
            st.error("El archivo GeoJSON no tiene un formato válido o está vacío.")
            st.stop()

        # Validar que todas las columnas necesarias han sido seleccionadas
        columnas_esenciales = [col_lat, col_lon, col_colonia, col_fecha, col_sm, campo_geojson_seleccionado]
        
        if all(columnas_esenciales):
            try:
                # PROCESAMIENTO DE DATOS
                df_procesado = df.copy()
                df_procesado['Fuente de Atención'] = np.where(
                    df_procesado[col_sm].apply(limpiar_texto) == 'sm', 
                    'Servicios Médicos', 
                    'Protección Civil'
                )
                df_procesado[col_colonia] = df_procesado[col_colonia].apply(limpiar_texto)
                df_procesado[col_lat] = pd.to_numeric(df_procesado[col_lat], errors='coerce')
                df_procesado[col_lon] = pd.to_numeric(df_procesado[col_lon], errors='coerce')
                df_procesado[col_fecha] = pd.to_datetime(df_procesado[col_fecha], errors='coerce')
                
                # Filtrar datos válidos
                df_limpio = df_procesado.dropna(subset=[col_lat, col_lon, col_fecha, col_colonia])
                
                if df_limpio.empty:
                    st.warning("⚠️ No hay datos válidos después de la limpieza.")
                    st.stop()
                
                st.subheader("3. Filtra por fecha")
                
                fecha_min = df_limpio[col_fecha].min().date()
                fecha_max = df_limpio[col_fecha].max().date()
                
                fecha_inicio, fecha_fin = st.date_input(
                    "Selecciona el rango de fechas:",
                    value=(fecha_min, fecha_max),
                    min_value=fecha_min,
                    max_value=fecha_max,
                    key="date_filter"
                )
                
                if fecha_inicio and fecha_fin:
                    # Filtrar el DataFrame
                    df_filtrado = df_limpio[
                        (df_limpio[col_fecha].dt.date >= fecha_inicio) &
                        (df_limpio[col_fecha].dt.date <= fecha_fin)
                    ]
                    
                    # Guardar en session_state para usar en el área principal
                    st.session_state.df_filtrado = df_filtrado
                    st.session_state.config = {
                        'gj_data': gj_data,
                        'campo_geojson': campo_geojson_seleccionado,
                        'col_lat': col_lat,
                        'col_lon': col_lon,
                        'col_colonia': col_colonia,
                        'col_fecha': col_fecha
                    }
                    st.session_state.mapa_generado = True
                    
            except Exception as e:
                st.error(f"Error al procesar los datos: {str(e)}")

# --- ÁREA PRINCIPAL PARA MOSTRAR EL MAPA ---
if (st.session_state.mapa_generado and 
    'df_filtrado' in st.session_state and 
    not st.session_state.df_filtrado.empty):
    
    df_filtrado = st.session_state.df_filtrado
    config = st.session_state.config
    
    st.success(f"🗺️ Mostrando {len(df_filtrado)} atenciones en el mapa.")
    
    # Mostrar métricas
    conteo_pc = (df_filtrado['Fuente de Atención'] == 'Protección Civil').sum()
    conteo_sm = (df_filtrado['Fuente de Atención'] == 'Servicios Médicos').sum()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("📊 Total de Atenciones", f"{conteo_pc + conteo_sm}")
    col2.metric("🔵 Protección Civil", f"{conteo_pc}")
    col3.metric("🔴 Servicios Médicos", f"{conteo_sm}")
    
    # Crear y mostrar el mapa
    with st.spinner("Generando mapa..."):
        mapa_final = crear_mapa(
            df_filtrado, 
            config['gj_data'], 
            config['campo_geojson'], 
            config['col_lat'], 
            config['col_lon'], 
            config['col_colonia'],
            config['col_fecha'],
            st.session_state.mostrar_leyenda
        )
    
    if mapa_final:
        # Mostrar el mapa con clave única
        st_folium(
            mapa_final, 
            width=1200, 
            height=600, 
            returned_objects=[],
            key="mapa_principal"
        )
        
        # --- BOTONES DE DESCARGA ---
        st.markdown("---")
        st.subheader("📥 Descargar Mapa")
        
        col_download1, col_download2 = st.columns(2)
        
        with col_download1:
            if st.button("💾 Descargar como HTML", use_container_width=True, key="download_html"):
                with st.spinner("Generando archivo HTML..."):
                    html_content = guardar_mapa_html(mapa_final)
                    if html_content:
                        st.download_button(
                            label="📥 Descargar HTML",
                            data=html_content,
                            file_name="mapa_atenciones_prehospitalarias.html",
                            mime="text/html",
                            key="final_download"
                        )
        
        with col_download2:
            st.info("""
            **Para guardar como imagen:**
            1. Haz clic derecho en el mapa
            2. Selecciona *'Guardar imagen como...'*
            3. Elige formato PNG o JPG
            """)

elif (uploaded_data_file and uploaded_geojson_file and 
      'df_filtrado' in st.session_state and 
      st.session_state.df_filtrado.empty):
    st.warning("⚠️ No se encontraron datos para el rango de fechas seleccionado.")
else:
    st.info("👋 ¡Bienvenido! Por favor, sube tus archivos y configura las opciones en la barra lateral para generar el mapa.")
