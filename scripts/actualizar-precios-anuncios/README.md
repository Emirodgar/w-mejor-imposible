# Precios de anuncios (Porsche, España)

Alimenta la sección «Evolución mensual del precio en anuncios» de `porsche/precio-segunda-mano.html`.

- `recoger.py`: recoge los anuncios de coches **usados** en AutoScout24.es (ES, sin dañados) para cada serie de `series.json` y **añade un punto del mes en curso** a `porsche/precios-anuncios.json`. Lo ya guardado no se modifica; si el mes ya existe, se respeta. Antes de escribir comprueba que el histórico previo queda idéntico.
- `series.json`: cada serie = id de `priceData` de la página + modelo de AutoScout24 + rango de años de primera matriculación. Los rangos aproximan las generaciones; Cayman/Boxster usan Boxster solo para el 986 y Cayman en el resto.
- `snapshots/AAAA-MM.jsonl.gz`: instantánea anuncio a anuncio de cada ejecución (acumulativa, se versiona). Permite recalcular otras métricas sin volver a recoger.
- Punto de la serie: `precio` = mediana, `n` = nº de anuncios, y además `media`, `p25`, `p75`. La página avisa de los meses con menos de 5 anuncios.
- La sección de la página se muestra desde el primer punto; con un solo punto enseña el dato y un aviso, y la curva aparece con 2 o más.

Ejecución: workflow `.github/workflows/precios-anuncios.yml` (día 1 de cada mes, 06:15 UTC; también manual). En local: `python scripts/actualizar-precios-anuncios/recoger.py [--solo ID ...] [--dry-run] [--mes AAAA-MM]`.

Cortesía con la fuente: un User-Agent que identifica al bot, 3 s entre peticiones y ~60 peticiones al mes. Revisar los términos de uso de AutoScout24 si se amplía la frecuencia o el volumen. Los precios son de anuncio, no de venta; la mediana mezcla versiones y kilometrajes dentro de cada generación.
