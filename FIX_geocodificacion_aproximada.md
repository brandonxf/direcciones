# Fix: coordenadas duplicadas por matches demasiado genéricos de Nominatim

## Problema observado
Varios pasajeros con direcciones distintas (barrios mal escritos: "cntry club",
"altos limn", direcciones vagas como "cerca al parque") recibían **exactamente
las mismas coordenadas** y se reportaban como "geocodificados con éxito", sin
ninguna advertencia visual.

## Causa raíz
1. `src/geocoding/service.py` ya reintentaba con precisión decreciente
   (dirección completa -> sin número de placa -> solo barrio/municipio) y sí
   guardaba una nota (`nota_precision`) cuando el resultado era aproximado.
2. Pero Nominatim, al no reconocer un barrio mal escrito, a veces ignoraba ese
   token y devolvía el centroide de "Barranquilla, Atlántico" completo — un
   resultado técnicamente válido pero inútil para ubicar a un pasajero
   específico.
3. El frontend (`index.html`) nunca leía `nota_precision`: pintaba de verde
   cualquier resultado con coordenadas, sin distinguir un match exacto de un
   centroide de ciudad reciclado entre múltiples pasajeros.

## Cambios realizados

### `src/geocoding/nominatim_client.py`
- Se agrega `addressdetails=1` a la consulta.
- Se define `CAMPOS_GRANULARIDAD_MINIMA` (road, suburb, neighbourhood,
  house_number, etc.). Si el resultado de Nominatim no incluye **ninguno** de
  esos campos —es decir, solo matcheó ciudad/departamento/país— se descarta y
  se trata como "no encontrada".
- Efecto: esas direcciones ahora caen honestamente en **Gestión de
  Excepciones (RF-09)** para revisión manual, en vez de producir un punto
  falso y duplicado en el mapa. Los matches legítimos a nivel de barrio (que
  sí tienen valor para ubicar aproximadamente a alguien) se siguen aceptando
  igual que antes.

### `src/web/templates/base.html`
- Se agregan variables CSS `--warning-bg`, `--warning-text`,
  `--warning-border` y estilos `.prog-badge` / `.prog-nota` para el nuevo
  estado "Aproximado".

### `src/web/templates/index.html`
- `appendRow()` ahora revisa `d.nota_precision`. Si existe, la fila se pinta
  en amarillo, se agrega una etiqueta "APROXIMADO" y se muestra el texto de
  la nota debajo de la dirección — en vez de mostrarse igual que un match
  exacto (verde).

### `src/web/templates/resultado.html`
- La tabla final de la ruta calculada también resalta en amarillo las
  paradas con `nota_precision` y muestra la etiqueta/nota correspondiente,
  para que quede visible incluso después de descargar/revisar la ruta ya
  generada.

## Cómo aplicar
Copia estos 4 archivos sobre las rutas equivalentes de tu proyecto,
respetando la misma estructura de carpetas (`src/geocoding/...`,
`src/web/templates/...`). No se tocó ningún otro archivo, ni `.env`, base de
datos ni datos de prueba.

## Cómo verificar
1. Vuelve a correr el mismo archivo de prueba con barrios mal escritos.
2. Las direcciones que antes "colapsaban" al centro de Barranquilla ahora
   deberían aparecer en rojo ("Sin ubicación") en el listado de excepciones,
   no en verde con coordenadas repetidas.
3. Si alguna dirección sí logra un match legítimo a nivel de barrio (no de
   ciudad completa), debería verse en **amarillo** con la etiqueta
   "Aproximado" y el texto explicativo, no confundida con un match exacto.
