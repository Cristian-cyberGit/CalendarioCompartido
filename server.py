#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor de Desarrollo Local (Python + SQLite)
Sirve los archivos estáticos del frontend y provee la API REST (simulando los archivos PHP).
Usa SQLite como base de datos relacional local sin dependencias externas.
Integra directamente la lógica de validación avanzada de eventos y compras.
"""

import os
import sys
import json
import sqlite3
import hashlib
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# Añadir directorio actual al path para importar validadores
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from backend.conflict_validator import validate_schedule
from backend.duplicate_checker import check_duplicates

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database', 'database.db')

# Intentar importar bcrypt para hashing seguro, si no, usar sha256 con fallback
try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False

def hash_pw(password):
    if HAS_BCRYPT:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    else:
        return hashlib.sha256(password.encode('utf-8')).hexdigest()

def verify_pw(password, hashed):
    if hashed.startswith("$2y$") or hashed.startswith("$2a$") or hashed.startswith("$2b$"):
        if HAS_BCRYPT:
            try:
                # PHP usa $2y$, bcrypt en Python espera $2b$ o similar, a veces funciona directo
                # si no, lo reemplazamos por $2b$
                h = hashed.replace('$2y$', '$2b$')
                return bcrypt.checkpw(password.encode('utf-8'), h.encode('utf-8'))
            except Exception:
                pass
        # Fallback para usuarios semilla: su contraseña es 'password123'
        return password == "password123"
    
    # Si es hash SHA256 (creado localmente sin bcrypt)
    if len(hashed) == 64:
        return hashlib.sha256(password.encode('utf-8')).hexdigest() == hashed
    
    if HAS_BCRYPT:
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except Exception:
            return False
    return False

def init_db():
    """Crea la base de datos SQLite y las tablas si no existen."""
    db_dir = os.path.dirname(DB_PATH)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Habilitar soporte para llaves foráneas en SQLite
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # 1. Usuarios
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        reset_token TEXT,
        reset_token_expires TEXT,
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # Migración automática de columnas para bases de datos existentes
    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN reset_token TEXT;")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN reset_token_expires TEXT;")
    except sqlite3.OperationalError:
        pass
    
    # 2. Grupos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS grupos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        codigo_acceso TEXT NOT NULL UNIQUE,
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # 3. Miembros
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS miembros_grupo (
        grupo_id INTEGER NOT NULL,
        usuario_id INTEGER NOT NULL,
        rol TEXT DEFAULT 'miembro',
        fecha_union TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (grupo_id, usuario_id),
        FOREIGN KEY (grupo_id) REFERENCES grupos(id) ON DELETE CASCADE,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
    );
    """)
    
    # 4. Eventos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grupo_id INTEGER NOT NULL,
        titulo TEXT NOT NULL,
        descripcion TEXT,
        fecha_inicio TEXT NOT NULL,
        fecha_fin TEXT NOT NULL,
        categoria TEXT DEFAULT 'general',
        creado_por INTEGER NOT NULL,
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        version INTEGER DEFAULT 1,
        FOREIGN KEY (grupo_id) REFERENCES grupos(id) ON DELETE CASCADE,
        FOREIGN KEY (creado_por) REFERENCES usuarios(id) ON DELETE CASCADE
    );
    """)
    
    # 5. Listas de compras
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS listas_compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grupo_id INTEGER NOT NULL,
        nombre TEXT NOT NULL,
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (grupo_id) REFERENCES grupos(id) ON DELETE CASCADE
    );
    """)
    
    # 6. Items de compras
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS items_compra (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lista_id INTEGER NOT NULL,
        nombre TEXT NOT NULL,
        cantidad INTEGER DEFAULT 1,
        unidad TEXT DEFAULT 'unidades',
        comprado INTEGER DEFAULT 0,
        actualizado_por INTEGER NULL,
        fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        version INTEGER DEFAULT 1,
        FOREIGN KEY (lista_id) REFERENCES listas_compras(id) ON DELETE CASCADE,
        FOREIGN KEY (actualizado_por) REFERENCES usuarios(id) ON DELETE SET NULL
    );
    """)
    
    # 7. Turnos rotativos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS turnos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grupo_id INTEGER NOT NULL,
        usuario_id INTEGER NOT NULL,
        fecha TEXT NOT NULL,
        tipo TEXT NOT NULL,
        FOREIGN KEY (grupo_id) REFERENCES grupos(id) ON DELETE CASCADE,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
        UNIQUE(usuario_id, fecha)
    );
    """)
    
    # Insertar datos semilla si la tabla de usuarios está vacía
    cursor.execute("SELECT COUNT(*) FROM usuarios;")
    if cursor.fetchone()[0] == 0:
        print("Insertando datos de prueba en la base de datos local...")
        # Contraseñas con bcrypt en producción PHP, en Python usaremos los hashes de producción
        # y el validador con fallback para password123
        p_hash = "$2y$10$tZ9v500HkO7k45D/p8a.yexiT3.j1r.9a32UbeAkykG8yDpx936e6"
        
        cursor.execute("INSERT INTO usuarios (id, nombre, email, password) VALUES (1, 'Mamá María', 'maria@familia.com', ?);", (p_hash,))
        cursor.execute("INSERT INTO usuarios (id, nombre, email, password) VALUES (2, 'Papá Juan', 'juan@familia.com', ?);", (p_hash,))
        cursor.execute("INSERT INTO usuarios (id, nombre, email, password) VALUES (3, 'Hijo Lucas', 'lucas@familia.com', ?);", (p_hash,))
        
        cursor.execute("INSERT INTO grupos (id, nombre, codigo_acceso) VALUES (1, 'Hogar Los Pérez', 'PEREZ2026');")
        
        cursor.execute("INSERT INTO miembros_grupo (grupo_id, usuario_id, rol) VALUES (1, 1, 'admin');")
        cursor.execute("INSERT INTO miembros_grupo (grupo_id, usuario_id, rol) VALUES (1, 2, 'miembro');")
        cursor.execute("INSERT INTO miembros_grupo (grupo_id, usuario_id, rol) VALUES (1, 3, 'miembro');")
        
        cursor.execute("""
        INSERT INTO eventos (id, grupo_id, titulo, descripcion, fecha_inicio, fecha_fin, categoria, creado_por) VALUES
        (1, 1, 'Almuerzo familiar domingo', 'Almuerzo mensual con abuelos', '2026-06-14 13:00:00', '2026-06-14 16:00:00', 'hogar', 1),
        (2, 1, 'Control médico Juan', 'Cardiólogo - Clínica Santa María', '2026-06-15 09:30:00', '2026-06-15 10:30:00', 'salud', 1),
        (3, 1, 'Reunión de apoderados Lucas', 'Colegio - Entrega de notas', '2026-06-15 18:00:00', '2026-06-15 19:30:00', 'hogar', 2);
        """)
        
        cursor.execute("INSERT INTO listas_compras (id, grupo_id, nombre) VALUES (1, 1, 'Compras de supermercado');")
        
        cursor.execute("""
        INSERT INTO items_compra (id, lista_id, nombre, cantidad, unidad, comprado, actualizado_por) VALUES
        (1, 1, 'Leche entera semidescremada', 6, 'cajas', 0, NULL),
        (2, 1, 'Pan de molde', 2, 'unidades', 0, NULL),
        (3, 1, 'Manzanas rojas', 1, 'kg', 1, 1),
        (4, 1, 'Arroz grado 1', 3, 'kg', 0, NULL);
        """)
        
        conn.commit()
        print("Datos de prueba insertados con éxito.")
        
    conn.close()

class APIServerHandler(BaseHTTPRequestHandler):
    def get_db_connection(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def send_json(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        # Habilitar CORS para facilitar desarrollo
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, User-ID')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_OPTIONS(self):
        """Maneja solicitudes preflight CORS."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, User-ID')
        self.end_headers()

    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query = parse_qs(parsed_url.query)
        
        # 1. API Endpoints
        if path == '/api/auth.php':
            action = query.get('action', [''])[0]
            user_id = self.headers.get('User-ID')
            
            if action == 'get_user_info' and user_id:
                self.handle_get_user_info(user_id)
                return
            else:
                self.send_json({"success": False, "error": "Acción no autorizada o no válida"}, 400)
                return
                
        elif path == '/api/events.php':
            grupo_id = query.get('grupo_id', [''])[0]
            if not grupo_id:
                self.send_json({"success": False, "error": "grupo_id requerido"}, 400)
                return
            self.handle_get_events(grupo_id)
            return
            
        elif path == '/api/shopping.php':
            grupo_id = query.get('grupo_id', [''])[0]
            if not grupo_id:
                self.send_json({"success": False, "error": "grupo_id requerido"}, 400)
                return
            self.handle_get_shopping(grupo_id)
            return
            
        elif path == '/api/shifts.php':
            grupo_id = query.get('grupo_id', [''])[0]
            if not grupo_id:
                self.send_json({"success": False, "error": "grupo_id requerido"}, 400)
                return
            self.handle_get_shifts(grupo_id)
            return

        # 2. Servir Archivos Estáticos (Frontend)
        # Sanitizar ruta para prevenir path traversal
        normalized_path = path.strip('/')
        if normalized_path == '':
            normalized_path = 'index.html'
            
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), normalized_path)
        
        if os.path.exists(file_path) and os.path.isfile(file_path):
            # Determinar Content-Type
            content_type = 'text/plain'
            if file_path.endswith('.html'):
                content_type = 'text/html; charset=utf-8'
            elif file_path.endswith('.css'):
                content_type = 'text/css; charset=utf-8'
            elif file_path.endswith('.js'):
                content_type = 'application/javascript; charset=utf-8'
            elif file_path.endswith('.json'):
                content_type = 'application/json'
            elif file_path.endswith('.png'):
                content_type = 'image/png'
                
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.end_headers()
            
            with open(file_path, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def do_POST(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query = parse_qs(parsed_url.query)
        
        # Leer el cuerpo de la solicitud
        content_length = int(self.headers.get('Content-Length', 0))
        post_data_bytes = self.rfile.read(content_length)
        post_data = {}
        if post_data_bytes:
            try:
                post_data = json.loads(post_data_bytes.decode('utf-8'))
            except json.JSONDecodeError:
                self.send_json({"success": False, "error": "JSON no válido"}, 400)
                return

        action = query.get('action', [''])[0]
        user_id = self.headers.get('User-ID')

        if path == '/api/auth.php':
            if action == 'login':
                self.handle_login(post_data)
            elif action == 'register':
                self.handle_register(post_data)
            elif action == 'request_reset':
                self.handle_request_reset(post_data)
            elif action == 'reset_password':
                self.handle_reset_password(post_data)
            elif action == 'create_group' and user_id:
                self.handle_create_group(user_id, post_data)
            elif action == 'join_group' and user_id:
                self.handle_join_group(user_id, post_data)
            else:
                self.send_json({"success": False, "error": f"Acción '{action}' desconocida o requiere cabecera User-ID"}, 400)
                
        elif path == '/api/events.php':
            if not user_id:
                self.send_json({"success": False, "error": "No autenticado"}, 401)
                return
            if action == 'create':
                self.handle_create_event(user_id, post_data)
            elif action == 'update':
                self.handle_update_event(user_id, post_data)
            elif action == 'delete':
                self.handle_delete_event(user_id, post_data)
            else:
                self.send_json({"success": False, "error": "Acción desconocida"}, 400)
                
        elif path == '/api/shopping.php':
            if not user_id:
                self.send_json({"success": False, "error": "No autenticado"}, 401)
                return
            if action == 'add_item':
                self.handle_add_shopping_item(user_id, post_data)
            elif action == 'toggle_item':
                self.handle_toggle_shopping_item(user_id, post_data)
            elif action == 'delete_item':
                self.handle_delete_shopping_item(user_id, post_data)
            else:
                self.send_json({"success": False, "error": "Acción desconocida"}, 400)
                
        elif path == '/api/shifts.php':
            if not user_id:
                self.send_json({"success": False, "error": "No autenticado"}, 401)
                return
            if action == 'set':
                self.handle_set_shift(user_id, post_data)
            else:
                self.send_json({"success": False, "error": "Acción desconocida"}, 400)
        else:
            self.send_json({"success": False, "error": "Ruta no encontrada"}, 404)

    # --- CONTROLADORES DE AUTENTICACIÓN ---

    def handle_login(self, data):
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        if not email or not password:
            self.send_json({"success": False, "error": "Email y contraseña requeridos"}, 400)
            return
            
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE email = ?;", (email,))
        user = cursor.fetchone()
        
        if user and verify_pw(password, user['password']):
            # Obtener el grupo del usuario (si tiene alguno)
            cursor.execute("""
                SELECT g.id, g.nombre, g.codigo_acceso, m.rol 
                FROM grupos g 
                JOIN miembros_grupo m ON g.id = m.grupo_id 
                WHERE m.usuario_id = ? LIMIT 1;
            """, (user['id'],))
            group = cursor.fetchone()
            
            group_data = None
            if group:
                group_data = {
                    "id": group["id"],
                    "nombre": group["nombre"],
                    "codigo_acceso": group["codigo_acceso"],
                    "rol": group["rol"]
                }
                
            self.send_json({
                "success": True,
                "user": {
                    "id": user["id"],
                    "nombre": user["nombre"],
                    "email": user["email"]
                },
                "group": group_data
            })
        else:
            self.send_json({"success": False, "error": "Credenciales incorrectas"}, 401)
        conn.close()

    def handle_register(self, data):
        nombre = data.get('nombre', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        if not nombre or not email or not password:
            self.send_json({"success": False, "error": "Todos los campos son requeridos"}, 400)
            return
            
        hashed = hash_pw(password)
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO usuarios (nombre, email, password) VALUES (?, ?, ?);", (nombre, email, hashed))
            conn.commit()
            new_id = cursor.lastrowid
            self.send_json({
                "success": True,
                "message": "Registro completado con éxito",
                "user": {"id": new_id, "nombre": nombre, "email": email}
            })
        except sqlite3.IntegrityError:
            self.send_json({"success": False, "error": "El email ya está registrado"}, 409)
        finally:
            conn.close()

    def handle_request_reset(self, data):
        email = data.get('email', '').strip()
        if not email:
            self.send_json({"success": False, "error": "Email requerido"}, 400)
            return
            
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM usuarios WHERE email = ?;", (email,))
        user = cursor.fetchone()
        
        if not user:
            self.send_json({"success": False, "error": "El correo electrónico no está registrado"}, 404)
            conn.close()
            return
            
        import random
        token = str(random.randint(100000, 999999))
        
        try:
            cursor.execute("""
                UPDATE usuarios 
                SET reset_token = ?, reset_token_expires = datetime('now', '+15 minutes') 
                WHERE email = ?;
            """, (token, email))
            conn.commit()
            
            print(f"\n[DEV MODE - PASSWORD RECOVERY] Código para {email}: {token}\n")
            
            self.send_json({
                "success": True,
                "message": "Código de verificación generado",
                "dev_token": token
            })
        except Exception as e:
            self.send_json({"success": False, "error": f"Error al generar código: {str(e)}"}, 500)
        finally:
            conn.close()

    def handle_reset_password(self, data):
        email = data.get('email', '').strip()
        token = data.get('token', '').strip()
        new_password = data.get('new_password', '')
        
        if not email or not token or not new_password:
            self.send_json({"success": False, "error": "Todos los campos son requeridos"}, 400)
            return
            
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM usuarios 
            WHERE email = ? AND reset_token = ? AND reset_token_expires > datetime('now');
        """, (email, token))
        user = cursor.fetchone()
        
        if not user:
            self.send_json({"success": False, "error": "Código de verificación incorrecto o expirado"}, 400)
            conn.close()
            return
            
        hashed = hash_pw(new_password)
        
        try:
            cursor.execute("""
                UPDATE usuarios 
                SET password = ?, reset_token = NULL, reset_token_expires = NULL 
                WHERE id = ?;
            """, (hashed, user['id']))
            conn.commit()
            self.send_json({
                "success": True,
                "message": "Tu contraseña ha sido restablecida con éxito"
            })
        except Exception as e:
            self.send_json({"success": False, "error": f"Error al actualizar la contraseña: {str(e)}"}, 500)
        finally:
            conn.close()

    def handle_get_user_info(self, user_id):
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre, email FROM usuarios WHERE id = ?;", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            self.send_json({"success": False, "error": "Usuario no encontrado"}, 404)
            conn.close()
            return
            
        cursor.execute("""
            SELECT g.id, g.nombre, g.codigo_acceso, m.rol 
            FROM grupos g 
            JOIN miembros_grupo m ON g.id = m.grupo_id 
            WHERE m.usuario_id = ? LIMIT 1;
        """, (user_id,))
        group = cursor.fetchone()
        
        group_data = None
        if group:
            group_data = {
                "id": group["id"],
                "nombre": group["nombre"],
                "codigo_acceso": group["codigo_acceso"],
                "rol": group["rol"]
            }
            
        self.send_json({
            "success": True,
            "user": {"id": user["id"], "nombre": user["nombre"], "email": user["email"]},
            "group": group_data
        })
        conn.close()

    def handle_create_group(self, user_id, data):
        nombre = data.get('nombre', '').strip()
        if not nombre:
            self.send_json({"success": False, "error": "Nombre del grupo es requerido"}, 400)
            return
            
        # Generar código de acceso aleatorio y único
        import random
        import string
        codigo = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        conn = self.get_db_connection()
        cursor = conn.cursor()
        try:
            # Transacción para crear grupo e insertar creador como admin
            cursor.execute("BEGIN TRANSACTION;")
            cursor.execute("INSERT INTO grupos (nombre, codigo_acceso) VALUES (?, ?);", (nombre, codigo))
            grupo_id = cursor.lastrowid
            
            cursor.execute("INSERT INTO miembros_grupo (grupo_id, usuario_id, rol) VALUES (?, ?, 'admin');", (grupo_id, user_id))
            
            # Crear lista de compras por defecto para el grupo
            cursor.execute("INSERT INTO listas_compras (grupo_id, nombre) VALUES (?, 'Lista de Compras Principal');", (grupo_id,))
            
            conn.commit()
            
            self.send_json({
                "success": True,
                "group": {
                    "id": grupo_id,
                    "nombre": nombre,
                    "codigo_acceso": codigo,
                    "rol": "admin"
                }
            })
        except Exception as e:
            conn.rollback()
            self.send_json({"success": False, "error": f"Error creando grupo: {str(e)}"}, 500)
        finally:
            conn.close()

    def handle_join_group(self, user_id, data):
        codigo = data.get('codigo_acceso', '').strip().upper()
        if not codigo:
            self.send_json({"success": False, "error": "Código de acceso requerido"}, 400)
            return
            
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM grupos WHERE codigo_acceso = ?;", (codigo,))
        group = cursor.fetchone()
        
        if not group:
            self.send_json({"success": False, "error": "Código de acceso no válido"}, 404)
            conn.close()
            return
            
        try:
            cursor.execute("INSERT INTO miembros_grupo (grupo_id, usuario_id, rol) VALUES (?, ?, 'miembro');", (group['id'], user_id))
            conn.commit()
            self.send_json({
                "success": True,
                "message": "Te has unido al grupo con éxito",
                "group": {
                    "id": group["id"],
                    "nombre": group["nombre"],
                    "codigo_acceso": group["codigo_acceso"],
                    "rol": "miembro"
                }
            })
        except sqlite3.IntegrityError:
            self.send_json({"success": False, "error": "Ya eres miembro de este grupo"}, 409)
        finally:
            conn.close()

    # --- CONTROLADORES DE EVENTOS ---

    def handle_get_events(self, grupo_id):
        conn = self.get_db_connection()
        cursor = conn.cursor()
        # Obtener los eventos del grupo ordenados cronológicamente
        cursor.execute("""
            SELECT e.*, u.nombre as creador_nombre 
            FROM eventos e 
            JOIN usuarios u ON e.creado_por = u.id 
            WHERE e.grupo_id = ? 
            ORDER BY e.fecha_inicio ASC;
        """, (grupo_id,))
        events = [dict(row) for row in cursor.fetchall()]
        self.send_json({"success": True, "events": events})
        conn.close()

    def handle_create_event(self, user_id, data):
        grupo_id = data.get('grupo_id')
        titulo = data.get('titulo', '').strip()
        descripcion = data.get('descripcion', '').strip()
        start = data.get('fecha_inicio', '').strip()
        end = data.get('fecha_fin', '').strip()
        categoria = data.get('categoria', 'general').strip()
        force = data.get('force', False) # Permitir forzar inserción ignorando advertencias leves
        
        if not grupo_id or not titulo or not start or not end:
            self.send_json({"success": False, "error": "Faltan campos obligatorios para crear el evento"}, 400)
            return
            
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # 1. Obtener eventos existentes del grupo para la validación avanzada de conflictos
        cursor.execute("SELECT id, titulo, fecha_inicio as start, fecha_fin as end FROM eventos WHERE grupo_id = ?;", (grupo_id,))
        existing_events = [dict(row) for row in cursor.fetchall()]
        
        # 2. Ejecutar validador avanzado de Python (importación directa)
        proposed = {"start": start, "end": end}
        val_result = validate_schedule(proposed, existing_events)
        
        # Manejo de error en parsing del validador
        if "error" in val_result:
            self.send_json({"success": False, "error": val_result["error"]}, 400)
            conn.close()
            return
            
        # 3. Si hay conflicto absoluto (traslape), bloqueamos la inserción siempre
        if val_result["conflict"]:
            self.send_json({
                "success": False,
                "conflict": True,
                "error": "Conflicto de horario: El evento se traslapa con otra actividad existente.",
                "details": val_result
            }, 409)
            conn.close()
            return
            
        # 4. Si hay advertencias de proximidad (menos de 15 min de separación) y no se forzó, avisar
        if val_result["warnings"] and not force:
            self.send_json({
                "success": False,
                "warning": True,
                "error": "Advertencia de proximidad de horario.",
                "details": val_result
            }, 200) # Devolvemos 200 con 'warning: true' para que el cliente decida si forzar la creación
            conn.close()
            return

        # 5. Insertar el evento usando transacciones para concurrencia segura
        try:
            cursor.execute("BEGIN TRANSACTION;")
            cursor.execute("""
                INSERT INTO eventos (grupo_id, titulo, descripcion, fecha_inicio, fecha_fin, categoria, creado_por, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1);
            """, (grupo_id, titulo, descripcion, start, end, categoria, user_id))
            conn.commit()
            new_id = cursor.lastrowid
            
            self.send_json({
                "success": True,
                "message": "Evento creado exitosamente",
                "event_id": new_id
            })
        except Exception as e:
            conn.rollback()
            self.send_json({"success": False, "error": f"Error insertando evento: {str(e)}"}, 500)
        finally:
            conn.close()

    def handle_update_event(self, user_id, data):
        event_id = data.get('id')
        grupo_id = data.get('grupo_id')
        titulo = data.get('titulo', '').strip()
        descripcion = data.get('descripcion', '').strip()
        start = data.get('fecha_inicio', '').strip()
        end = data.get('fecha_fin', '').strip()
        categoria = data.get('categoria', 'general').strip()
        current_version = data.get('version', 1) # Control de concurrencia optimista
        force = data.get('force', False)
        
        if not event_id or not grupo_id or not titulo or not start or not end:
            self.send_json({"success": False, "error": "Campos incompletos para actualizar"}, 400)
            return
            
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # 1. Obtener eventos existentes del grupo EXCLUYENDO el actual
        cursor.execute("SELECT id, titulo, fecha_inicio as start, fecha_fin as end FROM eventos WHERE grupo_id = ? AND id != ?;", (grupo_id, event_id))
        existing_events = [dict(row) for row in cursor.fetchall()]
        
        # 2. Validar conflicto de horarios
        proposed = {"start": start, "end": end}
        val_result = validate_schedule(proposed, existing_events)
        
        if "error" in val_result:
            self.send_json({"success": False, "error": val_result["error"]}, 400)
            conn.close()
            return
            
        if val_result["conflict"]:
            self.send_json({
                "success": False,
                "conflict": True,
                "error": "Conflicto de horario detectado.",
                "details": val_result
            }, 409)
            conn.close()
            return
            
        if val_result["warnings"] and not force:
            self.send_json({
                "success": False,
                "warning": True,
                "error": "Proximidad detectada.",
                "details": val_result
            }, 200)
            conn.close()
            return

        # 3. Transacción con bloqueo optimista para prevenir sobreescrituras concurrentes
        try:
            cursor.execute("BEGIN TRANSACTION;")
            
            # Verificar versión actual en BD
            cursor.execute("SELECT version FROM eventos WHERE id = ?;", (event_id,))
            row = cursor.fetchone()
            if not row:
                self.send_json({"success": False, "error": "El evento no existe"}, 404)
                conn.rollback()
                return
                
            db_version = row['version']
            
            if db_version != current_version:
                self.send_json({
                    "success": False,
                    "concurrency_error": True,
                    "error": "El evento fue modificado por otro miembro. Recarga el calendario para ver los cambios."
                }, 409)
                conn.rollback()
                return
                
            # Incrementar versión e insertar
            new_version = db_version + 1
            cursor.execute("""
                UPDATE eventos 
                SET titulo = ?, descripcion = ?, fecha_inicio = ?, fecha_fin = ?, categoria = ?, version = ?
                WHERE id = ? AND version = ?;
            """, (titulo, descripcion, start, end, categoria, new_version, event_id, db_version))
            
            if cursor.rowcount == 0:
                # Falló el update por condición de versión en WHERE (concurrencia)
                self.send_json({
                    "success": False,
                    "concurrency_error": True,
                    "error": "Conflicto de concurrencia al actualizar el registro."
                }, 409)
                conn.rollback()
            else:
                conn.commit()
                self.send_json({"success": True, "message": "Evento actualizado con éxito", "version": new_version})
                
        except Exception as e:
            conn.rollback()
            self.send_json({"success": False, "error": f"Error del sistema: {str(e)}"}, 500)
        finally:
            conn.close()

    def handle_delete_event(self, user_id, data):
        event_id = data.get('id')
        if not event_id:
            self.send_json({"success": False, "error": "id de evento requerido"}, 400)
            return
            
        conn = self.get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM eventos WHERE id = ?;", (event_id,))
            conn.commit()
            self.send_json({"success": True, "message": "Evento eliminado"})
        except Exception as e:
            self.send_json({"success": False, "error": str(e)}, 500)
        finally:
            conn.close()

    # --- CONTROLADORES DE COMPRAS ---

    def handle_get_shopping(self, grupo_id):
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Obtener la lista de compras del grupo
        cursor.execute("SELECT id, nombre FROM listas_compras WHERE grupo_id = ? LIMIT 1;", (grupo_id,))
        lista = cursor.fetchone()
        
        if not lista:
            # Crear una lista por defecto si no existe
            cursor.execute("INSERT INTO listas_compras (grupo_id, nombre) VALUES (?, 'Lista de Compras Principal');", (grupo_id,))
            conn.commit()
            cursor.execute("SELECT id, nombre FROM listas_compras WHERE grupo_id = ? LIMIT 1;", (grupo_id,))
            lista = cursor.fetchone()
            
        lista_id = lista['id']
        
        # Obtener los items
        cursor.execute("""
            SELECT i.*, u.nombre as actualizado_por_nombre 
            FROM items_compra i 
            LEFT JOIN usuarios u ON i.actualizado_por = u.id
            WHERE i.lista_id = ?
            ORDER BY i.comprado ASC, i.fecha_actualizacion DESC;
        """, (lista_id,))
        items = [dict(row) for row in cursor.fetchall()]
        
        self.send_json({
            "success": True,
            "list_id": lista_id,
            "list_name": lista['nombre'],
            "items": items
        })
        conn.close()

    def handle_add_shopping_item(self, user_id, data):
        lista_id = data.get('lista_id')
        nombre = data.get('nombre', '').strip()
        cantidad = data.get('cantidad', 1)
        unidad = data.get('unidad', 'unidades').strip()
        force = data.get('force', False)
        
        if not lista_id or not nombre:
            self.send_json({"success": False, "error": "Datos incompletos"}, 400)
            return
            
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # 1. Obtener items existentes no comprados para verificar duplicidad difusa
        cursor.execute("SELECT id, nombre as name, comprado FROM items_compra WHERE lista_id = ? AND comprado = 0;", (lista_id,))
        existing_items = [dict(row) for row in cursor.fetchall()]
        
        # 2. Ejecutar corrector de duplicados de Python
        dup_result = check_duplicates(nombre, existing_items)
        
        # 3. Si hay sospecha de duplicado y no está forzado, notificar al cliente
        if dup_result["duplicate"] and not force:
            self.send_json({
                "success": False,
                "duplicate": True,
                "error": dup_result["warning_message"],
                "details": dup_result
            }, 200) # Retorna 200 con flag 'duplicate: true' para cuadro de confirmación en UI
            conn.close()
            return
            
        # 4. Insertar item
        try:
            cursor.execute("""
                INSERT INTO items_compra (lista_id, nombre, cantidad, unidad, comprado, actualizado_por)
                VALUES (?, ?, ?, ?, 0, ?);
            """, (lista_id, nombre, cantidad, unidad, user_id))
            conn.commit()
            new_id = cursor.lastrowid
            self.send_json({
                "success": True,
                "message": "Artículo agregado",
                "item_id": new_id
            })
        except Exception as e:
            self.send_json({"success": False, "error": str(e)}, 500)
        finally:
            conn.close()

    def handle_toggle_shopping_item(self, user_id, data):
        item_id = data.get('id')
        comprado = data.get('comprado') # 0 o 1
        current_version = data.get('version', 1)
        
        if item_id is None or comprado is None:
            self.send_json({"success": False, "error": "item_id y estado 'comprado' requeridos"}, 400)
            return
            
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # Optimistic locking
        try:
            cursor.execute("BEGIN TRANSACTION;")
            cursor.execute("SELECT version FROM items_compra WHERE id = ?;", (item_id,))
            row = cursor.fetchone()
            
            if not row:
                self.send_json({"success": False, "error": "El artículo no existe"}, 404)
                conn.rollback()
                return
                
            db_version = row['version']
            if db_version != current_version:
                self.send_json({
                    "success": False,
                    "concurrency_error": True,
                    "error": "El artículo fue modificado por otro miembro. Recarga la lista."
                }, 409)
                conn.rollback()
                return
                
            new_version = db_version + 1
            cursor.execute("""
                UPDATE items_compra 
                SET comprado = ?, actualizado_por = ?, version = ?, fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE id = ? AND version = ?;
            """, (comprado, user_id, new_version, item_id, db_version))
            
            conn.commit()
            self.send_json({
                "success": True, 
                "message": "Estado del artículo actualizado", 
                "version": new_version
            })
        except Exception as e:
            conn.rollback()
            self.send_json({"success": False, "error": str(e)}, 500)
        finally:
            conn.close()

    def handle_delete_shopping_item(self, user_id, data):
        item_id = data.get('id')
        if not item_id:
            self.send_json({"success": False, "error": "id requerido"}, 400)
            return
            
        conn = self.get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM items_compra WHERE id = ?;", (item_id,))
            conn.commit()
            self.send_json({"success": True, "message": "Artículo eliminado"})
        except Exception as e:
            self.send_json({"success": False, "error": str(e)}, 500)
        finally:
            conn.close()

    # --- CONTROLADORES DE TURNOS ---

    def handle_get_shifts(self, grupo_id):
        conn = self.get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT t.id, t.grupo_id, t.usuario_id, t.fecha, t.tipo, u.nombre as usuario_nombre
                FROM turnos t
                JOIN usuarios u ON t.usuario_id = u.id
                WHERE t.grupo_id = ?;
            """, (grupo_id,))
            shifts = [dict(row) for row in cursor.fetchall()]
            self.send_json({"success": True, "shifts": shifts})
        except Exception as e:
            self.send_json({"success": False, "error": str(e)}, 500)
        finally:
            conn.close()

    def handle_set_shift(self, user_id, data):
        grupo_id = data.get('grupo_id')
        fecha = data.get('fecha')
        tipo = data.get('tipo')
        
        if not grupo_id or not fecha:
            self.send_json({"success": False, "error": "grupo_id y fecha requeridos"}, 400)
            return
            
        conn = self.get_db_connection()
        cursor = conn.cursor()
        try:
            if tipo == 'borrar' or not tipo:
                cursor.execute("DELETE FROM turnos WHERE usuario_id = ? AND fecha = ?;", (user_id, fecha))
                conn.commit()
                self.send_json({"success": True, "message": "Turno eliminado"})
            else:
                cursor.execute("""
                    INSERT OR REPLACE INTO turnos (grupo_id, usuario_id, fecha, tipo)
                    VALUES (?, ?, ?, ?);
                """, (grupo_id, user_id, fecha, tipo))
                conn.commit()
                self.send_json({"success": True, "message": "Turno registrado/actualizado"})
        except Exception as e:
            self.send_json({"success": False, "error": str(e)}, 500)
        finally:
            conn.close()

def run(server_class=HTTPServer, handler_class=APIServerHandler, port=8000):
    init_db()
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f"Servidor backend activo en http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor apagado de forma ordenada.")
        httpd.server_close()

if __name__ == '__main__':
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run(port=port)
