# Vigilancia de eventos de alto standing en España

Cada día, un workflow de GitHub (`.github/workflows/vigilancia-eventos.yml`) lee los RSS, extrae los hechos de cada
artículo con Gemini y **crea la ficha del evento si no existe o la enriquece si ya existe**.

## Flujo

1. `vigilancia.py` recoge los feeds de Google Alerts (secreto `GOOGLE_ALERTS_FEEDS`) y los feeds directos de
   `data/portal/vigilancia/alertas.json`. Las consultas de ese archivo en Google News RSS sirven para el OPML y el informe local.
2. `pipeline.py` descarta lo ya visto (`vistos.json`). **Gemini hace el triaje**: una sola llamada con todos los titulares nuevos
   decide cuáles interesan (si falla, se usa un filtro por palabras clave). Solo de esos se descarga el artículo y se pregunta a Gemini
   si habla de un evento de alto standing en España. El modelo solo puede usar hechos que aparezcan en el texto.
3. Se aplica con reglas deterministas:
   - **Evento nuevo** → ficha en `data/portal/eventos.json` (y página `/eventos/<id>/` en los 6 idiomas).
     Confianza `alta` solo con fuente oficial (`fuentes_oficiales.json` o la web del propio evento); si no, `media`;
     si el texto es ambiguo, `baja` (la ficha existe pero no se publica hasta que se confirme).
   - **Evento existente** → se añade una **novedad** (`novedades[]`) con fecha, texto y fuente. Nada se borra. Las fechas
     solo cambian con fuente oficial y el cambio queda en `historial[]`; si una fuente no oficial da otras fechas,
     se anota como novedad «pendiente de confirmar».
   - **Otra edición** (el evento ya pasó y llegan fechas posteriores) → ficha nueva; la anterior se conserva.
4. Se traduce lo nuevo a en/fr/de/pt/it con Gemini, se reconstruye el portal (`build.py`) y se añade Open Graph.
   Se revierten las páginas que solo cambian en la fecha de hoy.
5. Commit y push solo si hay cambios. El informe del día se guarda como artefacto del workflow (30 días).

## Qué lleva cada ficha (pensada para que la citen las IA)

Cada evento tiene su página `/eventos/<id>/` en los 6 idiomas, con este orden y estas reglas:

- **Respuesta primero**: `resumen` de 1-2 frases (qué es, cuándo, dónde) justo bajo el título; es también la meta description.
- **Datos clave** (`<dl>`): tipo, cuándo (`<time>`), dónde, organizador, edición, horario, entradas, cómo llegar, web oficial y estado.
- **Qué es y en qué consiste**: 3-6 párrafos de una idea y máximo 2 frases.
- **Preguntas frecuentes** visibles, formuladas como las haría una persona a un asistente, con respuestas autosuficientes.
- **Novedades** acumuladas con fecha y fuente, y **fuentes** con enlace. Fecha de actualización visible.
- Datos estructurados: `Event` (organizador, lugar, fechas, sameAs), `FAQPage`, `WebPage` con `dateModified`, `BreadcrumbList`.
- `llms.txt` lista cada evento con su resumen; `sitemap-portal.xml` incluye todas las fichas.

El enriquecimiento (`pipeline.py`, función `enriquecer`) reúne para cada ficha su web oficial, las fuentes ya citadas y los artículos
del día que hablan del evento, y pide a Gemini que redacte la ficha **solo con lo que dicen esas fuentes**. Cada ejecución procesa primero
las fichas que han cambiado hoy y después las que nunca se han enriquecido o llevan más de 30 días (`ENRIQUECER_MAX`, por defecto 6).
Lo nuevo se suma a lo existente: párrafos y preguntas se añaden si no repiten lo anterior; los datos cambian solo con fuente oficial y
lo sustituido queda en `historial`.

Limitación: los enlaces de Google News no llevan al artículo, así que la vigilancia diaria se apoya en los feeds de Google Alerts
(que sí traen la URL real) y en los feeds directos de `alertas.json`.

## Configuración en GitHub (una vez)

Repositorio → Settings → Secrets and variables → Actions → New repository secret:

- `GEMINI_API_KEY`: ya existe (la usa el workflow de tendencias).
- `GOOGLE_ALERTS_FEEDS`: las URL de los feeds de Google Alerts, **una por línea**
  (las mismas que `scripts/vigilancia/google-alerts-feeds.txt`, archivo ignorado por git).

Opcionales (Variables): `GEMINI_MODEL` (por defecto `gemini-flash-latest`).

## Uso en local

```powershell
python scripts/vigilancia/pipeline.py --dry        # lista candidatos sin llamar a Gemini ni escribir
$env:GEMINI_API_KEY = "..."; python scripts/vigilancia/pipeline.py
```

Para ampliar la vigilancia: añadir una entrada a `alertas.json`, o un dominio a `fuentes_oficiales.json`, y
ejecutar `python scripts/vigilancia/vigilancia.py opml terminos` para regenerar el OPML y el listado de Google Alerts.
