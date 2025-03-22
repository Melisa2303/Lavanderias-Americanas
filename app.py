import streamlit as st
import sqlite3
import pandas as pd
import folium
from streamlit_folium import folium_static
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

# Función para obtener coordenadas de una dirección
def obtener_coordenadas(direccion):
    geolocator = Nominatim(user_agent="lavanderia_app")
    location = geolocator.geocode(direccion)
    if location:
        return (location.latitude, location.longitude)
    else:
        raise ValueError("No se pudo encontrar la dirección")

# Función para calcular la matriz de distancias
def calcular_matriz_distancias(ubicaciones):
    matriz = []
    for i in range(len(ubicaciones)):
        fila = []
        for j in range(len(ubicaciones)):
            if i == j:
                fila.append(0)  # Distancia de un punto a sí mismo es 0
            else:
                distancia = geodesic((ubicaciones[i][1], ubicaciones[i][2]), (ubicaciones[j][1], ubicaciones[j][2])).km
                fila.append(distancia)
        matriz.append(fila)
    return matriz

# Función para optimizar la ruta usando OR-Tools
def optimizar_ruta(matriz_distancias):
    manager = pywrapcp.RoutingIndexManager(len(matriz_distancias), 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        return matriz_distancias[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC

    solution = routing.SolveWithParameters(search_parameters)

    if solution:
        index = routing.Start(0)
        ruta = []
        while not routing.IsEnd(index):
            ruta.append(manager.IndexToNode(index))
            index = solution.Value(routing.NextVar(index))
        return ruta
    else:
        return None

# Conectar a la base de datos
conn = sqlite3.connect('lavanderia.db')
cursor = conn.cursor()

# Crear tablas si no existen
cursor.execute('''
    CREATE TABLE IF NOT EXISTS pedidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_boleta TEXT,
        direccion TEXT,
        fecha_entrega DATE,
        latitud REAL,
        longitud REAL
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS sucursales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        direccion TEXT,
        latitud REAL,
        longitud REAL
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS recogidas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sucursal_id INTEGER,
        fecha DATE,
        FOREIGN KEY (sucursal_id) REFERENCES sucursales(id)
    )
''')
conn.commit()

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

        # Calcular la matriz de distancias
        matriz_distancias = calcular_matriz_distancias(ubicaciones)

        # Optimizar la ruta
        ruta_optimizada = optimizar_ruta(matriz_distancias)

        if ruta_optimizada:
            st.write("Ruta optimizada:", ruta_optimizada)

            # Crear un mapa con Folium
            mapa = folium.Map(location=[-16.3989, -71.5350], zoom_start=14)
            for i, idx in enumerate(ruta_optimizada):
                ubicacion = ubicaciones[idx]
                folium.Marker(
                    location=[ubicacion[1], ubicacion[2]],
                    popup=f"Punto {i+1}: {ubicacion[0]}"
                ).add_to(mapa)

            # Dibujar la ruta optimizada
            for i in range(len(ruta_optimizada) - 1):
                punto_actual = ubicaciones[ruta_optimizada[i]]
                punto_siguiente = ubicaciones[ruta_optimizada[i + 1]]
                folium.PolyLine(
                    locations=[[punto_actual[1], punto_actual[2]], [punto_siguiente[1], punto_siguiente[2]]],
                    color="blue"
                ).add_to(mapa)

            # Mostrar el mapa en Streamlit
            folium_static(mapa)
        else:
            st.error("No se pudo optimizar la ruta.")
