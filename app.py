import streamlit as st
import sqlite3
import folium
import pandas as pd
from streamlit_folium import folium_static
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from datetime import timedelta
import openrouteservice as ors

# Configura la API key de OpenRouteService
ors_api_key = "5b3ce3597851110001cf62486bc22aa6557847f3a94a99f41f14ec16"  # Reemplaza con tu API key

# Mostrar el logo y el nombre de la lavandería
col1, col2 = st.columns([1, 4])  # Divide la cabecera en dos columnas

with col1:
    # Mostrar el logo (asegúrate de que el archivo "logo.png" esté en la misma carpeta)
    st.image("https://github.com/Melisa2303/Lavanderias-Americanas/blob/main/LOGO.PNG?raw=true", width=100)  # Ajusta el ancho según sea necesario

with col2:
    # Mostrar el nombre de la lavandería
    st.title("Lavanderías Americanas") 

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

# Crear la tabla boletas si no existe
cursor.execute('''
    CREATE TABLE IF NOT EXISTS boletas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_boleta TEXT NOT NULL,
        nombre_cliente TEXT NOT NULL,
        dni_cliente TEXT NOT NULL,
        monto_pagar REAL NOT NULL,
        medio_pago TEXT NOT NULL,
        tipo_entrega TEXT NOT NULL,
        sucursal_id INTEGER,
        fecha_registro DATE  -- Nueva columna para la fecha de registro
    )
''')
conn.commit()

# Título de la aplicación
st.title("Optimización de Rutas para Lavandería")

# Menú de opciones
menu = st.sidebar.selectbox("Menú", ["Ingresar Boleta", "Ingresar Sucursal", "Solicitar Recogida", "Datos de Recojos", "Datos de Boletas Registradas", "Ver Ruta Optimizada"])

if menu == "Ingresar Boleta":
    st.header("Ingresar Boleta")
    
    # Campos para ingresar los datos de la boleta
    numero_boleta = st.text_input("Número de Boleta")
    nombre_cliente = st.text_input("Nombre del Cliente")
    dni_cliente = st.text_input("DNI del Cliente")

    # Crear dos columnas para Monto a Pagar y Medio de 
    col1, col2 = st.columns(2)  # Dos columnas de igual ancho

    with col1:
        monto_pagar = st.number_input("Monto a Pagar", min_value=0.0, format="%.2f")

    with col2:
        medio_pago = st.selectbox("Medio de ", ["Efectivo", "Yape", "Plin", "Transferencia"])
    
    # Campo para seleccionar la fecha de registro
    fecha_registro = st.date_input("Fecha de Registro")

    # Opciones de entrega: Sucursal o Delivery
    tipo_entrega = st.radio("Tipo de Entrega", ("Sucursal", "Delivery"))

    if tipo_entrega == "Sucursal":
        # Si es entrega en sucursal, mostrar un desplegable para elegir la sucursal
        cursor.execute('SELECT id, nombre FROM sucursales')
        sucursales = cursor.fetchall()
        sucursal_id = st.selectbox("Seleccione la sucursal", [s[0] for s in sucursales], format_func=lambda x: [s[1] for s in sucursales if s[0] == x][0])
        direccion = None  # No se necesita dirección para entrega en sucursal
    elif tipo_entrega == "Delivery":
        # Si es delivery, no se pide la dirección
        sucursal_id = None  # No se necesita sucursal para delivery
        direccion = None  # No se necesita dirección

    # Botón para guardar la boleta
    if st.button("Guardar Boleta"):
        if numero_boleta and nombre_cliente and dni_cliente and monto_pagar and medio_pago:
            # Insertar los datos en la tabla boletas
            cursor.execute('''
                INSERT INTO boletas (
                    numero_boleta, nombre_cliente, dni_cliente, monto_pagar, medio_pago, tipo_entrega, sucursal_id, direccion, fecha_registro
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (numero_boleta, nombre_cliente, dni_cliente, monto_pagar, medio_pago, tipo_entrega, sucursal_id, direccion, fecha_registro))
            conn.commit()
            st.success("Boleta guardada correctamente!")
        else:
            st.error("Por favor, complete todos los campos.")

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
            fecha_entrega = fecha_recogida + timedelta(days=3)
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
                fecha_entrega = fecha_recogida + timedelta(days=3)
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

elif menu == "Datos de Recojos":
    st.header("Datos de Recojos")
    
    # Filtro por fecha
    fecha_filtro = st.date_input("Filtrar por fecha")

    # Mostrar recojos en sucursal
    st.subheader("Recojos en Sucursal")
    cursor.execute('''
        SELECT s.direccion, r.fecha
        FROM recogidas r
        JOIN sucursales s ON r.sucursal_id = s.id
        WHERE r.fecha = ?
    ''', (fecha_filtro,))
    recojos_sucursal = cursor.fetchall()

    if recojos_sucursal:
        df_sucursal = pd.DataFrame(recojos_sucursal, columns=["Dirección de la Sucursal", "Fecha de Recojo"])
        st.dataframe(df_sucursal)
    else:
        st.info("No hay recojos en sucursal para la fecha seleccionada.")

    # Mostrar recojos de clientes (delivery)
    st.subheader("Recojos de Clientes (Delivery)")
    cursor.execute('''
        SELECT nombre, telefono, direccion, fecha_recogida
        FROM clientes_delivery
        WHERE fecha_recogida = ?
    ''', (fecha_filtro,))
    recojos_delivery = cursor.fetchall()

    if recojos_delivery:
        df_delivery = pd.DataFrame(recojos_delivery, columns=["Nombre del Cliente", "Teléfono", "Dirección", "Fecha de Recojo"])
        st.dataframe(df_delivery)
    else:
        st.info("No hay recojos de clientes (delivery) para la fecha seleccionada.")

elif menu == "Datos de Boletas Registradas":
    st.header("Datos de Boletas Registradas")
    
    # Filtro por rango de fechas
    st.subheader("Filtrar por Rango de Fechas")
    fecha_inicio = st.date_input("Fecha de inicio")
    fecha_fin = st.date_input("Fecha de fin")

    # Filtro por tipo de entrega (sucursal o delivery)
    st.subheader("Filtrar por Tipo de Entrega")
    tipo_entrega_filtro = st.radio("Tipo de entrega", ("Todas", "Sucursal", "Delivery"))

    # Si el tipo de entrega es sucursal, mostrar un desplegable para elegir la sucursal
    sucursal_filtro = None
    if tipo_entrega_filtro == "Sucursal":
        cursor.execute('SELECT id, nombre FROM sucursales')
        sucursales = cursor.fetchall()
        if sucursales:
            sucursal_filtro = st.selectbox("Seleccione la sucursal", [s[0] for s in sucursales], format_func=lambda x: [s[1] for s in sucursales if s[0] == x][0])
        else:
            st.warning("No hay sucursales registradas.")

    # Construir la consulta SQL según los filtros seleccionados
    query = '''
        SELECT 
            b.numero_boleta, 
            b.nombre_cliente, 
            b.dni_cliente, 
            b.monto_pagar, 
            b.medio_pago, 
            b.tipo_entrega, 
            s.nombre AS sucursal, 
            b.fecha_registro
        FROM boletas b
        LEFT JOIN sucursales s ON b.sucursal_id = s.id
        WHERE 1=1
    '''
    params = []

    # Aplicar filtro por rango de fechas
    if fecha_inicio and fecha_fin:
        query += " AND b.fecha_registro BETWEEN ? AND ?"
        params.extend([fecha_inicio, fecha_fin])

    # Aplicar filtro por tipo de entrega
    if tipo_entrega_filtro == "Sucursal":
        if sucursal_filtro:
            query += " AND b.tipo_entrega = ? AND b.sucursal_id = ?"
            params.extend(["Sucursal", sucursal_filtro])
        else:
            st.warning("Seleccione una sucursal para filtrar.")
    elif tipo_entrega_filtro == "Delivery":
        query += " AND b.tipo_entrega = ?"
        params.append("Delivery")

    # Ejecutar la consulta
    try:
        cursor.execute(query, params)
        boletas_filtradas = cursor.fetchall()

        # Mostrar los resultados en una tabla
        if boletas_filtradas:
            st.subheader("Boletas Registradas")
            df = pd.DataFrame(boletas_filtradas, columns=[
                "Número de Boleta", "Nombre del Cliente", "DNI", "Monto a Pagar", 
                "Medio de Pago", "Tipo de Entrega", "Sucursal", "Dirección", "Fecha de Registro"
            ])
            st.dataframe(df)

            # Botón para exportar a Excel
            if st.button("Exportar a Excel"):
                # Crear un archivo Excel
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Boletas')
                output.seek(0)

                # Descargar el archivo
                st.download_button(
                    label="Descargar archivo Excel",
                    data=output,
                    file_name="boletas_registradas.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.success("Archivo Excel generado correctamente.")
        else:
            st.info("No hay boletas registradas que coincidan con los filtros seleccionados.")
    except sqlite3.OperationalError as e:
        st.error(f"Error al ejecutar la consulta SQL: {e}")
    except Exception as e:
        st.error(f"Error inesperado: {e}")
        
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
        ubicaciones = recogidas + entregas

        # Calcular la matriz de distancias
        with st.spinner("Calculando matriz de distancias..."):
            matriz_distancias = calcular_matriz_distancias(ubicaciones)

        # Optimizar la ruta
        with st.spinner("Optimizando ruta..."):
            ruta_optimizada = optimizar_ruta(matriz_distancias)

        if ruta_optimizada:
            st.write("Ruta optimizada:")
            for i, idx in enumerate(ruta_optimizada):
                st.write(f"{i+1}. {ubicaciones[idx][0]}")  # Muestra los nombres de las ubicaciones

            # Obtener coordenadas en el orden optimizado
            coordenadas_ruta = [[ubicaciones[idx][2], ubicaciones[idx][1]] for idx in ruta_optimizada]

            # Obtener la ruta real usando OpenRouteService
            with st.spinner("Calculando ruta real..."):
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
