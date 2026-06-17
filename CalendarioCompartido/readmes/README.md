# LogiFamily - Calendario Compartido y Lista de Compras Familiar

LogiFamily es una aplicación web interactiva diseñada para centralizar y coordinar la logística de un hogar (eventos, listas de compras y turnos de trabajo). Es un proyecto desarrollado bajo estándares profesionales e ingeniería de software para presentación de título universitario.

El sistema cuenta con una **estrategia de doble backend** que permite dos modos de operación:
1.  **Modo de Desarrollo Local (Python + SQLite)**: Ejecución instantánea con un solo comando sin requerir configuraciones de servidores web externos.
2.  **Modo de Producción Académico (PHP + MySQL)**: Estructura de código tradicional API REST para despliegue final sobre servidores web Apache y bases de datos MySQL.

---

## Características Principales

*   **Interfaz de Usuario Premium (SPA)**: Diseñada con HTML5 y CSS3 nativo mediante un diseño móvil-primero, variables HSL, temas Claro/Oscuro (automático y manual) y micro-animaciones en botones, tarjetas y vistas.
*   **Calendario Interactivo**: Visualización dinámica de actividades familiares por mes.
*   **Validador de Horarios Avanzado (Python)**: Analiza el ingreso de eventos mediante el script `backend/conflict_validator.py`. Evita traslapes de horario absolutos y genera alertas de proximidad (menos de 15 min de separación), sugiriendo automáticamente hasta dos espacios libres recomendados.
*   **Pintor Rápido de Turnos y Festivos**: Barra de herramientas para pintar rápidamente turnos de trabajo ('Mañana', 'Tarde', 'Noche', 'Libre', 'Borrar') haciendo clic en las celdas del calendario. Destaca automáticamente los días domingo y festivos del año 2026.
*   **Lista de Compras Coherente**: Administra artículos del supermercado.
*   **Corrector de Duplicados Difuso (Python)**: Utiliza `backend/duplicate_checker.py` para realizar comparación de texto no exacta (fuzzy string matching). Si intentas agregar un artículo similar a uno existente (ej. "Leche" y "Leche descremada"), alerta al usuario para evitar compras redundantes.
*   **Control de Concurrencia de Datos (Transacciones + Bloqueo Optimista)**: Protege la base de datos ante escrituras simultáneas en el calendario o lista de compras utilizando transacciones atómicas de base de datos (`BEGIN TRANSACTION`) y validación de versiones (`version`) para evitar sobreescrituras ciegas.

---

## Estructura del Proyecto

```text
├── api/
│   ├── config.php             # Configuración y conexión PDO a MySQL
│   ├── auth.php               # API PHP de autenticación y grupos
│   ├── events.php             # API PHP de eventos (llama a Python conflict_validator)
│   ├── shopping.php           # API PHP de compras (llama a Python duplicate_checker)
│   └── shifts.php             # API PHP de turnos rotativos
├── backend/
│   ├── conflict_validator.py  # Script Python de validación temporal y sugerencias
│   └── duplicate_checker.py   # Script Python de similitud difusa en compras
├── css/
│   └── styles.css             # Estilos responsivos con temas y animaciones
├── database/
│   └── schema.sql             # Estructura e inserciones semilla de base de datos MySQL
├── docs/
│   └── AVANCES.md             # Memoria técnica detallada para el informe de título
├── js/
│   └── app.js                 # Controlador Javascript del lado del cliente (Fetch/SPA)
├── readmes/
│   └── README.md              # Este archivo de instrucciones generales
├── tests/
│   └── stress_test.py         # Script Python de pruebas de estrés concurrentes (multihilo)
├── index.html                 # Punto de entrada de la aplicación SPA
└── server.py                  # Servidor local Python con base de datos SQLite
```

---

## Instrucciones de Inicio Rápido (Python + SQLite)

Para probar la aplicación inmediatamente en tu computadora local:

1.  Abre una terminal en el directorio raíz del proyecto:
    ```bash
    cd "c:\Users\ac42028\Documents\Calendario compartido"
    ```
2.  Inicia el servidor local de desarrollo:
    ```bash
    python server.py
    ```
3.  Ingresa desde tu navegador a la dirección:
    [http://localhost:8000](http://localhost:8000)
4.  Usa cualquiera de las siguientes credenciales semilla (contraseña común: `password123`):
    *   **Mamá María**: `maria@familia.com`
    *   **Papá Juan**: `juan@familia.com`
    *   **Hijo Lucas**: `lucas@familia.com`

---

## Pruebas de Estrés y Concurrencia

Para verificar la robustez de las transacciones y validaciones frente a accesos paralelos:

1.  Mantén el servidor corriendo en una terminal (`python server.py`).
2.  Abre otra terminal y ejecuta el script de estrés:
    ```bash
    python tests/stress_test.py
    ```
3.  El script enviará 15 peticiones concurrentes simultáneas al mismo horario del calendario. Observarás que el sistema procesa las solicitudes, aprueba exactamente **1 evento** y rechaza de forma segura los otros **14 intentos** de traslape, garantizando la consistencia absoluta en el base de datos.

---

## Despliegue en Producción (Apache/PHP + MySQL)

Para presentar la versión sobre servidores web tradicionales (ej. XAMPP):

1.  Importa el archivo [database/schema.sql](file:///c:/Users/ac42028/Documents/Calendario%20compartido/database/schema.sql) en tu servidor de base de datos MySQL.
2.  Configura las credenciales de base de datos de tu servidor en [api/config.php](file:///c:/Users/ac42028/Documents/Calendario%20compartido/api/config.php).
3.  Copia todo el directorio del proyecto dentro de la carpeta pública de tu servidor web (ej. `C:\xampp\htdocs\calendario_compartido`).
4.  Accede a la URL correspondiente en tu navegador (ej. `http://localhost/calendario_compartido`).
