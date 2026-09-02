---
name: actualizar-valoraciones-concesionarios
description: Actualiza la puntuación de Google, el número de reseñas y un resumen de opiniones (lo más valorado / quejas más comunes) de cada Centro Porsche oficial en mejorimposible.es, tanto en el listado /concesionarios como en cada ficha individual. Requiere navegador (Google Maps en vivo). Úsala solo bajo demanda, cuando el usuario pida explícitamente actualizar valoraciones/reseñas de concesionarios — no está pensada para ejecución desatendida.
---

# Actualizar valoraciones y reseñas de los Centros Porsche

## Contexto

Este repo es el sitio estático de mejorimposible.es (GitHub Pages, rama `main`). Cada centro oficial tiene:
- Una entrada en el array `dealerData` dentro de `concesionarios.html` (campos `rating` y, opcionalmente, `reviewCount`).
- Una ficha individual en `concesionarios/<slug>.html`, con front matter YAML (`rating`, `review_count`, `reviews_positive`, `reviews_negative`, `google_profile_url`, `cover_image`) que alimenta el layout `_layouts/dealer.html`.

Esta skill usa el **navegador** (herramientas `mcp__Claude_Browser__*`) para consultar el perfil de Google Business/Maps real de cada centro y extraer: la puntuación media, el número de reseñas, y una lectura de una muestra de reseñas para resumir qué se valora y de qué se quejan los clientes. No hay API key de Google configurada — todo se hace leyendo la página de Maps como lo haría una persona.

Está pensada para ejecutarse **a mano, cuando el usuario lo pida explícitamente** (p. ej. "actualiza las valoraciones de los concesionarios"). No la ejecutes de forma programada ni la asumas como parte de otra tarea.

## Listado completo de centros (slug, nombre, enlace de Google Maps)

| Slug (`concesionarios/<slug>.html`) | Nombre exacto | Enlace de búsqueda en Google Maps |
| --- | --- | --- |
| centro-porsche-a-coruna | Centro Porsche A Coruña | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+A+Coru%C3%B1a |
| centro-porsche-alicante | Centro Porsche Alicante | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Alicante |
| centro-porsche-asturias | Centro Porsche Asturias | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Asturias |
| centro-porsche-baleares | Centro Porsche Baleares | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Baleares |
| centro-porsche-barcelona | Centro Porsche Barcelona | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Barcelona |
| centro-porsche-bilbao | Centro Porsche Bilbao | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Bilbao |
| centro-porsche-las-palmas | Centro Porsche Canarias (Gran Canaria) | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Canarias+Gran+Canaria |
| centro-porsche-canarias-tenerife | Centro Porsche Canarias (Tenerife) | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Canarias+Tenerife |
| centro-porsche-girona | Centro Porsche Girona | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Girona |
| centro-porsche-granada | Centro de Servicio Porsche Granada | https://www.google.com/maps/search/?api=1&query=Centro+de+Servicio+Porsche+Granada |
| centro-porsche-madrid-norte | Centro Porsche Madrid Norte | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Madrid+Norte |
| centro-porsche-madrid-oeste | Centro Porsche Madrid Oeste | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Madrid+Oeste |
| centro-porsche-malaga | Centro Porsche Málaga | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Malaga |
| centro-porsche-marbella | Centro Porsche Marbella | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Marbella |
| centro-porsche-murcia | Centro Porsche Murcia | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Murcia |
| centro-porsche-pamplona | Centro Porsche Pamplona | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Pamplona |
| centro-porsche-sant-cugat | Centro Porsche Sant Cugat | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Sant+Cugat |
| centro-porsche-santander | Centro Porsche Santander | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Santander |
| centro-porsche-sevilla | Centro Porsche Sevilla | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Sevilla |
| centro-porsche-valencia | Centro Porsche Valencia | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Valencia |
| centro-porsche-valladolid | Centro Porsche Valladolid | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Valladolid |
| centro-porsche-vigo | Centro Porsche Vigo | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Vigo |
| centro-porsche-zaragoza | Centro Porsche Zaragoza | https://www.google.com/maps/search/?api=1&query=Centro+Porsche+Zaragoza |

## Pasos

Repite esto para cada centro de la tabla (puedes trabajar en lotes dentro de la misma ejecución; si uno falla, anótalo y sigue con el resto — no abandones toda la tarea por un fallo puntual):

1. **Abre el enlace de Google Maps** del centro con las herramientas de navegador. Si aparece un diálogo de cookies/consentimiento, acéptalo (botón tipo "Aceptar todo") para poder leer la página.

2. **Localiza la ficha correcta**. La búsqueda suele llevar directamente al panel del negocio si el nombre es específico. Si en vez de eso aparece una lista de varios resultados, elige el que coincida exactamente (o casi) con el "Nombre exacto" de la tabla — nunca elijas un resultado claramente distinto (otra marca, otra ciudad) solo por estar el primero. Si no encuentras una coincidencia razonable, anota ese centro como "no encontrado" y pasa al siguiente; no inventes datos.

3. **Extrae la puntuación media y el número de reseñas** del panel del negocio (normalmente aparecen juntos, ej. "4.3 · 190 opiniones" o "4.3 (190)"). Usa `read_page` (árbol de accesibilidad) o `get_page_text` — suele ser más fiable que la captura visual para estos datos.

4. **Guarda la URL del perfil** (`window.location.href` en ese momento, vía `javascript_tool`): es la URL canónica `https://www.google.com/maps/place/...` a la que redirige la búsqueda. Esta será el enlace de "Ver todas las reseñas en Google".

5. **Extrae la foto de portada del negocio** si hay alguna disponible: con `javascript_tool`, busca en el DOM las imágenes cuyo `src` contenga `googleusercontent.com/gps-cs-s/` (son las fotos del propio negocio; ignora las que contengan `/a/` o `/a-/`, que son avatares de usuarios que han dejado reseña). Coge la primera/principal (suele ser la foto de cabecera del panel) y pide una resolución mayor cambiando el sufijo de tamaño de la URL a `=w1200-h500-k-no` (sustituye el sufijo `=wNNN-hNNN...` que traiga por defecto). Verifica con una petición `fetch` que la URL con el nuevo tamaño responde 200 antes de darla por buena. Si no encuentras ninguna imagen de este tipo, simplemente omite el campo `cover_image` para ese centro — no es obligatorio.

6. **Lee una muestra relevante de reseñas** visibles en el panel (las que carguen por defecto, normalmente 5-10; si hay una sección/pestaña de "Reseñas" o "Opiniones" haz scroll para ver algunas más si es rápido, pero no hace falta leerlas todas). Fíjate en el texto de cada una, no solo en la puntuación de estrellas.

7. **Resume en español** lo que encuentres, con honestidad (no fuerces negativos si casi no los hay, ni ocultes quejas reales):
   - `reviews_positive`: 2-4 puntos cortos sobre lo que los clientes valoran más (ej. trato del personal, rapidez, calidad del servicio de taller, proceso de compra, etc.), como frases hechas a partir de patrones reales de la muestra, no traducciones literales de una sola reseña.
   - `reviews_negative`: 2-4 puntos cortos sobre las quejas más repetidas y su motivo (ej. "tiempos de espera largos en el taller", "dificultad para conseguir cita", "diferencia de trato según el vendedor"). Si la muestra es abrumadoramente positiva y no hay quejas repetidas, usa un único punto honesto como "Sin quejas destacables en la muestra revisada" en vez de inventar problemas.

8. **Actualiza la ficha individual** `concesionarios/<slug>.html`: en el front matter YAML, actualiza `rating:` con el valor numérico (ej. `4.4`), añade o actualiza `review_count:` (número entero), `google_profile_url:` (la URL canónica del paso 4), `cover_image:` (la URL de la foto en tamaño grande del paso 5, si se encontró), y `reviews_positive:` / `reviews_negative:` como listas YAML, por ejemplo:
   ```yaml
   review_count: 190
   google_profile_url: "https://www.google.com/maps/place/..."
   cover_image: "https://lh3.googleusercontent.com/gps-cs-s/AHRPTW.../=w1200-h500-k-no"
   reviews_positive:
     - "Trato cercano y profesional durante todo el proceso de compra."
     - "Buena rapidez en el servicio de taller."
   reviews_negative:
     - "Varios clientes mencionan tiempos de espera largos para conseguir cita en el taller."
   ```
   No toques el resto del front matter (`title`, `dealer_name`, `address`, `phone`, `lat`, `lng`) ni el contenido markdown del cuerpo de la página — **ni siquiera si la dirección o coordenadas que ves en Google no coinciden con las que ya hay en el archivo**. Eso es una discusión aparte (el centro pudo cambiar de dirección, o el dato original podía estar desactualizado) que no corresponde a esta skill; señálalo en el resumen final si lo detectas, pero no lo corrijas tú mismo.

9. **Actualiza `concesionarios.html`**: en el array `dealerData`, localiza la entrada cuyo `detailSlug` coincida con el slug del centro, y actualiza su `rating` y añade/actualiza un campo `reviewCount` (número entero) en ese mismo objeto. No toques ningún otro campo de esa entrada ni la estructura del array.

## Al terminar todos los centros

10. **Publica el cambio**:
   ```
   git add concesionarios.html concesionarios/*.html
   git commit -m "Actualiza valoraciones y reseñas de los Centros Porsche (Google)"
   git push
   ```
   Si `git push` falla, deja el commit local hecho, no lo fuerces, e informa del problema.

11. **Resumen final**: cuando termines, dile al usuario, para cada centro: si se actualizó correctamente (con su nueva puntuación y nº de reseñas), o si no se pudo encontrar/leer su perfil (y por qué). No hace falta repetir el detalle completo de positivos/negativos en el resumen del chat, con confirmar que se escribieron en la ficha basta.

## Notas

- Esta skill depende de poder leer Google Maps en vivo con las herramientas de navegador — solo tiene sentido ejecutarla en una sesión interactiva con esas herramientas disponibles, nunca en un entorno headless sin navegador.
- Sé fiel a lo que ves en la página: no inventes puntuaciones, números de reseñas ni opiniones si no has podido leerlos.
- Si Google muestra el panel en otro idioma o formato distinto al esperado, adapta la lectura pero mantén la salida siempre en español.
- Si el mismo centro ya tiene `reviews_positive`/`reviews_negative` de una ejecución anterior, sustitúyelos enteros por el resumen nuevo (no los acumules ni los mezcles).
- `cover_image` enlaza directamente a una foto alojada en los servidores de Google (`googleusercontent.com`), no se descarga ni se copia al repositorio. Es una imagen pública del propio perfil del negocio, pero esa URL podría dejar de funcionar en el futuro si Google la retira; no es un fallo grave si eso ocurre en algún centro, simplemente la imagen dejaría de mostrarse.
