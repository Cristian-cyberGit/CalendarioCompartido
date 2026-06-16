<?php
// API de Eventos en PHP (Integración Híbrida con Python)
// Proyecto: Calendario Compartido Familiar

require_once 'config.php';

$action = isset($_GET['action']) ? $_GET['action'] : '';
$method = $_SERVER['REQUEST_METHOD'];
$userID = getRequestUserID();

if (!$userID) {
    sendJSON(["success" => false, "error" => "No autorizado. Falta User-ID."], 401);
}

$db = getDBConnection();

// --- 1. LEER EVENTOS (GET) ---
if ($method === 'GET') {
    $grupoID = isset($_GET['grupo_id']) ? intval($_GET['grupo_id']) : 0;
    if ($grupoID <= 0) {
        sendJSON(["success" => false, "error" => "grupo_id no válido."], 400);
    }

    try {
        $stmt = $db->prepare("
            SELECT e.*, u.nombre as creador_nombre 
            FROM eventos e 
            JOIN usuarios u ON e.creado_por = u.id 
            WHERE e.grupo_id = ? 
            ORDER BY e.fecha_inicio ASC
        ");
        $stmt->execute([$grupoID]);
        $events = $stmt->fetchAll();
        
        sendJSON(["success" => true, "events" => $events]);
    } catch (PDOException $e) {
        sendJSON(["success" => false, "error" => "Error de base de datos: " . $e->getMessage()], 500);
    }
}

// --- 2. ESCRIBIR/MODIFICAR EVENTOS (POST) ---
if ($method === 'POST') {
    $input = getJSONInput();

    // CREACIÓN DE EVENTO
    if ($action === 'create') {
        $grupoID = isset($input['grupo_id']) ? intval($input['grupo_id']) : 0;
        $titulo = isset($input['titulo']) ? trim($input['titulo']) : '';
        $descripcion = isset($input['descripcion']) ? trim($input['descripcion']) : '';
        $start = isset($input['fecha_inicio']) ? trim($input['fecha_inicio']) : '';
        $end = isset($input['fecha_fin']) ? trim($input['fecha_fin']) : '';
        $categoria = isset($input['categoria']) ? trim($input['categoria']) : 'general';
        $force = isset($input['force']) ? (bool)$input['force'] : false;

        if ($grupoID <= 0 || empty($titulo) || empty($start) || empty($end)) {
            sendJSON(["success" => false, "error" => "Campos requeridos incompletos."], 400);
        }

        try {
            // 1. Obtener eventos existentes del grupo para la validación
            $stmtExist = $db->prepare("SELECT id, titulo, fecha_inicio as start, fecha_fin as end FROM eventos WHERE grupo_id = ?");
            $stmtExist->execute([$grupoID]);
            $existingEvents = $stmtExist->fetchAll();

            // 2. Ejecutar script Python para validación de traslape y proximidad
            $valResult = callPythonValidator($start, $end, $existingEvents);

            if (isset($valResult['error'])) {
                sendJSON(["success" => false, "error" => "Error del validador: " . $valResult['error']], 400);
            }

            // 3. Evaluar conflicto absoluto (traslape)
            if ($valResult['conflict']) {
                sendJSON([
                    "success" => false,
                    "conflict" => true,
                    "error" => "Conflicto de horario: El evento coincide con otra actividad programada.",
                    "details" => $valResult
                ], 409);
            }

            // 4. Evaluar advertencias de proximidad (holgura < 15 min)
            if (!empty($valResult['warnings']) && !$force) {
                sendJSON([
                    "success" => false,
                    "warning" => true,
                    "error" => "Advertencia de proximidad entre horarios.",
                    "details" => $valResult
                ], 200);
            }

            // 5. Inserción con transacción para concurrencia
            $db->beginTransaction();
            $stmtInsert = $db->prepare("
                INSERT INTO eventos (grupo_id, titulo, descripcion, fecha_inicio, fecha_fin, categoria, creado_por, version) 
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ");
            $stmtInsert->execute([$grupoID, $titulo, $descripcion, $start, $end, $categoria, $userID]);
            $newID = $db->lastInsertId();
            $db->commit();

            sendJSON([
                "success" => true,
                "message" => "Evento creado con éxito.",
                "event_id" => $newID
            ]);

        } catch (Exception $e) {
            if ($db->inTransaction()) {
                $db->rollBack();
            }
            sendJSON(["success" => false, "error" => "Error al guardar evento: " . $e->getMessage()], 500);
        }
    }

    // ACTUALIZACIÓN DE EVENTO
    elseif ($action === 'update') {
        $eventID = isset($input['id']) ? intval($input['id']) : 0;
        $grupoID = isset($input['grupo_id']) ? intval($input['grupo_id']) : 0;
        $titulo = isset($input['titulo']) ? trim($input['titulo']) : '';
        $descripcion = isset($input['descripcion']) ? trim($input['descripcion']) : '';
        $start = isset($input['fecha_inicio']) ? trim($input['fecha_inicio']) : '';
        $end = isset($input['fecha_fin']) ? trim($input['fecha_fin']) : '';
        $categoria = isset($input['categoria']) ? trim($input['categoria']) : 'general';
        $currentVersion = isset($input['version']) ? intval($input['version']) : 1;
        $force = isset($input['force']) ? (bool)$input['force'] : false;

        if ($eventID <= 0 || $grupoID <= 0 || empty($titulo) || empty($start) || empty($end)) {
            sendJSON(["success" => false, "error" => "Campos obligatorios incompletos."], 400);
        }

        try {
            // 1. Obtener eventos existentes excluyendo el actual
            $stmtExist = $db->prepare("SELECT id, titulo, fecha_inicio as start, fecha_fin as end FROM eventos WHERE grupo_id = ? AND id != ?");
            $stmtExist->execute([$grupoID, $eventID]);
            $existingEvents = $stmtExist->fetchAll();

            // 2. Ejecutar script Python
            $valResult = callPythonValidator($start, $end, $existingEvents);

            if (isset($valResult['error'])) {
                sendJSON(["success" => false, "error" => $valResult['error']], 400);
            }

            if ($valResult['conflict']) {
                sendJSON([
                    "success" => false,
                    "conflict" => true,
                    "error" => "Conflicto de horario: El evento coincide con otra actividad programada.",
                    "details" => $valResult
                ], 409);
            }

            if (!empty($valResult['warnings']) && !$force) {
                sendJSON([
                    "success" => false,
                    "warning" => true,
                    "error" => "Advertencia de proximidad.",
                    "details" => $valResult
                ], 200);
            }

            // 3. Transacción con Bloqueo Optimista
            $db->beginTransaction();

            // Verificar versión actual en BD
            $stmtVersion = $db->prepare("SELECT version FROM eventos WHERE id = ? FOR UPDATE");
            $stmtVersion->execute([$eventID]);
            $eventRow = $stmtVersion->fetch();

            if (!$eventRow) {
                sendJSON(["success" => false, "error" => "El evento ya no existe."], 404);
            }

            $dbVersion = intval($eventRow['version']);

            if ($dbVersion !== $currentVersion) {
                sendJSON([
                    "success" => false,
                    "concurrency_error" => true,
                    "error" => "El evento fue modificado por otro usuario de forma concurrente. Recarga los datos."
                ], 409);
            }

            $newVersion = $dbVersion + 1;

            // Actualizar registro incrementando la versión
            $stmtUpdate = $db->prepare("
                UPDATE eventos 
                SET titulo = ?, descripcion = ?, fecha_inicio = ?, fecha_fin = ?, categoria = ?, version = ?
                WHERE id = ? AND version = ?
            ");
            $stmtUpdate->execute([$titulo, $descripcion, $start, $end, $categoria, $newVersion, $eventID, $dbVersion]);

            $db->commit();

            sendJSON([
                "success" => true,
                "message" => "Evento actualizado con éxito.",
                "version" => $newVersion
            ]);

        } catch (Exception $e) {
            if ($db->inTransaction()) {
                $db->rollBack();
            }
            sendJSON(["success" => false, "error" => "Error al actualizar: " . $e->getMessage()], 500);
        }
    }

    // ELIMINACIÓN DE EVENTO
    elseif ($action === 'delete') {
        $eventID = isset($input['id']) ? intval($input['id']) : 0;
        if ($eventID <= 0) {
            sendJSON(["success" => false, "error" => "ID de evento no válido."], 400);
        }

        try {
            $stmt = $db->prepare("DELETE FROM eventos WHERE id = ?");
            $stmt->execute([$eventID]);
            sendJSON(["success" => true, "message" => "Evento eliminado con éxito."]);
        } catch (PDOException $e) {
            sendJSON(["success" => false, "error" => "Error de base de datos: " . $e->getMessage()], 500);
        }
    }

    else {
        sendJSON(["success" => false, "error" => "Acción POST no válida."], 400);
    }
}

/**
 * Invoca el script Python para analizar traslapes mediante tuberías de entrada/salida (pipes).
 */
function callPythonValidator($start, $end, $existingEvents) {
    // Definir la ruta relativa al script de Python
    $pythonScript = __DIR__ . '/../backend/conflict_validator.py';
    
    // Preparar el JSON de entrada
    $payload = json_encode([
        "proposed" => [
            "start" => $start,
            "end" => $end
        ],
        "existing" => $existingEvents
    ]);

    // Especificar canales
    $descriptorspec = [
        0 => ["pipe", "r"], // stdin
        1 => ["pipe", "w"], // stdout
        2 => ["pipe", "w"]  // stderr
    ];

    // Abrir proceso Python
    $process = proc_open('python ' . escapeshellarg($pythonScript), $descriptorspec, $pipes);

    if (is_resource($process)) {
        // Enviar datos JSON por stdin
        fwrite($pipes[0], $payload);
        fclose($pipes[0]);

        // Leer salida
        $stdout = stream_get_contents($pipes[1]);
        fclose($pipes[1]);

        // Leer errores
        $stderr = stream_get_contents($pipes[2]);
        fclose($pipes[2]);

        $status = proc_close($process);

        if ($status !== 0 || !empty($stderr)) {
            return ["error" => "Ejecución de Python falló: " . (!empty($stderr) ? $stderr : "Código de salida $status")];
        }

        $result = json_decode($stdout, true);
        if (json_last_error() !== JSON_ERROR_NONE) {
            return ["error" => "Salida de Python no es un JSON válido: " . $stdout];
        }

        return $result;
    }

    return ["error" => "No se pudo iniciar el validador en Python."];
}
?>
