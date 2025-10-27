# --- IMPORTS NECESARIOS ---
import pandas as pd
import json
import folium
from folium.plugins import HeatMap
from io import BytesIO
import streamlit as st
import unicodedata
from streamlit_folium import st_folium

# --- FUNCIÓN DE LIMPIEZA DE DATOS ---
def limpiar_texto(texto):
    if not isinstance(texto, str):
        return texto
    texto_limpio = unicodedata.normalize('NFD', texto) \
                              .encode('ascii', 'ignore') \
                              .decode('utf-8') \
                              .lower() \
                              .strip()
    if texto_limpio.startswith('deslizamiento de tierra/talud'):
        return 'deslizamiento de tierra/talud'
    return texto_limpio

# ------------------- CARGA DE ARCHIVOS -------------------
def cargar_archivo():
    archivo = st.file_uploader("📁 Cargar archivo de datos (.csv o .xlsx)", type=["csv", "xlsx"])
    if archivo:
        if archivo.name.endswith(".csv"):
            return pd.read_csv(archivo)
        else:
            return pd.read_excel(archivo)
    return None

def cargar_geojson_y_seleccionar_campo():
    geojson_file = st.file_uploader("🌍 Cargar archivo GeoJSON", type=["geojson", "json"])
    if geojson_file:
        data = json.load(geojson_file)
        campos = list(data['features'][0]['properties'].keys())
        campo_colonia_geojson = st.selectbox("🗂️ Selecciona el campo que representa el nombre de la colonia:", campos)
        return geojson_file, campo_colonia_geojson
    return None, None

# ------------------- SELECCIÓN DE COLUMNAS -------------------
def seleccionar_columnas(df):
    st.subheader("🧩 Selecciona las columnas necesarias")
    col_lat = st.selectbox("Columna de LATITUD:", df.columns)
    col_lon = st.selectbox("Columna de LONGITUD:", df.columns)
    col_colonia = st.selectbox("Columna de COLONIA:", df.columns)
    col_tipo = st.selectbox("Columna de TIPO DE INCIDENTE:", df.columns)
    col_desc = st.selectbox("Columna de DESCRIPCIÓN (opcional):", [None] + list(df.columns))
    col_fecha = st.selectbox("Columna de FECHA:", df.columns)
    return col_lat, col_lon, col_colonia, col_tipo, col_desc, col_fecha

# ------------------- LEYENDA -------------------
def agregar_leyenda(mapa, color_map):
    items_html = "".join([f' &nbsp; <i style="background:{color}; width:15px; height:15px; float:left; margin-right:8px;"></i> {tipo}<br>' for tipo, color in color_map.items()])
    leyenda_html = f'''
     <div style="
     position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%);
     width: auto; background-color: rgba(255, 255, 255, 0.9);
     border:2px solid grey; border-radius: 8px; z-index:9999;
     font-size:14px; padding: 10px; box-shadow: 3px 3px 150px rgba(0,0,0,0.3);">
     <b>Leyenda de colores</b><br>{items_html}</div>'''
    mapa.get_root().html.add_child(folium.Element(leyenda_html))

# ------------------- CENTROIDE -------------------
def _centroide_feature(feature):
    geom = feature.get("geometry", {})
    gtype, coords = geom.get("type"), geom.get("coordinates", [])
    def _centroide_de_aro(aro):
        if not aro: return None, None
        lons, lats = [p[0] for p in aro], [p[1] for p in aro]
        return (sum(lats)/len(lats), sum(lons)/len(lons))
    if gtype == "Polygon": return _centroide_de_aro(coords[0] if coords else [])
    if gtype == "MultiPolygon":
        best = max((poly[0] for poly in coords if poly), key=len, default=[])
        return _centroide_de_aro(best)
    return None, None

# --- CREACIÓN DEL MAPA ---
def crear_mapa(df, geojson_data, campo_geojson, col_lat, col_lon, col_colonia, col_tipo, col_desc, col_fecha):
    df[col_lat] = pd.to_numeric(df[col_lat], errors='coerce')
    df[col_lon] = pd.to_numeric(df[col_lon], errors='coerce')
    df = df.dropna(subset=[col_lat, col_lon, col_colonia, col_tipo, col_fecha])
    if df.empty:
        st.warning("⚠️ No hay datos válidos para generar el mapa.")
        return None

    centro = [df[col_lat].mean(), df[col_lon].mean()]
    mapa = folium.Map(location=centro, zoom_start=14)

    tipos_unicos = df[col_tipo].unique()
    colores = ['#e41a1c','#377eb8','#4daf4a','#984ea3','#ff7f00','#ffff33','#a65628','#f781bf']
    color_map = {tipo: colores[i % len(colores)] for i, tipo in enumerate(tipos_unicos)}

    # Limpieza de nombres dentro del GeoJSON
    for feature in geojson_data['features']:
        if campo_geojson in feature['properties']:
            feature['properties'][campo_geojson] = limpiar_texto(feature['properties'][campo_geojson])

    folium.GeoJson(geojson_data, name='Colonias',
                   tooltip=folium.GeoJsonTooltip(fields=[campo_geojson], aliases=['Colonia:'])
                   ).add_to(mapa)

    # Etiquetas de colonias
    capa_etiquetas = folium.FeatureGroup(name="Nombres de colonias", show=True)
    for feat in geojson_data.get("features", []):
        nombre = feat.get("properties", {}).get(campo_geojson)
        lat, lon = _centroide_feature(feat)
        if nombre and lat and lon:
            folium.Marker(
                location=[lat, lon],
                icon=folium.DivIcon(html=f'''<div style="color:black;font-weight:bold;
                        background:transparent;padding:3px;">{nombre}</div>''')
            ).add_to(capa_etiquetas)
    capa_etiquetas.add_to(mapa)

    # Incidentes
    capa_incidentes = folium.FeatureGroup(name="Incidentes", show=True)
    for _, row in df.iterrows():
        popup_text = f"<b>Fecha:</b> {row[col_fecha].date()}<br><b>Colonia:</b> {row[col_colonia]}<br><b>Tipo:</b> {row[col_tipo]}"
        if col_desc and pd.notna(row.get(col_desc)):
            popup_text += f"<br><b>Descripción:</b> {row.get(col_desc, '')}"
        color_incidente = color_map.get(row[col_tipo], '#000000')
        folium.CircleMarker(
            location=[row[col_lat], row[col_lon]], radius=7, color=color_incidente,
            fill=True, fill_color=color_incidente, fill_opacity=0.8,
            popup=folium.Popup(popup_text, max_width=300)
        ).add_to(capa_incidentes)
    capa_incidentes.add_to(mapa)

    capa_calor = folium.FeatureGroup(name="Mapa de Calor", show=False)
    HeatMap(df[[col_lat, col_lon]].values.tolist()).add_to(capa_calor)
    capa_calor.add_to(mapa)

    folium.LayerControl(collapsed=False).add_to(mapa)
    agregar_leyenda(mapa, color_map)
    return mapa

# ------------------- APLICACIÓN STREAMLIT -------------------
st.title("🗺️ Mapa de Incidentes - Protección Civil La Magdalena Contreras")

df = cargar_archivo()
geojson_file, campo_geojson = cargar_geojson_y_seleccionar_campo()

if df is not None and geojson_file is not None:
    columnas = seleccionar_columnas(df)
    col_lat, col_lon, col_colonia, col_tipo, col_desc, col_fecha = columnas

    # Limpieza y conversión
    df[col_tipo] = df[col_tipo].apply(limpiar_texto)
    df[col_colonia] = df[col_colonia].apply(limpiar_texto)
    df[col_fecha] = pd.to_datetime(df[col_fecha], errors='coerce')
    df = df.dropna(subset=[col_fecha])

    # Filtros
    st.subheader("📆 Filtros")
    min_fecha, max_fecha = df[col_fecha].min().date(), df[col_fecha].max().date()
    rango_fechas = st.date_input("Selecciona rango de fechas", [min_fecha, max_fecha], min_value=min_fecha, max_value=max_fecha)

    if len(rango_fechas) == 2:
        inicio, fin = pd.to_datetime(rango_fechas[0]), pd.to_datetime(rango_fechas[1])
        df = df[(df[col_fecha] >= inicio) & (df[col_fecha] <= fin)]

    tipos = sorted(df[col_tipo].unique())
    tipos_seleccionados = st.multiselect("Selecciona tipo(s) de incidente", ["Todos"] + tipos, default="Todos")

    if "Todos" not in tipos_seleccionados:
        df = df[df[col_tipo].isin(tipos_seleccionados)]

    if not df.empty:
        geojson_data = json.load(geojson_file)
        mapa = crear_mapa(df, geojson_data, campo_geojson, *columnas)
        if mapa:
            st_data = st_folium(mapa, width=1200, height=700)
    else:
        st.warning("⚠️ No hay datos que coincidan con los filtros seleccionados.")
else:
    st.info("📂 Carga un archivo CSV/Excel y un GeoJSON para comenzar.")
