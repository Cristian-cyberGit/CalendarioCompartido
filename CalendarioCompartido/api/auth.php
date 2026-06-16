<?php
// API de Autenticación y Grupos en PHP
// Proyecto: Calendario Compartido Familiar

require_once 'config.php';

$action = isset($_GET['action']) ? $_GET['action'] : '';
$method = $_SERVER['REQUEST_METHOD'];

$db = getDBConnection();

// 1. Obtener información de usuario actual (GET)
if ($method === 'GET') {
    if ($action === 'get_user_info') {
        $userID = getRequestUserID();
        if (!$userID) {
            sendJSON(["success" => false, "error" => "No autorizado. Falta User-ID en cabeceras."], 401);
        }

        try {
            // Obtener datos de usuario
            $stmt = $db->prepare("SELECT id, nombre, email FROM usuarios WHERE id = ?");
            $stmt->execute([$userID]);
            $user = $stmt->fetch();

            if (!$user) {
                sendJSON(["success" => false, "error" => "Usuario no encontrado."], 404);
            }

            // Obtener grupo del usuario
            $stmtGroup = $db->prepare("
                SELECT g.id, g.nombre, g.codigo_acceso, m.rol 
                FROM grupos g 
                JOIN miembros_grupo m ON g.id = m.grupo_id 
                WHERE m.usuario_id = ? LIMIT 1
            ");
            $stmtGroup->execute([$userID]);
            $group = $stmtGroup->fetch();

            sendJSON([
                "success" => true,
                "user" => $user,
                "group" => $group ? $group : null
            ]);
        } catch (PDOException $e) {
            sendJSON(["success" => false, "error" => "Error de base de datos: " . $e->getMessage()], 500);
        }
    } else {
        sendJSON(["success" => false, "error" => "Acción GET no válida."], 400);
    }
    exit();
}

// 2. Operaciones de Modificación (POST)
if ($method === 'POST') {
    $input = getJSONInput();

    // LOGIN
    if ($action === 'login') {
        $email = isset($input['email']) ? trim($input['email']) : '';
        $password = isset($input['password']) ? $input['password'] : '';

        if (empty($email) || empty($password)) {
            sendJSON(["success" => false, "error" => "Email y contraseña requeridos."], 400);
        }

        try {
            $stmt = $db->prepare("SELECT * FROM usuarios WHERE email = ?");
            $stmt->execute([$email]);
            $user = $stmt->fetch();

            if ($user && password_verify($password, $user['password'])) {
                // Obtener grupo si tiene
                $stmtGroup = $db->prepare("
                    SELECT g.id, g.nombre, g.codigo_acceso, m.rol 
                    FROM grupos g 
                    JOIN miembros_grupo m ON g.id = m.grupo_id 
                    WHERE m.usuario_id = ? LIMIT 1
                ");
                $stmtGroup->execute([$user['id']]);
                $group = $stmtGroup->fetch();

                sendJSON([
                    "success" => true,
                    "user" => [
                        "id" => $user['id'],
                        "nombre" => $user['nombre'],
                        "email" => $user['email']
                    ],
                    "group" => $group ? $group : null
                ]);
            } else {
                sendJSON(["success" => false, "error" => "Credenciales incorrectas."], 401);
            }
        } catch (PDOException $e) {
            sendJSON(["success" => false, "error" => "Error de servidor: " . $e->getMessage()], 500);
        }
    }

    // REGISTRO
    elseif ($action === 'register') {
        $nombre = isset($input['nombre']) ? trim($input['nombre']) : '';
        $email = isset($input['email']) ? trim($input['email']) : '';
        $password = isset($input['password']) ? $input['password'] : '';

        if (empty($nombre) || empty($email) || empty($password)) {
            sendJSON(["success" => false, "error" => "Todos los campos son requeridos."], 400);
        }

        try {
            // Verificar si el email ya existe
            $stmtCheck = $db->prepare("SELECT id FROM usuarios WHERE email = ?");
            $stmtCheck->execute([$email]);
            if ($stmtCheck->fetch()) {
                sendJSON(["success" => false, "error" => "El correo electrónico ya está registrado."], 409);
            }

            // Registrar usuario
            $hashedPassword = password_hash($password, PASSWORD_DEFAULT);
            $stmt = $db->prepare("INSERT INTO usuarios (nombre, email, password) VALUES (?, ?, ?)");
            $stmt->execute([$nombre, $email, $hashedPassword]);
            $newID = $db->lastInsertId();

            sendJSON([
                "success" => true,
                "message" => "Usuario registrado con éxito.",
                "user" => [
                    "id" => $newID,
                    "nombre" => $nombre,
                    "email" => $email
                ]
            ]);
        } catch (PDOException $e) {
            sendJSON(["success" => false, "error" => "Error al registrar usuario: " . $e->getMessage()], 500);
        }
    }

    // CREAR GRUPO
    elseif ($action === 'create_group') {
        $userID = getRequestUserID();
        if (!$userID) {
            sendJSON(["success" => false, "error" => "No autorizado."], 401);
        }

        $nombre = isset($input['nombre']) ? trim($input['nombre']) : '';
        if (empty($nombre)) {
            sendJSON(["success" => false, "error" => "El nombre del grupo es obligatorio."], 400);
        }

        try {
            $db->beginTransaction();

            // Generar código de acceso único
            $codigo = strtoupper(bin2hex(random_bytes(4))); // 8 caracteres

            $stmt = $db->prepare("INSERT INTO grupos (nombre, codigo_acceso) VALUES (?, ?)");
            $stmt->execute([$nombre, $codigo]);
            $grupoID = $db->lastInsertId();

            // Asociar creador como 'admin'
            $stmtMember = $db->prepare("INSERT INTO miembros_grupo (grupo_id, usuario_id, rol) VALUES (?, ?, 'admin')");
            $stmtMember->execute([$grupoID, $userID]);

            // Crear lista de compras principal por defecto
            $stmtList = $db->prepare("INSERT INTO listas_compras (grupo_id, nombre) VALUES (?, 'Lista de Compras Principal')");
            $stmtList->execute([$grupoID]);

            $db->commit();

            sendJSON([
                "success" => true,
                "group" => [
                    "id" => $grupoID,
                    "nombre" => $nombre,
                    "codigo_acceso" => $codigo,
                    "rol" => "admin"
                ]
            ]);
        } catch (Exception $e) {
            $db->rollBack();
            sendJSON(["success" => false, "error" => "Error al crear grupo: " . $e->getMessage()], 500);
        }
    }

    // UNIRSE A GRUPO
    elseif ($action === 'join_group') {
        $userID = getRequestUserID();
        if (!$userID) {
            sendJSON(["success" => false, "error" => "No autorizado."], 401);
        }

        $codigo = isset($input['codigo_acceso']) ? strtoupper(trim($input['codigo_acceso'])) : '';
        if (empty($codigo)) {
            sendJSON(["success" => false, "error" => "El código de acceso es obligatorio."], 400);
        }

        try {
            // Verificar existencia del grupo
            $stmtGroup = $db->prepare("SELECT * FROM grupos WHERE codigo_acceso = ?");
            $stmtGroup->execute([$codigo]);
            $group = $stmtGroup->fetch();

            if (!$group) {
                sendJSON(["success" => false, "error" => "Código de acceso no válido."], 404);
            }

            // Unirse al grupo
            $stmtJoin = $db->prepare("INSERT INTO miembros_grupo (grupo_id, usuario_id, rol) VALUES (?, ?, 'miembro')");
            $stmtJoin->execute([$group['id'], $userID]);

            sendJSON([
                "success" => true,
                "message" => "Te has unido al grupo con éxito.",
                "group" => [
                    "id" => $group['id'],
                    "nombre" => $group['nombre'],
                    "codigo_acceso" => $group['codigo_acceso'],
                    "rol" => "miembro"
                ]
            ]);
        } catch (PDOException $e) {
            // Código SQLSTATE 23000 es duplicado (Integrity Constraint Violation)
            if ($e->getCode() == 23000) {
                sendJSON(["success" => false, "error" => "Ya eres miembro de este grupo."], 409);
            }
            sendJSON(["success" => false, "error" => "Error de servidor: " . $e->getMessage()], 500);
        }
    }

    // Acción no encontrada
    else {
        sendJSON(["success" => false, "error" => "Acción POST no válida."], 400);
    }
}
?>
