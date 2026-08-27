"""Genera un Excel de prueba con 20 pasajeros de distintos municipios del Atlántico.

Las direcciones usan calles y barrios reales de cada municipio (nomenclatura vial real de
Barranquilla, Soledad, Malambo, Puerto Colombia, Galapa y Baranoa). El barrio SIEMPRE incluye
el municipio explícito (ej. "Salamanca, Soledad") — dejar solo el barrio sin el municipio
generó fallos de geocodificación en la primera versión de este dataset (ver README).

Los nombres de pasajeros son ficticios (solo para la prueba); las coordenadas NO se incluyen
aquí — las calcula la app en vivo contra Nominatim/OpenStreetMap, que es justamente lo que se
va a validar.
"""
import pandas as pd

rows = [
    # Barranquilla
    {"identificador": "2001", "nombre": "Laura Martínez", "direccion": "Calle 72 #43-15", "barrio": "El Prado, Barranquilla", "turno": "mañana"},
    {"identificador": "2002", "nombre": "Andrés Cantillo", "direccion": "Carrera 51B #79-30", "barrio": "Alto Prado, Barranquilla", "turno": "mañana"},
    {"identificador": "2003", "nombre": "Valentina Rúa", "direccion": "Calle 84 #50-20", "barrio": "Riomar, Barranquilla", "turno": "mañana"},
    {"identificador": "2004", "nombre": "Jorge Padilla", "direccion": "Carrera 38 #74-10", "barrio": "Boston, Barranquilla", "turno": "tarde"},
    {"identificador": "2005", "nombre": "Camila Herrera", "direccion": "Calle 45 #20-35", "barrio": "Ciudad Jardín, Barranquilla", "turno": "mañana"},
    {"identificador": "2006", "nombre": "Sebastián Orozco", "direccion": "Carrera 8 #30-12", "barrio": "Rebolo, Barranquilla", "turno": "tarde"},
    {"identificador": "2007", "nombre": "Daniela Barrios", "direccion": "Calle 30 #15-40", "barrio": "Simón Bolívar, Barranquilla", "turno": "mañana"},
    {"identificador": "2008", "nombre": "Kevin Salcedo", "direccion": "Carrera 46 #79-50", "barrio": "Villa Country, Barranquilla", "turno": "tarde"},
    {"identificador": "2009", "nombre": "Paola De la Hoz", "direccion": "Calle 74 #55-60", "barrio": "El Golf, Barranquilla", "turno": "mañana"},
    {"identificador": "2010", "nombre": "Ricardo Fontalvo", "direccion": "Carrera 20 #25-18", "barrio": "La Concepción, Barranquilla", "turno": "tarde"},
    # Soledad
    {"identificador": "2011", "nombre": "Ana Julia Consuegra", "direccion": "Calle 30 #22-18", "barrio": "Salamanca, Soledad", "turno": "mañana"},
    {"identificador": "2012", "nombre": "Miguel Meza", "direccion": "Carrera 6B #48-28", "barrio": "Costa Hermosa, Soledad", "turno": "mañana"},
    {"identificador": "2013", "nombre": "Natalia Pacheco", "direccion": "Calle 26 #17D-23", "barrio": "Boulevard Sol Real, Soledad", "turno": "tarde"},
    {"identificador": "2014", "nombre": "Julián Vega", "direccion": "Carrera 13 #19-45", "barrio": "El Hipódromo, Soledad", "turno": "mañana"},
    {"identificador": "2015", "nombre": "Estefanía Polo", "direccion": "Calle 19 #12-30", "barrio": "Soledad 2000, Soledad", "turno": "tarde"},
    # Malambo
    {"identificador": "2016", "nombre": "Cristian Movilla", "direccion": "Carrera 21 #15-40", "barrio": "Las Flores, Malambo", "turno": "mañana"},
    {"identificador": "2017", "nombre": "Luisa Iguarán", "direccion": "Calle 10 #8-22", "barrio": "Malambo", "turno": "tarde"},
    # Puerto Colombia
    {"identificador": "2018", "nombre": "Fabián Charris", "direccion": "Calle 3 #5-20", "barrio": "Puerto Colombia", "turno": "mañana"},
    # Galapa
    {"identificador": "2019", "nombre": "Karen Mendoza", "direccion": "Carrera 12 #10-15", "barrio": "Galapa", "turno": "tarde"},
    # Baranoa
    {"identificador": "2020", "nombre": "Oscar Villalba", "direccion": "Calle 18 #14-33", "barrio": "Baranoa", "turno": "mañana"},
]

df = pd.DataFrame(rows)
df.to_excel("data/samples/pasajeros_prueba_20.xlsx", index=False)
print(f"Archivo generado: data/samples/pasajeros_prueba_20.xlsx ({len(df)} filas)")
