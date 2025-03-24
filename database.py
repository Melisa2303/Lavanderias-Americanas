import sqlite3

# Conectar a la base de datos
conn = sqlite3.connect('lavanderia.db')
cursor = conn.cursor()

# Crear tabla de usuarios si no existe
cursor.execute('''
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT UNIQUE NOT NULL,
        contraseña TEXT NOT NULL,
        perfil TEXT NOT NULL
    )
''')
conn.commit()

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

# Insertar usuarios de prueba (solo la primera vez)
try:
    cursor.execute('''
        INSERT INTO usuarios (usuario, contraseña, perfil)
        VALUES (?, ?, ?)
    ''', ("admin", "admin123", "Administrador"))
    cursor.execute('''
        INSERT INTO usuarios (usuario, contraseña, perfil)
        VALUES (?, ?, ?)
    ''', ("chofer", "chofer123", "Chofer"))
    cursor.execute('''
        INSERT INTO usuarios (usuario, contraseña, perfil)
        VALUES (?, ?, ?)
    ''', ("sucursal", "sucursal123", "Sucursal"))
    conn.commit()
except sqlite3.IntegrityError:
    pass  # Los usuarios ya existen

# Guardar cambios y cerrar la conexión
conn.commit()
conn.close()
