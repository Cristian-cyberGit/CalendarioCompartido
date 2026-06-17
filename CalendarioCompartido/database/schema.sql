-- Esquema de Base de Datos para Calendario Compartido y Lista de Compras Familiar (MySQL)
-- Diseñado para persistencia relacional con restricciones e integridad referencial.

CREATE DATABASE IF NOT EXISTS calendario_familiar CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE calendario_familiar;

-- 1. Tabla de Usuarios
CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL, -- Almacenará hashes bcrypt
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 2. Tabla de Grupos (para compartir calendarios/listas entre familiares)
CREATE TABLE IF NOT EXISTS grupos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    codigo_acceso VARCHAR(20) NOT NULL UNIQUE, -- Código único para invitar a otros miembros
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 3. Tabla de Relación Miembros de Grupo (N a N)
CREATE TABLE IF NOT EXISTS miembros_grupo (
    grupo_id INT NOT NULL,
    usuario_id INT NOT NULL,
    rol VARCHAR(20) DEFAULT 'miembro', -- 'admin' o 'miembro'
    fecha_union TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (grupo_id, usuario_id),
    FOREIGN KEY (grupo_id) REFERENCES grupos(id) ON DELETE CASCADE,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 4. Tabla de Eventos del Calendario
CREATE TABLE IF NOT EXISTS eventos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    grupo_id INT NOT NULL,
    titulo VARCHAR(150) NOT NULL,
    descripcion TEXT,
    fecha_inicio DATETIME NOT NULL,
    fecha_fin DATETIME NOT NULL,
    categoria VARCHAR(50) DEFAULT 'general', -- 'hogar', 'salud', 'trabajo', 'ocio', etc.
    creado_por INT NOT NULL,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Control de concurrencia: versión para bloqueo optimista o timestamp de última actualización
    version INT DEFAULT 1,
    FOREIGN KEY (grupo_id) REFERENCES grupos(id) ON DELETE CASCADE,
    FOREIGN KEY (creado_por) REFERENCES usuarios(id) ON DELETE CASCADE,
    INDEX idx_rango_fechas (grupo_id, fecha_inicio, fecha_fin) -- Índice para optimizar consultas de traslape y filtros mensuales
) ENGINE=InnoDB;

-- 5. Tabla de Listas de Compras
CREATE TABLE IF NOT EXISTS listas_compras (
    id INT AUTO_INCREMENT PRIMARY KEY,
    grupo_id INT NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (grupo_id) REFERENCES grupos(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 6. Tabla de Artículos de la Lista de Compras (Items)
CREATE TABLE IF NOT EXISTS items_compra (
    id INT AUTO_INCREMENT PRIMARY KEY,
    lista_id INT NOT NULL,
    nombre VARCHAR(150) NOT NULL,
    cantidad INT DEFAULT 1,
    unidad VARCHAR(50) DEFAULT 'unidades', -- 'kg', 'litros', 'paquetes', etc.
    comprado TINYINT(1) DEFAULT 0, -- 0 = pendiente, 1 = comprado
    actualizado_por INT NULL,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    version INT DEFAULT 1, -- Control de concurrencia optimista
    FOREIGN KEY (lista_id) REFERENCES listas_compras(id) ON DELETE CASCADE,
    FOREIGN KEY (actualizado_por) REFERENCES usuarios(id) ON DELETE SET NULL,
    INDEX idx_lista_pendiente (lista_id, comprado) -- Optimizar carga de items pendientes
) ENGINE=InnoDB;

-- 7. Tabla de Turnos Rotativos
CREATE TABLE IF NOT EXISTS turnos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    grupo_id INT NOT NULL,
    usuario_id INT NOT NULL,
    fecha DATE NOT NULL,
    tipo VARCHAR(50) NOT NULL, -- 'manana', 'tarde', 'noche', 'libre'
    FOREIGN KEY (grupo_id) REFERENCES grupos(id) ON DELETE CASCADE,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    UNIQUE KEY uq_usuario_fecha (usuario_id, fecha) -- Evita duplicados del mismo usuario el mismo día
) ENGINE=InnoDB;


-- INSERCIÓN DE DATOS DE PRUEBA (SEMILLAS)
-- 1. Usuarios de prueba (contraseñas seguras pre-hasheadas con bcrypt correspondientes a 'password123')
-- Hash de 'password123' = $2y$10$tZ9v500HkO7k45D/p8a.yexiT3.j1r.9a32UbeAkykG8yDpx936e6
INSERT INTO usuarios (id, nombre, email, password) VALUES
(1, 'Mamá María', 'maria@familia.com', '$2y$10$tZ9v500HkO7k45D/p8a.yexiT3.j1r.9a32UbeAkykG8yDpx936e6'),
(2, 'Papá Juan', 'juan@familia.com', '$2y$10$tZ9v500HkO7k45D/p8a.yexiT3.j1r.9a32UbeAkykG8yDpx936e6'),
(3, 'Hijo Lucas', 'lucas@familia.com', '$2y$10$tZ9v500HkO7k45D/p8a.yexiT3.j1r.9a32UbeAkykG8yDpx936e6');

-- 2. Grupo familiar
INSERT INTO grupos (id, nombre, codigo_acceso) VALUES
(1, 'Hogar Los Pérez', 'PEREZ2026');

-- 3. Miembros del grupo
INSERT INTO miembros_grupo (grupo_id, usuario_id, rol) VALUES
(1, 1, 'admin'),
(1, 2, 'miembro'),
(1, 3, 'miembro');

-- 4. Eventos iniciales
INSERT INTO eventos (id, grupo_id, titulo, descripcion, fecha_inicio, fecha_fin, categoria, creado_por) VALUES
(1, 1, 'Almuerzo familiar domingo', 'Almuerzo mensual con abuelos', '2026-06-14 13:00:00', '2026-06-14 16:00:00', 'hogar', 1),
(2, 1, 'Control médico Juan', 'Cardiólogo - Clínica Santa María', '2026-06-15 09:30:00', '2026-06-15 10:30:00', 'salud', 1),
(3, 1, 'Reunión de apoderados Lucas', 'Colegio - Entrega de notas', '2026-06-15 18:00:00', '2026-06-15 19:30:00', 'hogar', 2);

-- 5. Lista de compras inicial
INSERT INTO listas_compras (id, grupo_id, nombre) VALUES
(1, 1, 'Compras de supermercado');

-- 6. Items de compras iniciales
INSERT INTO items_compra (id, lista_id, nombre, cantidad, unidad, comprado, actualizado_por) VALUES
(1, 1, 'Leche entera semidescremada', 6, 'cajas', 0, NULL),
(2, 1, 'Pan de molde', 2, 'unidades', 0, NULL),
(3, 1, 'Manzanas rojas', 1, 'kg', 1, 1),
(4, 1, 'Arroz grado 1', 3, 'kg', 0, NULL);

-- 7. Turnos rotativos iniciales
INSERT INTO turnos (grupo_id, usuario_id, fecha, tipo) VALUES
(1, 1, '2026-06-15', 'manana'),
(1, 2, '2026-06-15', 'tarde'),
(1, 1, '2026-06-16', 'libre'),
(1, 2, '2026-06-16', 'noche');
