# Mi Billetera de Beneficios

Web personal que junta los beneficios de **Banco de Chile, Santander, Falabella (CMR/Débito), Copec Pay y Entel**, los ordena por día y por tarjeta, y los muestra en un mapa según dónde estás. Un pipeline semanal revisa los sitios de cada proveedor y agrega o da de baja beneficios solo.

```
GitHub Actions (lunes y día 1 de cada mes)
  └─ pipeline/run.py
       1. fetch.py     Playwright abre cada sitio (renderiza JS, sigue enlaces de detalle)
       2. extract.py   Gemini (gratis) o Claude convierte el texto en beneficios estructurados (JSON)
       3. models.py    normaliza: id estable, días, categoría, % numérico
       4. merge.py     altas / cambios / ausencias / bajas / vencidos, con resguardos
       5. geocode.py   direcciones -> lat/lng; cadenas -> sucursales (OpenStreetMap, o Google si hay key)
       6. data/beneficios.json + data/cambios/AAAA-MM-DD.md + data/estado.json
  └─ commit al repo  ->  workflow "Publicar sitio"  ->  GitHub Pages
```

## Cómo decide qué agregar y qué quitar

| Situación | Qué pasa |
|---|---|
| Aparece un beneficio nuevo | Se agrega con `primer_visto` = hoy y la etiqueta **Nuevo** por 10 días |
| Vuelve a aparecer | Se actualizan sus campos y queda **verificado** hoy |
| No aparece en una corrida | Suma una ausencia y la web muestra “Confirma en la app” |
| No aparece en 2 corridas sanas seguidas | Se da de baja y pasa a `data/retirados.json` |
| Su `vigencia_hasta` ya pasó | Se da de baja de inmediato |
| El sitio de un proveedor falla, o trae menos del 40% de lo que había | **No se toca nada** de ese proveedor y se reporta |
| Un proveedor falla 2 corridas seguidas | Se abre (o comenta) un issue en GitHub |
| Está en `data/manual.json` | Nunca se da de baja por ausencia (útil para beneficios que el scraper no ve) |

Todas estas reglas están en `pipeline/merge.py` y cubiertas por `tests/test_merge.py`.

Se usa un modelo de lenguaje para extraer en vez de selectores CSS porque los bancos rediseñan sus sitios seguido: mientras el texto del beneficio siga visible, la extracción sigue funcionando. Si cambia una URL, se corrige en `pipeline/sources.yaml`.

## Puesta en marcha (gratis)

Todo funciona sin pagar nada: el mapa es OpenStreetMap, la ubicación de locales usa OpenStreetMap (Nominatim y Overpass) y la extracción usa el plan gratuito de Gemini. Solo necesitas **una key**:

1. **Key de Gemini (gratis, sin tarjeta)**: entra a [aistudio.google.com/apikey](https://aistudio.google.com/apikey) con tu cuenta de Google y toca *Create API key*. Copia la key.
2. **Secreto en GitHub**: en tu repo, *Settings → Secrets and variables → Actions → New repository secret*. Nombre: `GEMINI_API_KEY`, valor: la key.
3. **GitHub Pages**: *Settings → Pages → Source: GitHub Actions*.
4. **Permisos del bot**: *Settings → Actions → General → Workflow permissions → Read and write permissions*.
5. **Primera corrida**: *Actions → Actualizar beneficios → Run workflow*. Al terminar, el resumen muestra el estado de cada proveedor y qué entró o salió. La web queda en `https://TU_USUARIO.github.io/NOMBRE_DEL_REPO/`.

> Los sitios de los bancos no se pudieron probar en vivo al construir esto. Es posible que en la primera corrida algún proveedor falle por URL o bloqueo; los resguardos mantienen sus datos actuales. Revisa el artefacto *paginas-descargadas* de la corrida y ajusta `pipeline/sources.yaml`.

### Opcionales (pagados)

| Secreto | Para qué | Nota |
|---|---|---|
| `GOOGLE_MAPS_KEY` | Usar Google Maps en vez de OpenStreetMap | Google exige una cuenta de facturación con tarjeta, aunque el uso personal quede dentro de la cuota gratuita |
| `GOOGLE_GEOCODING_KEY` | Ubicar direcciones y sucursales con Google | Más preciso que OpenStreetMap para cadenas pequeñas; misma condición de tarjeta |
| `ANTHROPIC_API_KEY` | Extraer con Claude en vez de Gemini | Se usa solo si no hay `GEMINI_API_KEY`, o si defines la variable `BB_EXTRACTOR=anthropic` |

### Límites del plan gratuito

- **Gemini**: el plan gratis limita las solicitudes por minuto y por día; el pipeline espera unos segundos entre llamadas y reintenta si recibe un límite. Una corrida usa del orden de 10 a 20 solicitudes. Google puede usar los datos enviados en el plan gratis para mejorar sus modelos; aquí solo se envía texto público de las páginas de beneficios. El modelo se cambia con la variable `BB_GEMINI_MODEL`.
- **OpenStreetMap**: Nominatim permite como máximo 1 consulta por segundo y el pipeline lo respeta; todo queda en caché en `data/geocache.json`. Los locales de cadenas solo aparecen si están registrados en OpenStreetMap.
- **Mapa**: usa los mapas base de CARTO sobre OpenStreetMap, gratuitos para uso personal con atribución.

## Uso local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && python -m playwright install chromium
python -m pytest -q                                  # tests del pipeline

export GEMINI_API_KEY=...
python -m pipeline.run --solo fal --dry-run          # prueba un proveedor sin escribir
python -m pipeline.run                               # corrida completa
python -m pipeline.run --desde-cache                 # re-extrae sin volver a descargar

python scripts/build_site.py && python -m http.server -d _site 8000
# abre http://localhost:8000

python scripts/build_artifact.py                     # versión de una sola página, sin Google Maps
```

## La web

- **Semana**: cada día muestra cuántos beneficios tienes y una barra apilada por proveedor.
- **Tarjetas**: activa o desactiva proveedores (se recuerda en tu navegador). Filtro por rubro y búsqueda.
- **Ubicación**: “Usar mi ubicación” pide el GPS del navegador (requiere HTTPS, que GitHub Pages da). Si no quieres compartirla, elige tu comuna o toca “Estoy aquí” y marca el mapa.
- **Cercanía**: con ubicación activa, la lista se ordena por distancia al local más cercano de cada beneficio y cada uno tiene “Cómo llegar” en Google Maps.
- El mapa es OpenStreetMap por defecto; con `GOOGLE_MAPS_KEY` usa Google Maps. Si ninguno carga, queda un mapa simple con los límites comunales de Santiago.

## Archivos

```
data/beneficios.json   datos publicados (lo lee la web)
data/manual.json       beneficios que mantienes a mano
data/retirados.json    historial de bajas con motivo
data/cambios/          un reporte por corrida
data/estado.json       salud de cada proveedor
data/geocache.json     caché de geocoding y sucursales
pipeline/sources.yaml  URLs y umbrales por proveedor
web/                   index.html, styles.css, app.js, map-leaflet.js, map-google.js, map-svg.js, comunas.json, vendor/leaflet
```

Límites comunales: datos BCN vía el paquete `react-chile-map` (MIT). Mapa: Leaflet (BSD-2), OpenStreetMap y CARTO.
