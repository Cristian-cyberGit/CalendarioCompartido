# LogiFamily - Calendario Compartido y Lista de Compras Familiar

LogiFamily es una aplicación web interactiva (SPA) diseñada para coordinar las actividades, compras y turnos de trabajo en el hogar. Cuenta con validaciones avanzadas de concurrencia y detección de duplicados en tiempo real. 

Este proyecto implementa una **estrategia de doble backend** que facilita tanto el desarrollo local rápido como el despliegue final en producción académica:
1. **Desarrollo Local (Python + SQLite)**: Base de datos embebida y servidor integrado, listo para funcionar con un solo comando.
2. **Producción Académica (PHP + MySQL)**: API REST tradicional orientada a servidores Apache y bases de datos MySQL relacionales.

---

## 🚀 Características Principales

*   **Diseño Premium Adaptativo**: Interfaz moderna de una sola página (SPA) con transiciones suaves, variables HSL, temas Claro y Oscuro de alta visibilidad (manual/automático) y micro-animaciones.
*   **Visualización de Turnos (1/4 de Día)**: Grilla de calendario que resalta automáticamente domingos, festivos del año 2026 y turnos de trabajo coloreados en la parte superior de cada celda (ocupando 1/4 del día) con el nombre del familiar:
    *   🌅 **Mañana**: Amarillo (`#ffd43b`)
    *   🌇 **Tarde**: Naranjo (`#fd7e14`)
    *   🌃 **Noche**: Azul (`#1971c2`)
    *   🍃 **Libre**: Verde (`#2f9e44`)
*   **Validador de Horarios y Conflictos**: Algoritmo en Python (`backend/conflict_validator.py`) que detecta traslapes de eventos y sugiere horarios libres alternativos.
*   **Flujo de Recuperación de Contraseña**: Sistema automático que genera códigos de verificación temporales de 6 dígitos para restablecer claves seguras. En entorno de desarrollo local, el sistema muestra el código directamente en pantalla para simplificar los tests.
*   **Evitación de Artículos Duplicados**: Sistema difuso en Python (`backend/duplicate_checker.py`) que alerta al usuario cuando intenta ingresar compras similares para evitar redundancias (ej. "Leche" y "Leche descremada").
*   **Control de Concurrencia**: Bloqueo optimista y transacciones atómicas en base de datos para prevenir sobreescrituras en actualizaciones simultáneas de turnos, eventos y listas de compras.

---

## 🛠️ Estructura del Proyecto

*   [index.html](file:///c:/Users/ac42028/Documents/CalendarioCompartido/index.html) - Punto de entrada y estructura SPA.
*   [css/styles.css](file:///c:/Users/ac42028/Documents/CalendarioCompartido/css/styles.css) - Estilos responsivos, temas y animaciones.
*   [js/app.js](file:///c:/Users/ac42028/Documents/CalendarioCompartido/js/app.js) - Lógica de cliente, enrutamiento y llamadas al API.
*   [server.py](file:///c:/Users/ac42028/Documents/CalendarioCompartido/server.py) - Servidor de desarrollo integrado en Python y SQLite.
*   [api/](file:///c:/Users/ac42028/Documents/CalendarioCompartido/api/) - APIs en PHP (`auth.php`, `events.php`, `shifts.php`, `shopping.php`) y configuración (`config.php`).
*   [database/schema.sql](file:///c:/Users/ac42028/Documents/CalendarioCompartido/database/schema.sql) - Esquema e inserciones semilla para MySQL.
*   [backend/](file:///c:/Users/ac42028/Documents/CalendarioCompartido/backend/) - Scripts core de validación difusa y conflictos de horarios en Python.
*   [tests/stress_test.py](file:///c:/Users/ac42028/Documents/CalendarioCompartido/tests/stress_test.py) - Script multihilo para simular escrituras concurrentes.

---

## 💻 Inicio Rápido (Desarrollo Local - Python)

1. Abre tu terminal en la raíz del proyecto.
2. Inicia el servidor de desarrollo:
   ```bash
   python server.py
   ```
3. Ingresa desde tu navegador a:
   [http://localhost:8000](http://localhost:8000)
4. Credenciales de prueba (contraseña común: `password123`):
   *   **Mamá María**: `maria@familia.com`
   *   **Papá Juan**: `juan@familia.com`
   *   **Hijo Lucas**: `lucas@familia.com`

---

## 🗄️ Guía de Recuperación y Reseteo Manual (SQL)

Debido a que las contraseñas se almacenan mediante hashes de un solo sentido (Bcrypt), no se pueden recuperar en texto plano desde los archivos o bases de datos. Si olvidas tu clave, puedes:

### A. Utilizar el flujo en la UI
Presiona **¿Olvidaste tu contraseña?** en la pantalla de inicio de sesión, introduce tu correo y escribe el código de 6 dígitos que se mostrará en la interfaz en modo desarrollo (o en la consola del servidor Python).

### B. Cambiar la contraseña directamente en Base de Datos
Puedes ejecutar una consulta SQL para cambiar tu clave a la contraseña por defecto (`password123`):
*   **En SQLite (`database/database.db`) o MySQL (`calendario_familiar`)**:
    ```sql
    UPDATE usuarios 
    SET password = '$2y$10$tZ9v500HkO7k45D/p8a.yexiT3.j1r.9a32UbeAkykG8yDpx936e6', 
        reset_token = NULL, 
        reset_token_expires = NULL 
    WHERE email = 'tu_correo@ejemplo.com';
    ```

---

## 🌐 Despliegue Académico (Producción - PHP + MySQL)

1. Importa [database/schema.sql](file:///c:/Users/ac42028/Documents/CalendarioCompartido/database/schema.sql) en phpMyAdmin o tu servidor MySQL.
2. Modifica la conexión a base de datos en [api/config.php](file:///c:/Users/ac42028/Documents/CalendarioCompartido/api/config.php) si es necesario.
3. Copia todo el directorio a la carpeta pública de tu servidor Apache (ej. `htdocs`).
