import streamlit as st
import sqlite3
import pandas as pd
import folium
from streamlit_folium import folium_static
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from geopy.geocoders import Nominatim

# Función para obtener coordenadas de una dirección
def obtener_coordenadas(direccion):
    geolocator = Nominatim(user_agent="lavanderia_app")
    location = geolocator.geocode(direccion)
    if location:
        return (location.latitude, location.longitude)
    else:
        raise ValueError("No se pudo encontrar la dirección")

# Conectar a la base de datos
conn = sqlite3.connect('lavanderia.db')
cursor = conn.cursor()

# Título de la aplicación
st.title("Optimización de Rutas para Lavandería")

# Menú de opciones
menu = st.sidebar.selectbox("Menú", ["Ingresar Pedido", "Ingresar Sucursal", "Solicitar Recogida", "Ver Ruta Optimizada"])

if menu == "Ingresar Pedido":
    st.header("Ingresar Nuevo Pedido")
    numero_boleta = st.text_input("Número de Boleta")
    direccion = st.text_input("Dirección")
    fecha_entrega = st.date_input("Fecha de Entrega")
    if st.button("Guardar Pedido"):
        try:
            latitud, longitud = obtener_coordenadas(direccion)
            cursor.execute('''
                INSERT INTO pedidos (numero_boleta, direccion, fecha_entrega, latitud, longitud)
                VALUES (?, ?, ?, ?, ?)
            ''', (numero_boleta, direccion, fecha_entrega, latitud, longitud))
            conn.commit()
            st.success("Pedido guardado correctamente!")
        except ValueError as e:
            st.error(f"Error: {e}")

elif menu == "Ingresar Sucursal":
    st.header("Ingresar Nueva Sucursal")
    nombre = st.text_input("Nombre de la Sucursal")
    direccion = st.text_input("Dirección")
    if st.button("Guardar Sucursal"):
        try:
            latitud, longitud = obtener_coordenadas(direccion)
            cursor.execute('''
                INSERT INTO sucursales (nombre, direccion, latitud, longitud)
                VALUES (?, ?, ?, ?)
            ''', (nombre, direccion, latitud, longitud))
            conn.commit()
            st.success("Sucursal guardada correctamente!")
        except ValueError as e:
            st.error(f"Error: {e}")

elif menu == "Solicitar Recogida":
    st.header("Solicitar Recogida")
    cursor.execute('SELECT id, nombre FROM sucursales')
    sucursales = cursor.fetchall()
    sucursal_id = st.selectbox("Seleccione la sucursal", [s[0] for s in sucursales], format_func=lambda x: [s[1] for s in sucursales if s[0] == x][0])
    fecha = st.date_input("Fecha de Recogida")
    if st.button("Solicitar Recogida"):
        cursor.execute('''
            INSERT INTO recogidas (sucursal_id, fecha)
            VALUES (?, ?)
        ''', (sucursal_id, fecha))
        conn.commit()
        st.success("Recogida solicitada correctamente!")

elif menu == "Ver Ruta Optimizada":
    st.header("Ruta Optimizada")
    fecha = st.date_input("Seleccione la fecha para ver la ruta")
    if st.button("Generar Ruta"):
        # Obtener pedidos, sucursales y recogidas para la fecha seleccionada
        cursor.execute('''
            SELECT direccion, latitud, longitud FROM pedidos
            WHERE fecha_entrega = ?
        ''', (fecha,))
        pedidos = cursor.fetchall()

        cursor.execute('''
            SELECT s.direccion, s.latitud, s.longitud
            FROM sucursales s
            JOIN recogidas r ON s.id = r.sucursal_id
            WHERE r.fecha = ?
        ''', (fecha,))
        recogidas = cursor.fetchall()

        cursor.execute('SELECT direccion, latitud, longitud FROM sucursales')
        sucursales = cursor.fetchall()

        # Combinar pedidos, sucursales y recogidas
        ubicaciones = pedidos + sucursales + recogidas

        # Crear un mapa con Folium
        mapa = folium.Map(location=[-16.3989, -71.5350], zoom_start=14)
        for ubicacion in ubicaciones:
            folium.Marker(
                location=[ubicacion[1], ubicacion[2]],
                popup=ubicacion[0]
            ).add_to(mapa)

        # Mostrar el mapa en Streamlit
        folium_static(mapa)
