import pandas as pd
df = pd.read_excel('data/uploads/Pasajeros_Prueba_Barranquilla_1.xlsx', dtype=str)
print('COLUMNAS:', list(df.columns))
print('TOTAL:', len(df))
for _, r in df.iterrows():
    name = r.get('nombre') or r.get('nombres') or ''
    addr = r.get('direccion') or r.get('dirección') or ''
    barrio = r.get('barrio') or ''
    print(f'| {name:20} | {addr:50} | barrio={barrio}')
