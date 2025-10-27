import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap

# --- Título de la aplicación ---
st.title("Mapa Interactivo de Incidentes Urbanos - Protección Civil")

# --- Carga de archivo ---
st.sidebar.header("Cargar archivo Excel o CSV")
archivo = st.sidebar.file_uploader("Selecciona un archivo (.xlsx o .csv)", type=["xlsx", "csv"])

if archivo is not None:
    # --- Lectura de archivo ---
    try:
        if archivo.name.endswith(".xlsx"):
            df = pd.read_excel(archivo, engine="openpyxl")
        else:
            df = pd.read_csv(archivo)
    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")
        st.stop()

    # --- Normaliza los nombres de las columnas ---
    df.columns = df.columns.str.strip().str.lower().str.replace("á", "a").str.replace("é", "e").str.replace("í", "i").str.replace("ó", "o").str.replace("ú", "u")

    # --- Muestra columnas detectadas ---
    st.subheader("🧭 Columnas detectadas en el archivo")
    st.write(list(df.columns))

    # --- Intenta asignar columnas automáticamente ---
    posibles_columnas = list(df.columns)
    col_colonia = None
    col_tipo = None
    col_fecha = None

    for col in posibles_columnas:
        if "colonia" in col:
            col_colonia = col
        if "tipo" in col or "incidente" in col:
            col_tipo = col
        if "fecha" in col:
            col_fecha = col

    if not all([col_colonia, col_tipo, col_fecha]):
        st.error("⚠️ No se pudieron detectar automáticamente las columnas 'colonia', 'tipo de incidente' o 'fecha'. Verifica los nombres.")
        st.stop()

    # --- Conversión de fechas ---
    try:
        df[col_fecha] = pd.to_datetime(df[col_fecha], errors="coerce", dayfirst=True)
    except Exception as e:
        st.warning(f"No se pudo convertir la columna de fechas: {e}")

    # --- Filtros ---
    st.sidebar.header("Filtros")
    colonias = sorted(df[col_colonia].dropna().unique())
    tipos = sorted(df[col_tipo].dropna().unique())

    colonia_sel = st.sidebar.multiselect("Selecciona colonia(s)", colonias)
    tipo_sel = st.sidebar.multiselect("Selecciona tipo(s) de incidente", tipos)

    df_filtrado = df.copy()
    if colonia_sel:
        df_filtrado = df_filtrado[df_filtrado[col_colonia].isin(colonia_sel)]
    if tipo_sel:
        df_filtrado = df_filtrado[df_filtrado[col_tipo].isin(tipo_sel)]

    st.subheader("📊 Datos filtrados")
    st.dataframe(df_filtrado)

    # --- Verifica coordenadas ---
    posibles_lat = [c for c in df.columns if "lat" in c]
    posibles_lon = [c for c in df.columns if "lon" in c or "long" in c]

    if not posibles_lat or not posibles_lon:
        st.error("⚠️ No se detectaron columnas de latitud y longitud en el archivo.")
        st.stop()

    lat_col = posibles_lat[0]
    lon_col = posibles_lon[0]

    # --- Mapa base ---
    st.subheader("🗺️ Mapa de Incidentes")
    if not df_filtrado.empty:
        lat_centro = df_filtrado[lat_col].mean()
        lon_centro = df_filtrado[lon_col].mean()
    else:
        lat_centro = df[lat_col].mean()
        lon_centro = df[lon_col].mean()

    mapa = folium.Map(location=[lat_centro, lon_centro], zoom_start=13)

    # --- Marcadores ---
    for _, fila in df_filtrado.iterrows():
        try:
            popup_text = f"""
            <b>Colonia:</b> {fila[col_colonia]}<br>
            <b>Tipo:</b> {fila[col_tipo]}<br>
            <b>Fecha:</b> {fila[col_fecha].strftime('%d/%m/%Y') if pd.notnull(fila[col_fecha]) else 'N/A'}<br>
            """
            folium.Marker(
                [fila[lat_col], fila[lon_col]],
                popup=popup_text,
                icon=folium.Icon(color="red", icon="info-sign")
            ).add_to(mapa)
        except:
            continue

    # --- Heatmap ---
    heat_data = df_filtrado[[lat_col, lon_col]].dropna().values.tolist()
    if heat_data:
        HeatMap(heat_data, radius=12).add_to(mapa)

    # --- Muestra el mapa en Streamlit ---
    st_folium(mapa, width=800, height=500)

else:
    st.info("📂 Carga un archivo para comenzar.")
