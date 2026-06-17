#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validador de Artículos Duplicados en Listas de Compras
Utiliza comparación difusa de texto (difflib - Standard Library) para detectar
elementos con nombres idénticos o muy similares, evitando duplicaciones por errores de escritura.
"""

import sys
import json
from difflib import SequenceMatcher

def clean_string(s):
    """Limpia y normaliza la cadena para mejorar la comparación."""
    if not s:
        return ""
    # Convertir a minúsculas, remover espacios extra y acentos comunes
    s = s.lower().strip()
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ü': 'u', 'ñ': 'n'
    }
    for orig, rep in replacements.items():
        s = s.replace(orig, rep)
    return s

def calculate_similarity(a, b):
    """Calcula la similitud de Jaro-Winkler o ratio de similitud básica mediante difflib."""
    clean_a = clean_string(a)
    clean_b = clean_string(b)
    
    # Coincidencia exacta post-limpieza
    if clean_a == clean_b:
        return 1.0
        
    # Coincidencia parcial por palabras
    words_a = set(clean_a.split())
    words_b = set(clean_b.split())
    
    # Intersección de palabras
    if words_a and words_b:
        intersection = words_a.intersection(words_b)
        # Si comparten palabras clave importantes (ej. "Leche" en "Leche condensada" y "Leche descremada")
        # El ratio del SequenceMatcher evaluará mejor el contexto completo
        pass
        
    return SequenceMatcher(None, clean_a, clean_b).ratio()

def check_duplicates(proposed_name, existing_items, threshold=0.75):
    """
    Compara el nombre del artículo propuesto con la lista de existentes.
    - proposed_name: string con el nombre del artículo.
    - existing_items: lista de dicts con 'id', 'name', 'comprado'.
    - threshold: umbral de similitud (default 0.75, donde 1.0 es idéntico).
    """
    if not proposed_name:
        return {"duplicate": False, "matches": []}
        
    matches = []
    
    for item in existing_items:
        # Solo comprobar contra artículos NO comprados (activos en la lista)
        if item.get('comprado', 0) == 1:
            continue
            
        name_existing = item.get('name', '')
        sim = calculate_similarity(proposed_name, name_existing)
        
        # Si supera el umbral de sospecha
        if sim >= threshold:
            matches.append({
                "id": item.get("id"),
                "name": name_existing,
                "similarity": round(sim, 2),
                "exact_match": sim == 1.0
            })
            
    # Ordenar por mayor similitud
    matches = sorted(matches, key=lambda m: m['similarity'], reverse=True)
    
    is_duplicate = len(matches) > 0
    
    # Crear un mensaje amigable de sugerencia si hay sospechas
    warning_message = ""
    if is_duplicate:
        best_match = matches[0]
        if best_match['exact_match']:
            warning_message = f"'{proposed_name}' ya está en la lista de compras."
        else:
            warning_message = f"¿Quisiste decir '{best_match['name']}'? Ya existe un artículo similar con un {int(best_match['similarity']*100)}% de coincidencia."
            
    return {
        "duplicate": is_duplicate,
        "warning_message": warning_message,
        "matches": matches
    }

def main():
    try:
        input_data = json.loads(sys.stdin.read())
        proposed = input_data.get("proposed")
        existing = input_data.get("existing", [])
        threshold = input_data.get("threshold", 0.75)
        
        if not proposed or not isinstance(proposed, dict) or "name" not in proposed:
            print(json.dumps({"error": "Falta el nombre del artículo propuesto ('proposed.name').", "duplicate": False}))
            sys.exit(1)
            
        result = check_duplicates(proposed["name"], existing, threshold)
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(json.dumps({"error": f"Error crítico en duplicate_checker: {str(e)}", "duplicate": False}))
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_proposed = {"name": "leche entera"}
        test_existing = [
            {"id": 1, "name": "Leche Semidescremada", "comprado": 0},
            {"id": 2, "name": "Arroz", "comprado": 0}
        ]
        print(json.dumps(check_duplicates(test_proposed["name"], test_existing), indent=2))
    else:
        main()
