<?php
// API de Turnos Rotativos en PHP
// Proyecto: Calendario Compartido Familiar

require_once 'config.php';

$action = isset($_GET['action']) ? $_GET['action'] : '';
$method = $_SERVER['REQUEST_METHOD'];
$userID = getRequestUserID();

if (!$userID) {
    sendJSON(["success" => false, "error" => "No autorizado. Falta User-ID."], 401);
}

$db = getDBConnection();

// --- 1. LEER TURNOS (GET) ---
if ($method === 'GET') {
    $grupoID = isset($_GET['grupo_id']) ? intval($_GET['grupo_id']) : 0;
    if ($grupoID <= 0) {
        sendJSON(["success" => false, "error" => "grupo_id no válido."], 400);
    }

    try {
        $stmt = $db->prepare("
            SELECT t.id, t.grupo_id, t.usuario_id, t.fecha, t.tipo, u.nombre as usuario_nombre
            FROM turnos t
            JOIN usuarios u ON t.usuario_id = u.id
            WHERE t.grupo_id = ?
        ");
        $stmt->execute([$grupoID]);
        $shifts = $stmt->fetchAll();
        
        sendJSON(["success" => true, "shifts" => $shifts]);
    } catch (PDOException $e) {
        sendJSON(["success" => false, "error" => "Error de base de datos: " . $e->getMessage()], 500);
    }
}

// --- 2. ESCRIBIR/MODIFICAR TURNOS (POST) ---
if ($method === 'POST') {
    $input = getJSONInput();

    if ($action === 'set') {
        $grupoID = isset($input['grupo_id']) ? intval($input['grupo_id']) : 0;
        $fecha = isset($input['fecha']) ? trim($input['fecha']) : '';
        $tipo = isset($input['tipo']) ? trim($input['tipo']) : '';

        if ($grupoID <= 0 || empty($fecha)) {
            sendJSON(["success" => false, "error" => "Campos obligatorios incompletos."], 400);
        }

        try {
            $db->beginTransaction();

            if ($tipo === 'borrar' || empty($tipo)) {
                // Eliminar turno si es tipo borrar
                $stmtDelete = $db->prepare("DELETE FROM turnos WHERE usuario_id = ? AND fecha = ?");
                $stmtDelete->execute([$userID, $fecha]);
                $message = "Turno eliminado con éxito.";
            } else {
                // Insertar o actualizar turno
                $stmtSet = $db->prepare("
                    INSERT INTO turnos (grupo_id, usuario_id, fecha, tipo)
                    VALUES (?, ?, ?, ?)
                    ON DUPLICATE KEY UPDATE tipo = VALUES(tipo)
                ");
                $stmtSet->execute([$grupoID, $userID, $fecha, $tipo]);
                $message = "Turno registrado/actualizado con éxito.";
            }

            $db->commit();
            sendJSON(["success" => true, "message" => $message]);

        } catch (Exception $e) {
            if ($db->inTransaction()) {
                $db->rollBack();
            }
            sendJSON(["success" => false, "error" => "Error al guardar el turno: " . $e->getMessage()], 500);
        }
    } else {
        sendJSON(["success" => false, "error" => "Acción POST no válida."], 400);
    }
}
?>
