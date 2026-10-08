# Repositorio de datos: análisis de modelos Porsche desde Reddit

Este directorio es la memoria acumulada de la skill `analisis-reddit-modelos`. Su valor está en que **crece con cada actualización y nunca se borra nada**: lo nuevo se incorpora y lo existente se conserva.

## Regla de oro

- **No borrar ni editar ficheros existentes** de `classified/`, `snapshots/`, `scope/`, `threads.json`, `comments-index.jsonl`.
- **Corregir = añadir.** Una re-revisión (por ejemplo, al añadir un modelo nuevo a `models.json`) es un fichero nuevo en `classified/` con numeración mayor, más su `scope/NNN.json`. `score.py` usa el número más alto que trate cada comentario y conserva el resto como historial.
- Si hay que apartar algo claramente erróneo (un resultado de una prueba rota, por ejemplo), se **mueve** a una carpeta de apartados (`snapshots/_pruebas/`, `descartados-rerevision/`); no se elimina.
- Los scripts son solo aditivos: `fetch_threads.py` añade al final de los ficheros y archiva los lotes viejos en lugar de borrarlos; `backfill_dates.py` solo rellena campos que faltan y deja copia previa.

## Qué hay aquí

| Ruta | Contenido | En git |
|---|---|---|
| `threads.json` | Metadatos de cada hilo analizado (título, subreddit, URL, fecha, nº de comentarios) | sí |
| `threads-done.json` | Ids de hilos ya descargados (evita repetirlos) | sí |
| `comments-index.jsonl` | Por comentario: `id`, `thread`, `user` (hash de 10 caracteres), `score`, `created` (fecha UTC). **Sin texto** | sí |
| `comments.jsonl` | Igual que el índice más `parent` y `body`. Es el texto de Reddit | **no** (local) |
| `classified/NNN.json` | Clasificación de cada comentario valorable: modelos, sentimiento, base (`owner`/`driven`/`hearsay`/`none`), aspectos y resumen en español | sí |
| `scope/NNN.json` | Lista de comentarios revisados por cada lote, hayan dado entrada o no. Permite que una re-revisión decida que un comentario "ya no cuenta" sin borrar nada | sí |
| `reviewed.json` | Ids de comentarios ya revisados (no se vuelven a encolar) | sí |
| `snapshots/AAAA-MM-DD_Nhilos.json` | Copia completa del resultado de cada puntuación. De aquí sale `history` en el JSON público y la evolución del ranking | sí |
| `snapshots/_pruebas/` | Snapshots apartados por proceder de pruebas con errores | sí |
| `descartados-rerevision/` | Segundas opiniones y entradas previas reemplazadas por re-revisiones. Útiles para medir la concordancia entre clasificadores | sí (salvo lo que lleve texto) |
| `batches/`, `archivo/` | Lotes de trabajo y copias de seguridad previas a reescrituras con texto de comentarios | **no** (local) |

## Por qué el texto de los comentarios no va a git

El repo se publica en GitHub Pages. Los comentarios son contenido de terceros y no se redistribuyen: en el repo quedan los ids, la clasificación y resúmenes reescritos con enlace al comentario original. Si se quiere un respaldo del texto, que sea fuera del repo público (copia de `comments.jsonl` en un almacenamiento privado).

## Cómo se obtiene un resultado

`scripts/score.py` lee `classified/` en orden numérico, aplica la sustitución por re-revisión, agrega con un voto por usuario y modelo, escribe `porsche/analisis-reddit.json` y deja un snapshot en `snapshots/`.

## Ideas para explotar la acumulación

- Evolución del % positivo y de la muestra por modelo (`history`).
- Opiniones por fecha del comentario (`created` en el índice): ¿mejora o empeora la percepción de un modelo?
- Concordancia entre clasificadores comparando `descartados-rerevision/` con `classified/`.
- Cruce con el histórico de noticias (`porsche/noticias-historico.json`) y menciones de prensa (`porsche/menciones-historico.json`).
