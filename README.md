# Sistema de Geocodificación y Optimización de Rutas de Transporte — Atlántico, Colombia

**Uso principal de la aplicación**: subir un Excel de pasajeros y obtener otro Excel con la
latitud/longitud real de cada dirección (nunca inventadas — si una dirección no se puede
ubicar, queda marcada como excepción para revisión manual, no con coordenadas falsas).

Implementación basada en `Documento_Tecnico_Sistema_Optimizacion_Rutas.docx.pdf`, con 3 de las
4 fases del flujo operativo activas por defecto (la 4ª, cálculo de rutas, queda disponible
como función secundaria):

1. **Ingesta** (`src/ingestion`) — carga y valida el Excel de pasajeros (RF-01 a RF-03).
2. **Normalización con IA** (`src/ai_normalization`) — corrige el formato de cada dirección vía
   NVIDIA NIM (API compatible con OpenAI), sin tocar sus coordenadas (RF-04 a RF-06).
3. **Geocodificación real** (`src/geocoding`) — obtiene lat/lng reales con Nominatim/OpenStreetMap
   por defecto (RF-07 a RF-10).
4. *(Opcional, vía `/ruta` o `main.py`)* **Ruteo** (`src/routing`) — calcula la secuencia óptima
   de paradas con OSRM (RF-11 a RF-14).

Las excepciones de geocodificación se gestionan en `src/exceptions` (sección 10) y el historial de
rutas (cuando se usa el cálculo de ruta) se persiste en SQLite vía `src/persistence` (RF-17).

## Estructura del proyecto

```
src/
  config.py              # variables de entorno y logging
  models/schemas.py      # entidades: Pasajero, RutaOptimizada, ParadaRuta
  ingestion/              # Fase 1
  ai_normalization/       # Fase 2 (NVIDIA NIM)
  geocoding/              # Fase 3
  routing/                # Fase 4
  exceptions/             # gestión de direcciones no geolocalizables
  persistence/            # SQLite: rutas, paradas, excepciones
  pipeline.py             # orquesta las 4 fases
main.py                  # CLI
data/samples/            # generador de Excel de ejemplo
tests/                    # pruebas unitarias (Fase 1, sin dependencias externas)
```

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements-dev.txt
```

Copia `.env.example` a `.env` y completa tus credenciales:

```
NVIDIA_API_KEY=...      # https://build.nvidia.com
GOOGLE_MAPS_API_KEY=...
```

## Uso

Generar un Excel de ejemplo (direcciones del Atlántico):

```bash
python data/samples/generate_sample.py
```

## Interfaz web

```bash
python -m src.web.app
```

Abre http://127.0.0.1:5000 en el navegador.

- **Página principal (`/`)**: sube el Excel de pasajeros, el sistema lo normaliza y geocodifica
  con datos reales, y descargas un Excel (`.xlsx`) con columnas `latitud`/`longitud` (o vacías +
  motivo si no se pudo ubicar). Este es el uso principal de la aplicación.
- **Página secundaria (`/ruta`)**: flujo completo con cálculo de ruta óptima (para cuando se
  necesite ese caso de uso adicional) — tabla de paradas, distancias, tiempos, descarga en CSV
  e historial de rutas (RF-17). No incluye mapa interactivo (RF-15), solo tabla de resultados.

## CLI — solo geocodificación (Excel -> Excel con lat/lon), uso principal

```bash
python geocodificar.py --excel data/samples/pasajeros.xlsx --salida data/output/pasajeros_geocodificados.xlsx
```

## CLI — cálculo de ruta óptima (flujo completo, opcional)

```bash
python main.py --excel data/samples/pasajeros.xlsx \
    --origen "Calle 30 #8-60, Barranquilla, Atlántico" \
    --sentido entrada --turno mañana \
    --export data/output/ruta_entrada.csv
```

## Pruebas

Las pruebas de la Fase 1 (ingesta) no requieren credenciales:

```bash
python -m pytest tests/ -v
```

## Estado verificado (2026-08-27)

Pipeline completo probado **de punta a punta con servicios reales**, sin mocks:

- **Fase 1 (Ingesta)**: probada con pytest, 5/5 pruebas pasan sin credenciales.
- **Fase 2 (IA)**: NVIDIA NIM en vivo. Modelo: `nvidia/nemotron-3-nano-30b-a3b` (es un modelo
  "reasoning" — requiere `extra_body={"chat_template_kwargs": {"thinking": False}}`, ya aplicado
  en `client.py`, o la respuesta viene mezclada con su cadena de pensamiento y puede truncarse
  antes de llegar a la dirección final). Otros modelos del catálogo (mistral-7b-instruct,
  granite-3.0-8b-instruct, mistral-nemo-12b-instruct) no están habilitados para esta cuenta (404).
- **Fase 3 (Geocodificación)**: por defecto usa **Nominatim** (OpenStreetMap) — gratis, sin key,
  sin tarjeta. Probado en vivo, geocodificó correctamente direcciones de Bogotá.
- **Fase 4 (Ruteo)**: por defecto usa **OSRM** (servidor demo público) — gratis, sin key, sin
  tarjeta. Probado en vivo con el servicio "trip" (equivalente a `optimize_waypoints` de Google),
  calculó una ruta real de 3 paradas con distancias y tiempos.
- **Google Maps**: la API key que compartiste es de demostración, sin facturación habilitada,
  por lo que Geocoding/Directions devuelven `REQUEST_DENIED`. El módulo `google_maps_client.py`
  se conserva como alternativa de pago (mejor precisión/cobertura); actívala poniendo
  `GEOCODING_PROVIDER=google` y `ROUTING_PROVIDER=google` en `.env` una vez tengas facturación
  habilitada en https://console.cloud.google.com/project/_/billing/enable.
- **Ejecución real de ejemplo**: `python main.py --excel data/samples/pasajeros.xlsx --origen
  "Terminal de Transporte, Bogota, Colombia" --sentido entrada --export data/output/ruta_entrada.csv`
  generó una ruta de 3 paradas (51 km, 78 min) y detectó automáticamente 1 excepción de
  geocodificación (dirección sin ciudad), sin detener el resto del flujo — validando RF-09 en vivo.

### Precisión de la geocodificación: el campo `barrio` importa

**Hallazgo real durante pruebas**: para "Calle 26 #17d-23, Soledad, Atlántico" sin barrio,
Nominatim devolvió una coordenada a **2.8 km** de la ubicación real, porque en Soledad existen
al menos 5 calles distintas llamadas "Calle 26" en barrios diferentes (Soluciones Mínimas,
Costa Hermosa, Salamanca, Boulevard Sol Real, El Ferrocarril) y OpenStreetMap no tiene
indexado el número de placa exacto en ninguna — solo la línea completa de cada calle. Sin más
contexto, el sistema no puede saber cuál de las 5 es la correcta.

**Solución aplicada**: se agregó una columna opcional `barrio` (alias: `urbanizacion`, `sector`,
`vereda`, `conjunto`) en el Excel de entrada. Cuando está presente, se incluye en el texto que
recibe la IA de normalización (que la conserva en el resultado, ver regla 6 del prompt en
`ai_normalization/client.py`) y ayuda a Nominatim a elegir la calle correcta. Con el barrio
"Boulevard Sol Real" para el mismo caso, el error bajó de 2.8 km a **133 metros** — dentro de
la misma manzana.

**Recomendación**: siempre que se conozca, incluir el barrio/urbanización en el Excel de
pasajeros. Es la mejora de precisión más significativa y no tiene costo. Para los casos donde
no se pueda conseguir el barrio, la alternativa es Google Maps (de pago, ver sección de
proveedores intercambiables), que suele tener mejor cobertura de numeración exacta.

**Segundo hallazgo**: agregar el barrio junto con el número de placa exacto a veces hace que
Nominatim devuelva "sin resultados" en vez de una coincidencia aproximada — la combinación
exacta (calle + número + barrio) no siempre está indexada, aunque la calle y el barrio sí
existan por separado. Se implementó una **cascada de reintentos** en `src/geocoding/service.py`:

1. Intenta la dirección completa (calle + número + barrio + municipio) — máxima precisión.
2. Si falla, reintenta sin el número de placa (calle + barrio + municipio) — precisión a
   nivel de calle/barrio.
3. Si falla, reintenta solo con barrio + municipio — precisión a nivel de sector.

Cuando el resultado proviene del paso 2 o 3, la fila queda marcada con `nota_precision`
explicando que es aproximado (visible en el Excel exportado y como etiqueta "aproximado" en la
interfaz web) — nunca se presenta un resultado aproximado como si fuera exacto.

**Validado con un dataset de prueba de 20 direcciones reales** de 6 municipios del Atlántico
(Barranquilla, Soledad, Malambo, Puerto Colombia, Galapa, Baranoa): la tasa de éxito subió de
50% a **95%** (19/20) con esta cascada; el único caso fallido correspondía a un barrio que no
existe en OpenStreetMap con ese nombre — el sistema lo dejó honestamente como excepción (RF-09)
en vez de forzar una coincidencia incorrecta. Generador: `data/samples/generate_test_20.py`.

**Nota de honestidad**: incluso una coincidencia "exacta" (paso 1) puede corresponder a la
línea completa de la calle y no al predio específico, si Nominatim no tiene indexado ningún
número de placa en esa vía — la ausencia de un fallback no es una garantía absoluta de
precisión a nivel de predio. Por eso cada fila del resultado incluye el botón "Ver en Google
Maps": se recomienda verificar visualmente los casos críticos antes de operar con ellos.

### LocationIQ: probado y descartado como proveedor por defecto

Se evaluó LocationIQ (`src/geocoding/locationiq_client.py`, disponible pero **no recomendado**
como proveedor por defecto) contra el mismo dataset de 20 direcciones. Resultado: 20/20
"exitosos" según LocationIQ, sin ninguno marcado como aproximado — pero al comparar contra
Nominatim para las mismas direcciones exactas, se encontraron diferencias de **hasta 44 km**,
con LocationIQ ubicando una dirección de Barranquilla en **Sabanalarga** (municipio distinto) y
otra con 41 km de error, ambas reportadas con total confianza. La causa: LocationIQ hace
interpolación de numeración de placa a nivel nacional que en estos casos ignoró la ciudad
indicada en la consulta.

**Conclusión**: una tasa de éxito más alta no es lo mismo que mayor precisión — LocationIQ
resultó menos confiable que Nominatim + cascada de reintentos para este caso de uso, porque no
señala cuándo su resultado es una interpolación de baja confianza. Se mantiene Nominatim como
proveedor por defecto (`GEOCODING_PROVIDER=nominatim`). El código de LocationIQ queda disponible
por si se quiere usar como verificación cruzada en el futuro, pero no debe activarse sin ese
resguardo adicional.

### Región objetivo: departamento del Atlántico, Colombia

El sistema está configurado para operar en el Atlántico (Barranquilla, Soledad, Malambo,
Puerto Colombia, Galapa, Sabanalarga, etc.):

- La geocodificación (Nominatim) prioriza resultados dentro de un `viewbox` que cubre el
  departamento (`NOMINATIM_VIEWBOX` en `.env`) y se restringe a Colombia (`NOMINATIM_COUNTRYCODES=co`).
- El prompt de IA (Fase 2) sabe que, si una dirección no menciona ciudad, debe asumir
  Barranquilla — pero **nunca** sobreescribe un municipio ya mencionado (ej. no convierte
  "Calle 3, Puerto Colombia" en "Barranquilla, Calle 3... Puerto Colombia").
- Se validó en vivo con 5 direcciones reales de Barranquilla, Soledad, Malambo y Puerto
  Colombia: **100% de éxito en geocodificación** tras la normalización con IA.

**Importante sobre el campo "origen"**: Nominatim (a diferencia de Google) no tiene una base
rica de nombres de lugares/negocios — nombres genéricos como "Terminal de Transporte" no
suelen encontrarse. Usa siempre una **dirección de calle real** (ej. "Calle 30 #8-60,
Barranquilla, Atlántico") o el nombre oficial exacto tal como aparece en OpenStreetMap.

### Límites de los proveedores gratuitos

- **Nominatim**: máx. 1 solicitud/segundo (ya respetado internamente), y su política de uso
  justo no está pensada para volumen alto en producción. Direcciones ambiguas o incompletas
  (sin ciudad/país) tienen más probabilidad de fallar que con Google.
- **OSRM (servidor demo)**: no recomendado para producción con tráfico alto; límite práctico
  de ~50 paradas por solicitud en este proyecto.
- Para producción real a mayor escala, la ruta natural es autohospedar Nominatim/OSRM, o
  cambiar a Google Maps con facturación habilitada (`GEOCODING_PROVIDER=google`,
  `ROUTING_PROVIDER=google`).

## Notas de diseño y límites conocidos

- **Proveedor de IA intercambiable**: `AddressNormalizerClient` (`src/ai_normalization/client.py`) es una
  interfaz abstracta. La implementación por defecto usa NVIDIA NIM; cambiar a OpenAI u otro proveedor
  solo requiere una nueva clase que la implemente (RNF-09, RNF-10).
- **Límite de la Directions API**: el optimizador de rutas (`src/routing/route_optimizer.py`) soporta
  hasta ~23 paradas por solicitud. Para lotes de cientos de pasajeros (RNF-01), el siguiente paso es
  agrupar por zona/vehículo y/o migrar a un solver VRP (Google OR-Tools) o a la API dedicada de
  "Route Optimization" de Google — el módulo está aislado para permitir ese reemplazo sin tocar el resto.
- **Fuera de alcance en esta primera versión** (según sección 3 del documento): seguimiento GPS en
  tiempo real, facturación, y asignación automática de pasajeros con restricciones de capacidad complejas.
- **Interfaz de usuario**: este repositorio implementa solo el motor de procesamiento (backend). La
  visualización en mapa interactivo (RF-15) queda pendiente para una capa de UI futura (web o móvil).
