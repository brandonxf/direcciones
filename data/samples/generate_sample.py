"""Genera un Excel de ejemplo con pasajeros del departamento del Atlántico (Colombia)
para probar la Fase 1 (ingesta) sin depender de APIs.
"""
import pandas as pd

rows = [
    {"identificador": "1001", "nombre": "Ana Torres", "direccion": "cll 84 # 46 - 30, barranquilla", "turno": "mañana", "barrio": ""},
    {"identificador": "1002", "nombre": "Carlos Ruiz", "direccion": "Cra 46 No 82-25, Barranquilla", "turno": "mañana", "barrio": ""},
    {"identificador": "1003", "nombre": "Marta Gómez", "direccion": "Cll 30 #22-18, Soledad, Atlantico", "turno": "mañana", "barrio": ""},
    {"identificador": "1004", "nombre": "", "direccion": "direccion sin nombre", "turno": "mañana", "barrio": ""},  # fila inválida (RF-03)
    {"identificador": "1005", "nombre": "Luis Pérez", "direccion": "Cra 21 # 15-40, Malambo", "turno": "tarde", "barrio": ""},
    {"identificador": "1006", "nombre": "Sara Julio", "direccion": "Calle 3 # 5-20, Puerto Colombia", "turno": "tarde", "barrio": ""},
    # Ejemplo real: "Calle 26" se repite en ~5 barrios distintos de Soledad. Sin el barrio,
    # Nominatim puede confundirla con una de otro sector, a varios km de distancia.
    {"identificador": "1007", "nombre": "Brandon Acevedo", "direccion": "calle 26 #17d-23, soledad Atlantico", "turno": "mañana", "barrio": "Boulevard Sol Real"},
]

df = pd.DataFrame(rows)
df.to_excel("data/samples/pasajeros.xlsx", index=False)
print("Archivo generado: data/samples/pasajeros.xlsx")
