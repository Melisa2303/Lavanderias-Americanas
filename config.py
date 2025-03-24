# config.py (seguro para subir a GitHub)
import os

def get_db_config():
    # Intenta obtener de variables de entorno (para producción)
    config = {
        'host': os.getenv('DB_HOST', 'db.tu_id.supabase.co'),  # Reemplaza con TU host real
        'database': 'postgres',
        'user': 'postgres',
        'password': os.getenv('DB_PASSWORD', ''),  # Se obtendrá del entorno
        'port': '5432',
        'sslmode': 'require'
    }
    return config
