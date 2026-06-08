<?php
// API de Lista de Compras en PHP (Integración con Python)
// Proyecto: Calendario Compartido Familiar

require_once 'config.php';

$action = isset($_GET['action']) ? $_GET['action'] : '';
$method = $_SERVER['REQUEST_METHOD'];
$userID = getRequestUserID();

if (!$userID) {
    sendJSON(["success" => false, "error" => "No autorizado. Falta User-ID."], 401);
}

$db = getDBConnection();

// --- 1. LEER LISTA Y ITEMS (GET) ---
if ($method === 'GET') {
    $grupoID = isset($_GET['grupo_id']) ? intval($_GET['grupo_id']) : 0;
    if ($grupoID <= 0) {
        sendJSON(["success" => false, "error" => "grupo_id no válido."], 400);
    }

    try {
        // Obtener lista principal
        $stmtList = $db->prepare("SELECT id, nombre FROM listas_compras WHERE grupo_id = ? LIMIT 1");
        $stmtList->execute([$grupoID]);
        $lista = $stmtList->fetch();

        if (!$lista) {
            // Crear lista por defecto si no existe
            $stmtCreate = $db->prepare("INSERT INTO listas_compras (grupo_id, nombre) VALUES (?, 'Lista de Compras Principal')");
            $stmtCreate->execute([$grupoID]);
            $listaID = $db->lastInsertId();
            $listaName = 'Lista de Compras Principal';
        } else {
            $listaID = $lista['id'];
            $listaName = $lista['nombre'];
        }

        // Obtener items de la lista
        $stmtItems = $db->prepare("
            SELECT i.*, u.nombre as actualizado_por_nombre 
            FROM items_compra i 
            LEFT JOIN usuarios u ON i.actualizado_por = u.id 
            WHERE i.lista_id = ? 
            ORDER BY i.comprado ASC, i.fecha_actualizacion DESC
        ");
        $stmtItems->execute([$listaID]);
        $items = $stmtItems->fetchAll();

        sendJSON([
            "success" => true,
            "list_id" => $listaID,
            "list_name" => $listaName,
            "items" => $items
        ]);

    } catch (PDOException $e) {
        sendJSON(["success" => false, "error" => "Error de base de datos: " . $e->getMessage()], 500);
    }
}

// --- 2. ACCIONES DE MODIFICACIÓN (POST) ---
if ($method === 'POST') {
    $input = getJSONInput();

    // AGREGAR ARTÍCULO
    if ($action === 'add_item') {
        $listaID = isset($input['lista_id']) ? intval($input['lista_id']) : 0;
        $nombre = isset($input['nombre']) ? trim($input['nombre']) : '';
        $cantidad = isset($input['cantidad']) ? intval($input['cantidad']) : 1;
        $unidad = isset($input['unidad']) ? trim($input['unidad']) : 'unidades';
        $force = isset($input['force']) ? (bool)$input['force'] : false;

        if ($listaID <= 0 || empty($nombre)) {
            sendJSON(["success" => false, "error" => "Datos incompletos para agregar el artículo."], 400);
        }

        try {
            // 1. Obtener ítems activos no comprados para la validación difusa
            $stmtExist = $db->prepare("SELECT id, nombre as name, comprado FROM items_compra WHERE lista_id = ? AND comprado = 0");
            $stmtExist->execute([$listaID]);
            $existingItems = $stmtExist->fetchAll();

            // 2. Ejecutar script Python para validación de similitud
            $dupResult = callPythonDuplicateChecker($nombre, $existingItems);

            if (isset($dupResult['error'])) {
                sendJSON(["success" => false, "error" => "Error de validación: " . $dupResult['error']], 400);
            }

            // 3. Si se sospecha duplicación y no se ha forzado el envío, advertir
            if ($dupResult['duplicate'] && !$force) {
                sendJSON([
                    "success" => false,
                    "duplicate" => true,
                    "error" => $dupResult['warning_message'],
                    "details" => $dupResult
                ], 200); // 200 con bandera 'duplicate' para diálogo de confirmación en el frontend
            }

            // 4. Insertar en la BD
            $stmtInsert = $db->prepare("
                INSERT INTO items_compra (lista_id, nombre, cantidad, unidad, comprado, actualizado_por, version) 
                VALUES (?, ?, ?, ?, 0, ?, 1)
            ");
            $stmtInsert->execute([$listaID, $nombre, $cantidad, $unidad, $userID]);
            $newID = $db->lastInsertId();

            sendJSON([
                "success" => true,
                "message" => "Artículo agregado con éxito.",
                "item_id" => $newID
            ]);

        } catch (PDOException $e) {
            sendJSON(["success" => false, "error" => "Error de base de datos: " . $e->getMessage()], 500);
        }
    }

    // MARCAR COMO COMPRADO / PENDIENTE
    elseif ($action === 'toggle_item') {
        $itemID = isset($input['id']) ? intval($input['id']) : 0;
        $comprado = isset($input['comprado']) ? intval($input['comprado']) : 0;
        $currentVersion = isset($input['version']) ? intval($input['version']) : 1;

        if ($itemID <= 0) {
            sendJSON(["success" => false, "error" => "ID de artículo no válido."], 400);
        }

        try {
            $db->beginTransaction();

            // Verificar versión en la BD
            $stmtVersion = $db->prepare("SELECT version FROM items_compra WHERE id = ? FOR UPDATE");
            $stmtVersion->execute([$itemID]);
            $itemRow = $stmtVersion->fetch();

            if (!$itemRow) {
                sendJSON(["success" => false, "error" => "El artículo no existe."], 404);
            }

            $dbVersion = intval($itemRow['version']);

            if ($dbVersion !== $currentVersion) {
                sendJSON([
                    "success" => false,
                    "concurrency_error" => true,
                    "error" => "El estado del artículo fue modificado por otro miembro. Recarga la lista."
                ], 409);
            }

            $newVersion = $dbVersion + 1;

            $stmtUpdate = $db->prepare("
                UPDATE items_compra 
                SET comprado = ?, actualizado_por = ?, version = ?, fecha_actualizacion = CURRENT_TIMESTAMP 
                WHERE id = ? AND version = ?
            ");
            $stmtUpdate->execute([$comprado, $userID, $newVersion, $itemID, $dbVersion]);

            $db->commit();

            sendJSON([
                "success" => true,
                "message" => "Artículo actualizado con éxito.",
                "version" => $newVersion
            ]);

        } catch (Exception $e) {
            if ($db->inTransaction()) {
                $db->rollBack();
            }
            sendJSON(["success" => false, "error" => "Error de base de datos: " . $e->getMessage()], 500);
        }
    }

    // ELIMINAR ARTÍCULO
    elseif ($action === 'delete_item') {
        $itemID = isset($input['id']) ? intval($input['id']) : 0;

        if ($itemID <= 0) {
            sendJSON(["success" => false, "error" => "ID no válido."], 400);
        }

        try {
            $stmt = $db->prepare("DELETE FROM items_compra WHERE id = ?");
            $stmt->execute([$itemID]);
            sendJSON(["success" => true, "message" => "Artículo eliminado con éxito."]);
        } catch (PDOException $e) {
            sendJSON(["success" => false, "error" => "Error al eliminar: " . $e->getMessage()], 500);
        }
    }

    else {
        sendJSON(["success" => false, "error" => "Acción POST no válida."], 400);
    }
}

/**
 * Invoca el corrector de duplicados difuso en Python enviando JSON mediante tuberías (pipes).
 */
function callPythonDuplicateChecker($proposedName, $existingItems) {
    $pythonScript = __DIR__ . '/../backend/duplicate_checker.py';
    
    $payload = json_encode([
        "proposed" => ["name" => $proposedName],
        "existing" => $existingItems,
        "threshold" => 0.75
    ]);

    $descriptorspec = [
        0 => ["pipe", "r"],
        1 => ["pipe", "w"],
        2 => ["pipe", "w"]
    ];

    $process = proc_open('python ' . escapeshellarg($pythonScript), $descriptorspec, $pipes);

    if (is_resource($process)) {
        fwrite($pipes[0], $payload);
        fclose($pipes[0]);

        $stdout = stream_get_contents($pipes[1]);
        fclose($pipes[1]);

        $stderr = stream_get_contents($pipes[2]);
        fclose($pipes[2]);

        $status = proc_close($process);

        if ($status !== 0 || !empty($stderr)) {
            return ["error" => "Ejecución de Python falló: " . (!empty($stderr) ? $stderr : "Código de salida $status")];
        }

        $result = json_decode($stdout, true);
        if (json_last_error() !== JSON_ERROR_NONE) {
            return ["error" => "Salida no JSON: " . $stdout];
        }

        return $result;
    }

    return ["error" => "No se pudo iniciar el comprobador en Python."];
}
?>
