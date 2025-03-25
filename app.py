import streamlit as st
import psycopg2
from psycopg2 import sql
import folium
import pandas as pd
from streamlit_folium import folium_static
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from datetime import timedelta
import datetime
import openrouteservice as ors
import io
import os
from dotenv import load_dotenv
from config import get_db_config

# Cargar variables de entorno
load_dotenv()

# Configura la API key de OpenRouteService
ors_api_key = "5b3ce3597851110001cf62486bc22aa6557847f3a94a99f41f14ec16"  # Reemplaza con tu API key

# app.py - Conexión directa (SOLO PARA PRUEBAS)

def conectar_db():
    try:
        return psycopg2.connect(
            host="db.iplccwzxyprinddvskyz.supabase.co",  # Reemplaza con tu host real
            dbname="postgres",
            user="postgres",
            password="lavamer123",  # Contraseña directa aquí
            port="5432",
            sslmode="require"
        )
    except Exception as e:
        print(f"Error de conexión: {e}")
        return None

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

#Creacion de tablas
def inicializar_tablas():
    conn = conectar_db()
    if conn:
        cursor = conn.cursor()
        
        comandos = [
            '''CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                usuario VARCHAR(255) UNIQUE NOT NULL,
                contraseña VARCHAR(255) NOT NULL,
                perfil VARCHAR(255) NOT NULL
            )''',
            '''CREATE TABLE IF NOT EXISTS sucursales (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(255),
                direccion TEXT,
                latitud FLOAT,
                longitud FLOAT
            )''',
            '''CREATE TABLE IF NOT EXISTS recogidas (
                id SERIAL PRIMARY KEY,
                sucursal_id INTEGER REFERENCES sucursales(id),
                fecha DATE
            )''',
            '''CREATE TABLE IF NOT EXISTS clientes_delivery (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(255) NOT NULL,
                telefono VARCHAR(20) NOT NULL,
                direccion TEXT NOT NULL,
                fecha_recogida DATE NOT NULL
            )''',
            '''CREATE TABLE IF NOT EXISTS entregas (
                id SERIAL PRIMARY KEY,
                tipo VARCHAR(50) NOT NULL,
                sucursal_id INTEGER REFERENCES sucursales(id),
                cliente_id INTEGER REFERENCES clientes_delivery(id),
                fecha_entrega DATE NOT NULL
            )''',
            '''CREATE TABLE IF NOT EXISTS boletas (
                id SERIAL PRIMARY KEY,
                numero_boleta VARCHAR(255) NOT NULL,
                nombre_cliente VARCHAR(255) NOT NULL,
                dni_cliente VARCHAR(20) NOT NULL,
                monto_pagar FLOAT NOT NULL,
                medio_pago VARCHAR(50) NOT NULL,
                tipo_entrega VARCHAR(50) NOT NULL,
                sucursal_id INTEGER REFERENCES sucursales(id),
                fecha_registro DATE,
                direccion TEXT
            )'''
        ]
        
        try:
            for comando in comandos:
                cursor.execute(comando)
            conn.commit()
            
            # Insertar usuarios de prueba si no existen
            cursor.execute('''
                INSERT INTO usuarios (usuario, contraseña, perfil)
                VALUES (%s, %s, %s)
                ON CONFLICT (usuario) DO NOTHING
            ''', ("admin", "admin123", "Administrador"))
            cursor.execute('''
                INSERT INTO usuarios (usuario, contraseña, perfil)
                VALUES (%s, %s, %s)
                ON CONFLICT (usuario) DO NOTHING
            ''', ("chofer", "chofer123", "Chofer"))
            cursor.execute('''
                INSERT INTO usuarios (usuario, contraseña, perfil)
                VALUES (%s, %s, %s)
                ON CONFLICT (usuario) DO NOTHING
            ''', ("sucursal", "sucursal123", "Sucursal"))
            conn.commit()
            
        except Exception as e:
            st.error(f"Error al crear tablas: {e}")
        finally:
            cursor.close()
            conn.close()

# Ejecutar solo una vez (luego comentar)
inicializar_tablas()

# Función para verificar el inicio de sesión
def verificar_login(usuario, contraseña):
    # Usuarios de prueba directos en el código
    usuarios = {
        "admin": {"password": "admin123", "perfil": "Administrador"},
        "chofer": {"password": "chofer123", "perfil": "Chofer"},
        "sucursal": {"password": "sucursal123", "perfil": "Sucursal"}
    }
    
    if usuario in usuarios and usuarios[usuario]["password"] == contraseña:
        return usuarios[usuario]["perfil"]
    return None

# Pantalla de inicio de sesión
# Función de login optimizada
def mostrar_login():
    # Contenedor para el formulario de login
    login_container = st.empty()
    
    with login_container.container():
        # Mostrar logo y nombre de la empresa
        col1, col2 = st.columns([1, 4])
        with col1:
            st.image("https://github.com/Melisa2303/Lavanderias-Americanas/blob/main/LOGO.PNG?raw=true", width=100)
        with col2:
            st.title("Lavanderías Americanas")
        
        # Formulario de login
        with st.form("login_form"):
            usuario = st.text_input("Usuario")
            contraseña = st.text_input("Contraseña", type="password")
            
            if st.form_submit_button("Ingresar"):
                perfil = verificar_login(usuario, contraseña)
                if perfil:
                    st.session_state.update({
                        'perfil': perfil,
                        'usuario': usuario,
                        'logged_in': True,
                        'first_login': True  # Para mostrar bienvenida
                    })
                    login_container.empty()  # Limpiar el login
                    st.rerun()  # Forzar actualización inmediata
                    return
                else:
                    st.error("Credenciales incorrectas")

# Función para mostrar el menú según el perfil
def mostrar_menu():
    if st.session_state['perfil'] == "Administrador":
        menu = st.sidebar.selectbox("Menú", [
            "Ingresar Boleta", "Ingresar Sucursal", "Solicitar Recogida",
            "Datos de Recojos", "Datos de Boletas Registradas", "Ver Ruta Optimizada"
        ])
    elif st.session_state['perfil'] == "Chofer":
        menu = st.sidebar.selectbox("Menú", [
            "Ver Ruta Optimizada", "Datos de Recojos"
        ])
    elif st.session_state['perfil'] == "Sucursal":
        menu = st.sidebar.selectbox("Menú", [
            "Solicitar Recogida"
        ])
    return menu

# ------------ INICIO DE LA APLICACIÓN ------------

# Verificar si el usuario está logueado
if 'logged_in' not in st.session_state:
    mostrar_login()
else:
    # Cabecera
    col1, col2 = st.columns([1, 4])
    with col1:
        st.image("https://github.com/Melisa2303/Lavanderias-Americanas/blob/main/LOGO.PNG?raw=true", width=100)
    with col2:
        st.title("Lavanderías Americanas")
    
    menu = mostrar_menu()

    # -------------------- SECCIÓN INGRESAR BOLETA --------------------
    if menu == "Ingresar Boleta":
        st.header("📄 Ingresar Boleta")
        
        numero_boleta = st.text_input("Número de Boleta")
        nombre_cliente = st.text_input("Nombre del Cliente")
        dni_cliente = st.text_input("DNI del Cliente")

        col1, col2 = st.columns(2)
        with col1:
            monto_pagar = st.number_input("Monto a Pagar", min_value=0.0, format="%.2f")
        with col2:
            medio_pago = st.selectbox("Medio de Pago", ["Efectivo", "Yape", "Plin", "Transferencia"])
        
        fecha_registro = st.date_input("Fecha de Registro")
        tipo_entrega = st.radio("Tipo de Entrega", ("Sucursal", "Delivery"))

        if tipo_entrega == "Sucursal":
            conn = conectar_db()
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute('SELECT id, nombre FROM sucursales')
                    sucursales = cursor.fetchall()
                    if sucursales:
                        sucursal_id = st.selectbox("Seleccione sucursal", 
                                                 [s[0] for s in sucursales], 
                                                 format_func=lambda x: [s[1] for s in sucursales if s[0] == x][0])
                    else:
                        st.warning("No hay sucursales registradas.")
                        sucursal_id = None
                finally:
                    cursor.close()
                    conn.close()
        else:
            sucursal_id = None

        if st.button("Guardar Boleta"):
            # Validaciones
            errores = []
            if not dni_cliente or not dni_cliente.isdigit() or len(dni_cliente) != 8:
                errores.append("DNI debe tener 8 dígitos")
            if not numero_boleta or not numero_boleta.isdigit():
                errores.append("Número de boleta inválido")
            
            if not errores:
                conn = conectar_db()
                if conn:
                    try:
                        cursor = conn.cursor()
                        cursor.execute('''
                            INSERT INTO boletas (
                                numero_boleta, nombre_cliente, dni_cliente, 
                                monto_pagar, medio_pago, tipo_entrega, 
                                sucursal_id, fecha_registro
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ''', (
                            numero_boleta, nombre_cliente, dni_cliente,
                            monto_pagar, medio_pago, tipo_entrega,
                            sucursal_id, fecha_registro
                        ))
                        conn.commit()
                        st.success("✅ Boleta guardada")
                    except Exception as e:
                        st.error(f"Error: {e}")
                    finally:
                        cursor.close()
                        conn.close()
            else:
                for error in errores:
                    st.error(error)

    # -------------------- SECCIÓN INGRESAR SUCURSAL --------------------
    elif menu == "Ingresar Sucursal":
        st.header("🏪 Ingresar Sucursal")
        
        nombre = st.text_input("Nombre de la Sucursal")
        direccion = st.text_input("Dirección Completa")

        if st.button("Guardar Sucursal"):
            try:
                lat, lon = obtener_coordenadas(direccion)
                if lat and lon:
                    conn = conectar_db()
                    if conn:
                        try:
                            cursor = conn.cursor()
                            cursor.execute('''
                                INSERT INTO sucursales (nombre, direccion, latitud, longitud)
                                VALUES (%s, %s, %s, %s)
                            ''', (nombre, direccion, lat, lon))
                            conn.commit()
                            st.success("✅ Sucursal registrada")
                        finally:
                            cursor.close()
                            conn.close()
                else:
                    st.error("No se pudo geocodificar la dirección")
            except Exception as e:
                st.error(f"Error: {e}")

    # -------------------- SECCIÓN SOLICITAR RECOGIDA --------------------
    elif menu == "Solicitar Recogida":
        st.header("🚚 Solicitar Recogida")
        
        tipo_recogida = st.radio("Tipo de Recogida", ["Sucursal", "Cliente Delivery"])

        if tipo_recogida == "Sucursal":
            conn = conectar_db()
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute('SELECT id, nombre FROM sucursales')
                    sucursales = cursor.fetchall()
                    
                    if sucursales:
                        sucursal_id = st.selectbox("Seleccione sucursal", 
                                                 [s[0] for s in sucursales],
                                                 format_func=lambda x: [s[1] for s in sucursales if s[0] == x][0])
                        fecha = st.date_input("Fecha de Recogida")
                        
                        if st.button("Programar Recogida"):
                            if fecha < datetime.date.today():
                                st.error("La fecha no puede ser pasada")
                            else:
                                try:
                                    # Registrar recogida
                                    cursor.execute('''
                                        INSERT INTO recogidas (sucursal_id, fecha)
                                        VALUES (%s, %s)
                                    ''', (sucursal_id, fecha))
                                    
                                    # Programar entrega (3 días después)
                                    fecha_entrega = fecha + timedelta(days=3)
                                    cursor.execute('''
                                        INSERT INTO entregas (tipo, sucursal_id, fecha_entrega)
                                        VALUES (%s, %s, %s)
                                    ''', ("sucursal", sucursal_id, fecha_entrega))
                                    
                                    conn.commit()
                                    st.success(f"✅ Recogida programada para el {fecha}")
                                except Exception as e:
                                    conn.rollback()
                                    st.error(f"Error: {e}")
                    else:
                        st.warning("No hay sucursales registradas")
                finally:
                    cursor.close()
                    conn.close()

        else:  # Cliente Delivery
            nombre = st.text_input("Nombre del Cliente")
            telefono = st.text_input("Teléfono")
            direccion = st.text_input("Dirección")
            fecha = st.date_input("Fecha de Recogida")
            
            if st.button("Registrar Recogida"):
                errores = []
                if not nombre:
                    errores.append("Nombre es obligatorio")
                if not telefono.isdigit() or len(telefono) != 9:
                    errores.append("Teléfono debe tener 9 dígitos")
                if fecha < datetime.date.today():
                    errores.append("Fecha no puede ser pasada")
                
                if not errores:
                    conn = conectar_db()
                    if conn:
                        try:
                            cursor = conn.cursor()
                            # Registrar cliente
                            cursor.execute('''
                                INSERT INTO clientes_delivery (nombre, telefono, direccion, fecha_recogida)
                                VALUES (%s, %s, %s, %s)
                                RETURNING id
                            ''', (nombre, telefono, direccion, fecha))
                            cliente_id = cursor.fetchone()[0]
                            
                            # Programar entrega (3 días después)
                            fecha_entrega = fecha + timedelta(days=3)
                            cursor.execute('''
                                INSERT INTO entregas (tipo, cliente_id, fecha_entrega)
                                VALUES (%s, %s, %s)
                            ''', ("delivery", cliente_id, fecha_entrega))
                            
                            conn.commit()
                            st.success(f"✅ Recogida programada para el {fecha}")
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Error: {e}")
                        finally:
                            cursor.close()
                            conn.close()
                else:
                    for error in errores:
                        st.error(error)

    # -------------------- SECCIÓN DATOS DE RECOJOS --------------------
    elif menu == "Datos de Recojos":
        st.header("📋 Datos de Recojos")
        
        fecha = st.date_input("Filtrar por fecha")
        
        conn = conectar_db()
        if conn:
            try:
                cursor = conn.cursor()
                
                # Recojos en sucursales
                st.subheader("Recojos en Sucursales")
                cursor.execute('''
                    SELECT s.nombre, s.direccion, r.fecha 
                    FROM recogidas r JOIN sucursales s ON r.sucursal_id = s.id
                    WHERE r.fecha = %s
                ''', (fecha,))
                df_sucursal = pd.DataFrame(cursor.fetchall(), columns=["Sucursal", "Dirección", "Fecha"])
                st.dataframe(df_sucursal)
                
                # Recojos a domicilio
                st.subheader("Recojos a Domicilio")
                cursor.execute('''
                    SELECT nombre, telefono, direccion, fecha_recogida
                    FROM clientes_delivery
                    WHERE fecha_recogida = %s
                ''', (fecha,))
                df_domicilio = pd.DataFrame(cursor.fetchall(), columns=["Cliente", "Teléfono", "Dirección", "Fecha"])
                st.dataframe(df_domicilio)
                
            finally:
                cursor.close()
                conn.close()

    # -------------------- SECCIÓN RUTA OPTIMIZADA --------------------
    elif menu == "Ver Ruta Optimizada":
        st.header("🗺️ Ruta Optimizada")
        
        fecha = st.date_input("Seleccionar fecha para ruta")
        
        if st.button("Generar Ruta"):
            conn = conectar_db()
            if conn:
                try:
                    cursor = conn.cursor()
                    
                    # Obtener ubicaciones (sucursales + clientes)
                    cursor.execute('''
                        SELECT 
                            CASE 
                                WHEN e.tipo = 'sucursal' THEN s.nombre
                                ELSE c.nombre
                            END AS nombre,
                            CASE 
                                WHEN e.tipo = 'sucursal' THEN s.latitud
                                ELSE NULL  # Suponiendo que clientes no tienen lat/lon
                            END AS latitud,
                            CASE 
                                WHEN e.tipo = 'sucursal' THEN s.longitud
                                ELSE NULL
                            END AS longitud,
                            CASE 
                                WHEN e.tipo = 'sucursal' THEN s.direccion
                                ELSE c.direccion
                            END AS direccion
                        FROM entregas e
                        LEFT JOIN sucursales s ON e.sucursal_id = s.id
                        LEFT JOIN clientes_delivery c ON e.cliente_id = c.id
                        WHERE e.fecha_entrega = %s
                    ''', (fecha,))
                    
                    ubicaciones = [
                        (nombre, lat, lon, dir) 
                        for nombre, lat, lon, dir in cursor.fetchall() 
                        if lat is not None and lon is not None
                    ]
                    
                    if ubicaciones:
                        # Optimizar ruta
                        matriz = calcular_matriz_distancias(ubicaciones)
                        ruta_optimizada = optimizar_ruta(matriz)
                        
                        if ruta_optimizada:
                            # Mostrar ruta ordenada
                            st.subheader("Orden de Visita")
                            for i, idx in enumerate(ruta_optimizada):
                                st.write(f"{i+1}. {ubicaciones[idx][0]} - {ubicaciones[idx][3]}")
                            
                            # Mostrar mapa
                            coordenadas = [[ubicaciones[idx][2], ubicaciones[idx][1]] for idx in ruta_optimizada]
                            if ruta_geojson := obtener_ruta_real(coordenadas, ors_api_key):
                                mapa = folium.Map(location=[-12.0464, -77.0428], zoom_start=12)
                                folium.GeoJson(ruta_geojson).add_to(mapa)
                                for idx in ruta_optimizada:
                                    folium.Marker(
                                        [ubicaciones[idx][1], ubicaciones[idx][2]],
                                        popup=ubicaciones[idx][0]
                                    ).add_to(mapa)
                                folium_static(mapa)
                    else:
                        st.warning("No hay entregas programadas para esta fecha")
                        
                finally:
                    cursor.close()
                    conn.close()

    # -------------------- BOTÓN CERRAR SESIÓN --------------------
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.clear()
        st.experimental_rerun()
        
