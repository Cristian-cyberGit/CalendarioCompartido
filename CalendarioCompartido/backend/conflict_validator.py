#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validador Avanzado de Conflictos de Horario
Analiza si un evento propuesto se traslapa con eventos existentes.
Calcula advertencias de proximidad (menos de 15 min de diferencia) y sugiere alternativas libres.
Soporta ejecución CLI (vía JSON en stdin) e importación directa como módulo.
"""

import sys
import json
from datetime import datetime, timedelta

def parse_time(dt_str):
    """Convierte cadena de fecha/hora a objeto datetime."""
    formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"]
    for fmt in formats:
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Formato de fecha no válido: '{dt_str}'. Utilice YYYY-MM-DD HH:MM:SS")

def format_time(dt):
    """Convierte objeto datetime a cadena estándar."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def find_alternatives(proposed_start, proposed_end, existing_events, duration):
    """
    Busca alternativas de horarios libres cercanos al propuesto.
    Evalúa ventanas de tiempo antes y después.
    """
    suggestions = []
    
    # Ordenar eventos existentes por hora de inicio
    sorted_events = sorted(existing_events, key=lambda e: parse_time(e['start']))
    
    # 1. Sugerir inmediatamente después del evento en conflicto más tardío
    if sorted_events:
        last_event_end = max(parse_time(e['end']) for e in sorted_events)
        sug_start_1 = last_event_end + timedelta(minutes=5) # 5 minutos de holgura
        sug_end_1 = sug_start_1 + duration
        suggestions.append({
            "start": format_time(sug_start_1),
            "end": format_time(sug_end_1),
            "reason": "Inmediatamente después del último evento del día"
        })

    # 2. Sugerir antes del primer evento en conflicto
    if sorted_events:
        first_event_start = min(parse_time(e['start']) for e in sorted_events)
        sug_end_2 = first_event_start - timedelta(minutes=5)
        sug_start_2 = sug_end_2 - duration
        # Solo sugerir si no es en el pasado lejano respecto a la propuesta original
        if sug_start_2 >= datetime.now():
            suggestions.append({
                "start": format_time(sug_start_2),
                "end": format_time(sug_end_2),
                "reason": "Antes del primer evento en conflicto"
            })
            
    # 3. Buscar huecos (gaps) entre los eventos existentes que quepan la duración
    for i in range(len(sorted_events) - 1):
        current_end = parse_time(sorted_events[i]['end'])
        next_start = parse_time(sorted_events[i+1]['start'])
        gap = (next_start - current_end).total_seconds()
        
        if gap >= duration.total_seconds():
            sug_start_gap = current_end + timedelta(minutes=5)
            sug_end_gap = sug_start_gap + duration
            if sug_end_gap <= next_start:
                suggestions.append({
                    "start": format_time(sug_start_gap),
                    "end": format_time(sug_end_gap),
                    "reason": "Espacio libre detectado entre eventos del día"
                })
                break # Solo necesitamos una alternativa de gap por ahora

    return suggestions[:2] # Retornar máximo 2 sugerencias

def validate_schedule(proposed_event, existing_events):
    """
    Comprueba si existe conflicto de horario y calcula detalles.
    - proposed_event: dict con 'start' y 'end' (cadenas de texto).
    - existing_events: list de dicts, cada uno con 'id', 'title', 'start', 'end'.
    """
    try:
        p_start = parse_time(proposed_event['start'])
        p_end = parse_time(proposed_event['end'])
    except Exception as e:
        return {
            "error": f"Error parseando evento propuesto: {str(e)}",
            "conflict": True
        }
    
    if p_start >= p_end:
        return {
            "error": "La fecha de inicio debe ser anterior a la de fin.",
            "conflict": True
        }
        
    duration = p_end - p_start
    conflicts = []
    warnings = []
    
    for event in existing_events:
        try:
            e_start = parse_time(event['start'])
            e_end = parse_time(event['end'])
        except Exception as err:
            # Si un evento existente tiene mal la fecha, lo ignoramos para evitar bloquear al usuario,
            # pero sería bueno registrar el error
            continue
            
        # 1. Detección de traslape absoluto (A.start < B.end y B.start < A.end)
        if p_start < e_end and e_start < p_end:
            conflicts.append({
                "id": event.get("id"),
                "title": event.get("title", "Evento sin título"),
                "start": event['start'],
                "end": event['end'],
                "type": "overlap"
            })
            
        # 2. Detección de proximidad (menos de 15 minutos entre eventos)
        elif not (p_start < e_end and e_start < p_end):
            # No hay traslape, pero veamos si están muy cerca
            diff_before = (p_start - e_end).total_seconds() / 60.0
            diff_after = (e_start - p_end).total_seconds() / 60.0
            
            if 0 <= diff_before < 15:
                warnings.append({
                    "id": event.get("id"),
                    "title": event.get("title"),
                    "message": f"Inicia solo {int(diff_before)} minutos después de terminar '{event.get('title')}'."
                })
            elif 0 <= diff_after < 15:
                warnings.append({
                    "id": event.get("id"),
                    "title": event.get("title"),
                    "message": f"Termina solo {int(diff_after)} minutos antes de iniciar '{event.get('title')}'."
                })

    has_conflict = len(conflicts) > 0
    result = {
        "conflict": has_conflict,
        "conflict_count": len(conflicts),
        "conflicting_events": conflicts,
        "warnings": warnings
    }
    
    if has_conflict:
        # Encontrar horarios alternativos
        result["suggestions"] = find_alternatives(p_start, p_end, conflicts, duration)
    else:
        result["suggestions"] = []
        
    return result

def main():
    # Leer entrada JSON desde la entrada estándar
    try:
        input_data = json.loads(sys.stdin.read())
        proposed = input_data.get("proposed")
        existing = input_data.get("existing", [])
        
        if not proposed:
            print(json.dumps({"error": "Falta el objeto 'proposed' en la entrada.", "conflict": True}))
            sys.exit(1)
            
        result = validate_schedule(proposed, existing)
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(json.dumps({"error": f"Error crítico de ejecución: {str(e)}", "conflict": True}))
        sys.exit(1)

if __name__ == "__main__":
    # Solo ejecutar si se invoca directamente desde CLI
    # Permite depurar pasándole argumentos si no hay stdin (pero stdin es la vía primaria)
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_proposed = {"start": "2026-06-15 09:00:00", "end": "2026-06-15 10:00:00"}
        test_existing = [
            {"id": 1, "title": "Médico", "start": "2026-06-15 09:30:00", "end": "2026-06-15 10:30:00"}
        ]
        print(json.dumps(validate_schedule(test_proposed, test_existing), indent=2))
    else:
        main()
