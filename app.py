import streamlit as st
import sqlite3
import folium
from streamlit_folium import folium_static
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from datetime import timedelta
import openrouteservice as ors

# Configura la API key de OpenRouteService
ors_api_key = "5b3ce3597851110001cf62486bc22aa6557847f3a94a99f41f14ec16"  # Reemplaza con tu API key

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

# Función para obtener la ruta real usando OpenRouteService
def obtener_ruta_real(coordenadas, api_key):
    client = ors.Client(key=api_key)
    try:
        ruta = client.directions(
            coordinates=coordenadas,
            profile='driving-car',  # Puedes cambiar a 'foot-walking' o 'cycling-regular'
            format='geojson'
        )
        return ruta
    except Exception as e:
        st.error(f"Error al calcular la ruta: {e}")
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

# Crear la tabla clientes_delivery si no existe
cursor.execute('''
    CREATE TABLE IF NOT EXISTS clientes_delivery (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        telefono TEXT NOT NULL,
        direccion TEXT NOT NULL,
        fecha_recogida DATE NOT NULL
    )
''')
conn.commit()

# Crear la tabla entregas si no existe
cursor.execute('''
    CREATE TABLE IF NOT EXISTS entregas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT NOT NULL,
        sucursal_id INTEGER,
        cliente_id INTEGER,
        fecha_entrega DATE NOT NULL,
        FOREIGN KEY (sucursal_id) REFERENCES sucursales(id),
        FOREIGN KEY (cliente_id) REFERENCES clientes_delivery(id)
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
    
    # Opción para seleccionar entre Sucursal o Cliente Delivery
    tipo_recogida = st.radio("Seleccione el tipo de recogida:", ("Sucursal", "Cliente Delivery"))

    if tipo_recogida == "Sucursal":
        # Opción de recogida en sucursal
        st.subheader("Registrar Recogida de Sucursal")
        cursor.execute('SELECT id, nombre FROM sucursales')
        sucursales = cursor.fetchall()
        sucursal_id = st.selectbox("Seleccione la sucursal", [s[0] for s in sucursales], format_func=lambda x: [s[1] for s in sucursales if s[0] == x][0])
        fecha_recogida = st.date_input("Fecha de Recogida")
        
        if st.button("Solicitar Recogida"):
            # Registrar la recogida en la tabla recogidas
            cursor.execute('''
                INSERT INTO recogidas (sucursal_id, fecha)
                VALUES (?, ?)
            ''', (sucursal_id, fecha_recogida))
            conn.commit()

            # Programar la entrega dos días después
            fecha_entrega = fecha_recogida + timedelta(days=2)
            cursor.execute('''
                INSERT INTO entregas (tipo, sucursal_id, fecha_entrega)
                VALUES (?, ?, ?)
            ''', ("sucursal", sucursal_id, fecha_entrega))
            conn.commit()

            st.success(f"Recogida en sucursal solicitada correctamente. La entrega ha sido agendada para el {fecha_entrega}.")

    elif tipo_recogida == "Cliente Delivery":
        # Opción de recogida a domicilio (nueva)
        st.subheader("Registrar Cliente para Recogida a Domicilio")
        nombre_cliente = st.text_input("Nombre del Cliente")
        telefono_cliente = st.text_input("Teléfono del Cliente")
        direccion_cliente = st.text_input("Dirección del Cliente")
        fecha_recogida = st.date_input("Fecha de Recogida")
        
        if st.button("Registrar Cliente para Recogida"):
            if nombre_cliente and telefono_cliente and direccion_cliente:
                # Registrar el cliente en la tabla clientes_delivery
                cursor.execute('''
                    INSERT INTO clientes_delivery (nombre, telefono, direccion, fecha_recogida)
                    VALUES (?, ?, ?, ?)
                ''', (nombre_cliente, telefono_cliente, direccion_cliente, fecha_recogida))
                cliente_id = cursor.lastrowid  # Obtener el ID del cliente recién insertado
                conn.commit()

                # Programar la entrega dos días después
                fecha_entrega = fecha_recogida + timedelta(days=2)
                cursor.execute('''
                    INSERT INTO entregas (tipo, cliente_id, fecha_entrega)
                    VALUES (?, ?, ?)
                ''', ("delivery", cliente_id, fecha_entrega))
                conn.commit()

                st.success(f"Cliente registrado para recogida a domicilio correctamente. La entrega ha sido agendada para el {fecha_entrega}.")
            else:
                st.error("Por favor, complete todos los campos.")

elif menu == "Datos Clientes de Delivery":
    st.header("Datos Clientes de Delivery")
    
    # Obtener todos los clientes de delivery de la base de datos
    cursor.execute('SELECT * FROM clientes_delivery')
    clientes_delivery = cursor.fetchall()
    
    if clientes_delivery:
        # Mostrar los datos en una tabla
        st.subheader("Lista de Clientes de Delivery")
        df = pd.DataFrame(clientes_delivery, columns=["ID", "Nombre", "Teléfono", "Dirección", "Fecha de Recogida"])
        st.dataframe(df)
    else:
        st.info("No hay clientes de delivery registrados.")

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

        # Obtener entregas programadas para la fecha seleccionada
        cursor.execute('''
            SELECT 
                CASE 
                    WHEN e.tipo = 'sucursal' THEN s.direccion
                    WHEN e.tipo = 'delivery' THEN c.direccion
                END AS direccion,
                CASE 
                    WHEN e.tipo = 'sucursal' THEN s.latitud
                    WHEN e.tipo = 'delivery' THEN c.latitud
                END AS latitud,
                CASE 
                    WHEN e.tipo = 'sucursal' THEN s.longitud
                    WHEN e.tipo = 'delivery' THEN c.longitud
                END AS longitud
            FROM entregas e
            LEFT JOIN sucursales s ON e.sucursal_id = s.id
            LEFT JOIN clientes_delivery c ON e.cliente_id = c.id
            WHERE e.fecha_entrega = ?
        ''', (fecha,))
        entregas = cursor.fetchall()

        # Combinar pedidos, sucursales, recogidas y entregas
        ubicaciones = pedidos + recogidas + entregas

        # Calcular la matriz de distancias
        matriz_distancias = calcular_matriz_distancias(ubicaciones)

        # Optimizar la ruta
        ruta_optimizada = optimizar_ruta(matriz_distancias)

        if ruta_optimizada:
            st.write("Ruta optimizada:")
            for i, idx in enumerate(ruta_optimizada):
                st.write(f"{i+1}. {ubicaciones[idx][0]}")  # Muestra los nombres de las ubicaciones

            # Obtener coordenadas en el orden optimizado
            coordenadas_ruta = [[ubicaciones[idx][2], ubicaciones[idx][1]] for idx in ruta_optimizada]

            # Obtener la ruta real usando OpenRouteService
            ruta_real = obtener_ruta_real(coordenadas_ruta, ors_api_key)

            if ruta_real:
                # Crear un mapa con Folium
                mapa = folium.Map(location=[-16.3989, -71.5350], zoom_start=14)

                # Dibujar la ruta real
                folium.GeoJson(ruta_real, name="Ruta optimizada").add_to(mapa)

                # Añadir marcadores para cada punto
                for idx in ruta_optimizada:
                    ubicacion = ubicaciones[idx]
                    folium.Marker(
                        location=[ubicacion[1], ubicacion[2]],
                        popup=ubicacion[0]
                    ).add_to(mapa)

                # Mostrar el mapa en Streamlit
                folium_static(mapa)
            else:
                st.error("No se pudo calcular la ruta real.")
        else:
            st.error("No se pudo optimizar la ruta.")
