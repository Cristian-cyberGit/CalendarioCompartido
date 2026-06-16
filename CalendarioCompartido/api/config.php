<?php
// Archivo de Configuración de Base de Datos y Encabezados Comunes
// Proyecto: Calendario Compartido Familiar

// Configuración de visualización de errores (para ambiente de desarrollo académico)
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

// Cabeceras HTTP estándar para API REST
header("Access-Control-Allow-Origin: *");
header("Content-Type: application/json; charset=UTF-8");
header("Access-Control-Allow-Methods: GET, POST, OPTIONS");
header("Access-Control-Allow-Headers: Content-Type, Access-Control-Allow-Headers, Authorization, X-Requested-With, User-ID");

// Manejo de solicitudes Preflight OPTIONS para CORS
if ($_SERVER['REQUEST_METHOD'] == 'OPTIONS') {
    http_response_code(200);
    exit();
}

// Parámetros de la Base de Datos MySQL
define('DB_HOST', 'localhost');
define('DB_USER', 'root');
define('DB_PASS', '');
define('DB_NAME', 'calendario_familiar');
define('DB_CHARSET', 'utf8mb4');

/**
 * Retorna la conexión PDO a MySQL.
 */
function getDBConnection() {
    try {
        $dsn = "mysql:host=" . DB_HOST . ";dbname=" . DB_NAME . ";charset=" . DB_CHARSET;
        $options = [
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES   => false,
        ];
        return new PDO($dsn, DB_USER, DB_PASS, $options);
    } catch (\PDOException $e) {
        sendJSON([
            "success" => false,
            "error" => "Error de conexión a la base de datos: " . $e->getMessage()
        ], 500);
        exit();
    }
}

/**
 * Helper para enviar respuestas JSON y terminar la ejecución.
 */
function sendJSON($data, $statusCode = 200) {
    http_response_code($statusCode);
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    exit();
}

/**
 * Obtiene el cuerpo de la solicitud JSON decodificado.
 */
function getJSONInput() {
    $rawInput = file_get_contents('php://input');
    if (empty($rawInput)) {
        return [];
    }
    $decoded = json_decode($rawInput, true);
    if (json_last_error() !== JSON_ERROR_NONE) {
        sendJSON(["success" => false, "error" => "Cuerpo de solicitud JSON mal formado."], 400);
    }
    return $decoded;
}

/**
 * Obtiene el ID de usuario desde las cabeceras.
 */
function getRequestUserID() {
    $headers = getallheaders();
    // Normalizar cabecera (las cabeceras pueden venir en minúsculas en algunos servidores)
    foreach ($headers as $key => $value) {
        if (strcasecmp($key, 'User-ID') === 0) {
            return intval($value);
        }
    }
    return null;
}
?>
