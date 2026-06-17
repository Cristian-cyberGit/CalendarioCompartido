#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Prueba de Estrés y Concurrencia
Simula múltiples usuarios familiares intentando realizar acciones en paralelo
(por ejemplo, agendar eventos en el mismo horario o agregar artículos de forma concurrente).
Valida la integridad de las transacciones, la tasa de éxito y los tiempos de respuesta.
"""

import threading
import time
import json
import urllib.request
import urllib.error

# Configuración de la prueba
BASE_URL = "http://localhost:8000"
NUM_HILOS = 15          # Cantidad de usuarios simultáneos
GRUPO_ID = 1            # Grupo de prueba predefinido
USUARIOS = [1, 2, 3]    # IDs de usuarios de prueba semilla

results = {
    "exitos": 0,
    "conflictos_esperados": 0,
    "errores_inesperados": 0,
    "detalles_errores": [],
    "tiempos_respuesta": []
}

lock = threading.Lock()

def send_post_request(url, payload, user_id):
    """Envía una solicitud POST y registra el tiempo de respuesta y resultado."""
    data_bytes = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data_bytes,
        headers={
            'Content-Type': 'application/json',
            'User-ID': str(user_id)
        },
        method='POST'
    )
    
    start_time = time.time()
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            resp_body = response.read().decode('utf-8')
            resp_json = json.loads(resp_body)
            duration = time.time() - start_time
            
            with lock:
                results["tiempos_respuesta"].append(duration)
                # El servidor Python devuelve 200 con warning/duplicate o success
                if resp_json.get("success"):
                    results["exitos"] += 1
                elif resp_json.get("duplicate") or resp_json.get("warning"):
                    results["conflictos_esperados"] += 1
                else:
                    results["errores_inesperados"] += 1
                    results["detalles_errores"].append(f"Respuesta sin éxito: {resp_json}")
                    
    except urllib.error.HTTPError as e:
        duration = time.time() - start_time
        try:
            resp_body = e.read().decode('utf-8')
            resp_json = json.loads(resp_body)
        except Exception:
            resp_json = {}
            
        with lock:
            results["tiempos_respuesta"].append(duration)
            # 409 es un conflicto de horario esperado (bloqueado por el validador)
            if e.code == 409:
                results["conflictos_esperados"] += 1
            else:
                results["errores_inesperados"] += 1
                results["detalles_errores"].append(f"HTTP {e.code}: {resp_body}")
                
    except Exception as e:
        with lock:
            results["errores_inesperados"] += 1
            results["detalles_errores"].append(f"Excepción: {str(e)}")

def stress_test_events():
    """Ejecuta una ráfaga de creación de eventos concurrentes en la misma franja horaria."""
    print(f"\n--- Iniciando prueba de estrés: {NUM_HILOS} peticiones concurrentes de eventos ---")
    threads = []
    
    url = f"{BASE_URL}/api/events.php?action=create"
    
    # Todos intentan reservar la misma hora el mismo día
    payload = {
        "grupo_id": GRUPO_ID,
        "titulo": "Reunión de Emergencia Familiar",
        "descripcion": "Todos intentando agendar al mismo tiempo",
        "fecha_inicio": "2026-06-20 18:00:00",
        "fecha_fin": "2026-06-20 19:00:00",
        "categoria": "hogar",
        "force": False
    }

    start_burst = time.time()
    
    for i in range(NUM_HILOS):
        # Rotar usuarios
        u_id = USUARIOS[i % len(USUARIOS)]
        t = threading.Thread(target=send_post_request, args=(url, payload, u_id))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    total_time = time.time() - start_burst
    
    # Calcular métricas
    avg_time = sum(results["tiempos_respuesta"]) / len(results["tiempos_respuesta"]) if results["tiempos_respuesta"] else 0
    max_time = max(results["tiempos_respuesta"]) if results["tiempos_respuesta"] else 0
    
    print("\nResultados de la Prueba de Eventos:")
    print(f"  - Tiempo total de ráfaga: {total_time:.3f} segundos")
    print(f"  - Eventos Creados con Éxito (Transacción Ok): {results['exitos']}")
    print(f"  - Conflictos de Horario Detectados y Evitados (Python OK): {results['conflictos_esperados']}")
    print(f"  - Errores Críticos / Excepciones: {results['errores_inesperados']}")
    print(f"  - Latencia Promedio de Respuesta: {avg_time*1000:.1f} ms")
    print(f"  - Latencia Máxima de Respuesta: {max_time*1000:.1f} ms")
    
    if results["errores_inesperados"] > 0:
        print("\nDetalles de errores inesperados:")
        for err in results["detalles_errores"][:5]:
            print(f"  - {err}")
            
    # Deberia haber exactamente 1 exito (el primero que entra en la base de datos)
    # y el resto deberian ser conflictos evitados, garantizando la consistencia.
    if results["exitos"] == 1 and results["errores_inesperados"] == 0:
        print("\n[OK] PRUEBA EXITOSA: Se garantizo la consistencia absoluta. Solo 1 evento fue reservado y los traslapes concurrentes fueron rechazados de manera segura.")
    else:
        print("\n[WARN] Advertencia: Esperado 1 exito y 0 errores. Revisa si el servidor esta corriendo en http://localhost:8000.")

if __name__ == "__main__":
    # Comprobar si el servidor está activo antes de correr
    try:
        urllib.request.urlopen(BASE_URL, timeout=2)
        stress_test_events()
    except Exception:
        print(f"Error: El servidor local no parece estar activo en {BASE_URL}.")
        print("Asegúrate de ejecutar primero: python server.py")
