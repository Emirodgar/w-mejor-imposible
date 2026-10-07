#!/usr/bin/env node
// Actualiza porsche/tendencias.html (resumen + tarjetas de noticias) a partir del
// feed Atom de Google Alerts, usando la API de Gemini para filtrar, traducir,
// clasificar y resumir. Es el equivalente sin supervisión de la skill
// .claude/skills/actualizar-tendencias-rss/SKILL.md (mismos criterios y mismas zonas).
//
// Requiere la variable de entorno GEMINI_API_KEY. Opcionales:
//   GEMINI_MODEL   modelo a usar (por defecto gemini-flash-latest)
//   --dry-run      no escribe ningún archivo, solo muestra lo que haría

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const FEED_URL = 'https://www.google.es/alerts/feeds/05845247816632936990/7384118912035573051';
const TENDENCIAS_PATH = path.join(ROOT, 'porsche', 'tendencias.html');
const SEEN_PATH = path.join(ROOT, '.claude', 'state', 'tendencias-rss-seen.json');
const SITEMAP_PATH = path.join(ROOT, 'sitemap.xml');
const SITEMAP_LOC = 'https://mejorimposible.es/porsche/tendencias';

const MODEL = process.env.GEMINI_MODEL || 'gemini-flash-latest';
const DRY_RUN = process.argv.includes('--dry-run');

const MAX_NEW = 6;          // noticias nuevas por pasada
const MAX_CARDS = 30;       // tarjetas totales en la página
const MAX_SEEN = 300;       // ids recordados en el estado
const THUMB_POSITIONS = new Set([1, 2, 3, 7, 8, 9]); // posiciones (1-based) con miniatura
const CATEGORIES = ['Lanzamientos', 'Análisis', 'Modelos', 'Guías'];
const MONTHS = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto',
    'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];

const TENDENCIAS_IMAGES = [
    'circuito.jfif', 'competicion.jfif', 'concesionario.png', 'deportivo.png',
    'descapotable-amarillo.jfif', 'fabrica.jfif', 'interior.png', 'motor.png', 'noche.jfif',
    'viaje-911.jfif', 'viaje-taycan.jfif', 'cayenne-electrico.jfif', 'porsche-clasico.jfif',
    'racing-competicion.jfif', 'indianapolis-competicion.jpg'
];
const MODELO_IMAGES = [
    '911.jfif', '9112.jfif', '9113.jfif', '718.jfif', '7182.jfif', '7183.jfif',
    'cayenne.jfif', 'cayenne2.jfif', 'cayenne3.jfif', 'macan.jfif', 'macan2.jfif', 'macan3.jfif',
    'panamera.jfif', 'panamera2.jfif', 'panamera3.jfif', 'taycan.jfif', 'taycan2.jfif', 'taycan3.jfif'
];
const IMAGE_CATALOG = [
    ...TENDENCIAS_IMAGES.map(f => `/img/tendencias/${f}`),
    ...MODELO_IMAGES.map(f => `/img/modelo/${f}`)
];
const IMAGE_DESCRIPTIONS = `
/img/tendencias/circuito.jfif — curva de circuito vista desde un coche en marcha
/img/tendencias/competicion.jfif — 911 GT3 RS verde en pista mojada
/img/tendencias/concesionario.png — showroom con varios Porsche
/img/tendencias/deportivo.png — 911 GT3 plateado en puerto de montaña
/img/tendencias/descapotable-amarillo.jfif — 718 Boxster amarillo en carretera costera
/img/tendencias/fabrica.jfif — línea de montaje / fábrica
/img/tendencias/interior.png — volante y cuadro de instrumentos
/img/tendencias/motor.png — motor en un taller
/img/tendencias/noche.jfif — Panamera de noche en ciudad
/img/tendencias/viaje-911.jfif — 911 azul en carretera de montaña
/img/tendencias/viaje-taycan.jfif — Taycan negro en autopista al atardecer
/img/tendencias/cayenne-electrico.jfif — tres Cayenne Electric en fila
/img/tendencias/porsche-clasico.jfif — dos 550 Spyder plateados clásicos
/img/tendencias/racing-competicion.jfif — 911 GT3 Cup rosa en boxes
/img/tendencias/indianapolis-competicion.jpg — 963 LMDh en pista
/img/modelo/911(.jfif|2|3) 718 cayenne macan panamera taycan — fotos de estudio del modelo (3 variantes cada uno: nombre.jfif, nombre2.jfif, nombre3.jfif)`.trim();

// ---------- utilidades de texto / feed (mismas que actualiza-ultima-hora.js) ----------

function decodeEntities(str) {
    return str
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'")
        .replace(/&nbsp;/g, ' ')
        .replace(/&amp;/g, '&');
}

function stripTags(str) {
    return str.replace(/<[^>]*>/g, '').trim();
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function extractRealUrl(googleUrl) {
    try {
        const real = new URL(googleUrl).searchParams.get('url');
        return real || googleUrl;
    } catch {
        return googleUrl;
    }
}

function parseEntries(xml) {
    const entries = [];
    for (const block of xml.match(/<entry>[\s\S]*?<\/entry>/g) || []) {
        const idMatch = block.match(/<id>([\s\S]*?)<\/id>/);
        const titleMatch = block.match(/<title[^>]*>([\s\S]*?)<\/title>/);
        const linkMatch = block.match(/<link href="([^"]*)"/);
        const publishedMatch = block.match(/<published>([\s\S]*?)<\/published>/);
        const contentMatch = block.match(/<content[^>]*>([\s\S]*?)<\/content>/);
        if (!idMatch || !titleMatch || !linkMatch) continue;

        const rawTitle = decodeEntities(stripTags(decodeEntities(titleMatch[1])));
        let title = rawTitle;
        let source = '';
        const sepIdx = rawTitle.lastIndexOf(' - ');
        if (sepIdx > -1) {
            title = rawTitle.slice(0, sepIdx).trim();
            source = rawTitle.slice(sepIdx + 3).trim();
        }

        entries.push({
            id: idMatch[1].trim(),
            title,
            source,
            snippet: contentMatch ? decodeEntities(stripTags(decodeEntities(contentMatch[1]))) : '',
            url: extractRealUrl(decodeEntities(linkMatch[1])),
            published: publishedMatch ? publishedMatch[1] : null
        });
    }
    return entries;
}

function formatDate(iso) {
    const d = iso ? new Date(iso) : new Date();
    const date = Number.isNaN(d.getTime()) ? new Date() : d;
    const parts = new Intl.DateTimeFormat('es-ES', {
        timeZone: 'Europe/Madrid', day: 'numeric', month: 'numeric', year: 'numeric'
    }).formatToParts(date);
    const get = type => parts.find(p => p.type === type).value;
    return `${get('day')} de ${MONTHS[Number(get('month')) - 1]}, ${get('year')}`;
}

// ---------- estado y sitemap ----------

function loadSeen() {
    try {
        const data = JSON.parse(fs.readFileSync(SEEN_PATH, 'utf8'));
        return Array.isArray(data) ? data : [];
    } catch {
        return [];
    }
}

function updateSitemapLastmod(sitemap, loc, isoDate) {
    const locEscaped = loc.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const blockRe = new RegExp(`(<url>\\s*<loc>${locEscaped}</loc>)([\\s\\S]*?)(</url>)`);
    if (!blockRe.test(sitemap)) return sitemap;
    return sitemap.replace(blockRe, (match, open, middle, close) => {
        const cleanedMiddle = middle.replace(/\s*<lastmod>[\s\S]*?<\/lastmod>/, '');
        return `${open}\n    <lastmod>${isoDate}</lastmod>${cleanedMiddle}${close}`;
    });
}

// ---------- Gemini ----------

const EDITORIAL_PROMPT = `Eres el editor de mejorimposible.es, una web en español para gente que se informa antes de comprar un Porsche. Recibes las entradas nuevas de un feed de Google Alerts sobre "Porsche" y debes elegir y redactar las noticias de la página de tendencias.

CRITERIO EDITORIAL
Quédate solo con noticias que aporten valor real a alguien que se informa para comprar un Porsche: lanzamientos y novedades de producto, cambios de gama o de precios, análisis o comparativas, movimientos de mercado o de la marca, tecnología, tendencias de compra o de segunda mano.
Descarta: cotilleos de famosos o influencers comprando o recibiendo un Porsche, resultados o crónicas de motorsport que solo mencionan "Porsche" de pasada, contenido de foros o redes de baja calidad, vídeos sin sustancia más allá del titular, anuncios/inauguraciones/eventos locales de concesionarios o centros Porsche concretos, clasificados de coches de segunda mano individuales, sucesos o anécdotas sin relación con la compra, y cualquier entrada duplicada o casi idéntica a otra que ya hayas elegido. Es normal descartar la mayoría de las entradas. Si ninguna tiene valor real, devuelve "items" vacío; no rellenes.
Elige como máximo ${MAX_NEW} noticias, las más relevantes.

REDACCIÓN (siempre en español, aunque la fuente esté en otro idioma)
- headline: titular corto y claro, en tu propio estilo.
- excerpt: 1-2 frases con lo esencial, sin traducción literal palabra por palabra. Basa el contenido SOLO en el titular y el fragmento recibidos; no inventes cifras, nombres ni detalles que no aparezcan.
- Tono directo e informativo, sin relleno ni superlativos vacíos.
- shortTitle: 2-5 palabras para una lista de destacados. note: una frase corta que amplía el shortTitle.
- category: exactamente una de ${CATEGORIES.join(', ')}. Lanzamientos = producto nuevo y anuncios oficiales; Análisis = opinión, comparativas, mercado, estrategia de marca; Modelos = contenido centrado en un modelo concreto; Guías = consejos de compra o de uso. Si dudas, Análisis.
- image: la ruta de la imagen del catálogo que mejor encaje con la noticia (si ninguna encaja de verdad, la menos mala). Catálogo:
${IMAGE_DESCRIPTIONS}
- id: copia literal el id de la entrada elegida.

RESUMEN
"summary" es un párrafo de 2-3 frases que sintetiza lo más destacado de las noticias elegidas, en español. Si no eliges ninguna, cadena vacía.`;

const RESPONSE_SCHEMA = {
    type: 'OBJECT',
    properties: {
        items: {
            type: 'ARRAY',
            items: {
                type: 'OBJECT',
                properties: {
                    id: { type: 'STRING' },
                    headline: { type: 'STRING' },
                    excerpt: { type: 'STRING' },
                    category: { type: 'STRING', enum: CATEGORIES },
                    shortTitle: { type: 'STRING' },
                    note: { type: 'STRING' },
                    image: { type: 'STRING', enum: IMAGE_CATALOG }
                },
                required: ['id', 'headline', 'excerpt', 'category', 'shortTitle', 'note', 'image']
            }
        },
        summary: { type: 'STRING' }
    },
    required: ['items', 'summary']
};

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function callGemini(candidates) {
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) throw new Error('Falta la variable de entorno GEMINI_API_KEY');

    const entriesText = candidates.map(c =>
        `ID: ${c.id}\nTitular: ${c.title}\nFuente: ${c.source || 'desconocida'}\nFecha: ${c.published || 'desconocida'}\nFragmento: ${c.snippet}`
    ).join('\n---\n');

    const body = {
        systemInstruction: { parts: [{ text: EDITORIAL_PROMPT }] },
        contents: [{ role: 'user', parts: [{ text: `Entradas nuevas del feed:\n\n${entriesText}` }] }],
        generationConfig: {
            temperature: 0.3,
            responseMimeType: 'application/json',
            responseSchema: RESPONSE_SCHEMA
        }
    };

    const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(MODEL)}:generateContent`;
    const maxAttempts = 4;
    let lastError;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            // La clave va en cabecera (no en la URL) para que no aparezca en logs.
            const res = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'x-goog-api-key': apiKey },
                body: JSON.stringify(body)
            });
            if (res.status === 429 || res.status >= 500) {
                throw new Error(`Gemini respondió HTTP ${res.status}: ${(await res.text()).slice(0, 300)}`);
            }
            if (!res.ok) {
                // Errores 4xx (clave inválida, modelo inexistente...) no se reintentan.
                const err = new Error(`Gemini respondió HTTP ${res.status}: ${(await res.text()).slice(0, 500)}`);
                err.fatal = true;
                throw err;
            }
            const data = await res.json();
            const candidate = data.candidates && data.candidates[0];
            const text = candidate && candidate.content && candidate.content.parts
                && candidate.content.parts.map(p => p.text || '').join('');
            if (!text) {
                const reason = (data.promptFeedback && data.promptFeedback.blockReason)
                    || (candidate && candidate.finishReason) || 'respuesta vacía';
                throw new Error(`Gemini no devolvió contenido (${reason})`);
            }
            return JSON.parse(text);
        } catch (err) {
            lastError = err;
            if (err.fatal || attempt === maxAttempts) break;
            const wait = 5000 * attempt;
            console.warn(`Intento ${attempt} fallido (${err.message}). Reintentando en ${wait / 1000}s...`);
            await sleep(wait);
        }
    }
    throw lastError;
}

// ---------- HTML ----------

function replaceBetween(html, startMarker, endMarker, build) {
    const start = html.indexOf(startMarker);
    const end = html.indexOf(endMarker);
    if (start === -1 || end === -1 || end < start) {
        throw new Error(`No se encontraron los marcadores ${startMarker} / ${endMarker} en tendencias.html`);
    }
    const inner = html.slice(start + startMarker.length, end);
    return html.slice(0, start + startMarker.length) + build(inner) + html.slice(end);
}

function buildSummaryHtml(summary, items) {
    const highlights = items.slice(0, 5).map(it =>
        `                    <li><a href="${escapeHtml(it.url)}" target="_blank" rel="noopener">${escapeHtml(it.shortTitle)}</a> — ${escapeHtml(it.note)}</li>`
    ).join('\n');
    return `
            <div class="weekly-summary">
                <span class="eyebrow">Resumen de la semana</span>
                <h2>Lo más destacado de esta semana en el mundo Porsche</h2>
                <p>${escapeHtml(summary)}</p>
                <ul>
${highlights}
                </ul>
            </div>
            `;
}

function buildCardHtml(it) {
    return `<div class="news-card" data-category="${it.category}">
                <div class="source">${escapeHtml(it.source)}</div>
                <h3>${escapeHtml(it.headline)}</h3>
                <p class="excerpt">${escapeHtml(it.excerpt)}</p>
                <div class="meta">
                    <span>${formatDate(it.published)}</span>
                    <a href="${escapeHtml(it.url)}" target="_blank" rel="noopener" class="read-more-link">Leer más →</a>
                </div>
                </div>`;
}

const CARD_RE = /<div class="news-card"[\s\S]*?<div class="meta">[\s\S]*?<\/div>\s*<\/div>/g;
const THUMB_RE = /\s*<div class="news-thumb">[\s\S]*?<\/div>/;
const THUMB_SRC_RE = /<div class="news-thumb"><img src="([^"]+)"/;

// Impone el patrón fijo de miniaturas: solo las posiciones 1,2,3,7,8,9 llevan imagen,
// y nunca se repite la misma foto entre las tarjetas con imagen.
function enforceThumbs(cards, preferredImages) {
    const used = new Set();
    // Primero reservamos las fotos que ya se quedan en su sitio.
    cards.forEach((card, i) => {
        if (THUMB_POSITIONS.has(i + 1)) {
            const m = card.match(THUMB_SRC_RE);
            if (m && !used.has(m[1])) used.add(m[1]);
        }
    });
    const seenInPass = new Set();
    return cards.map((card, i) => {
        const pos = i + 1;
        const has = THUMB_SRC_RE.test(card);
        if (!THUMB_POSITIONS.has(pos)) {
            return has ? card.replace(THUMB_RE, '') : card;
        }
        if (has) {
            const src = card.match(THUMB_SRC_RE)[1];
            if (!seenInPass.has(src)) {
                seenInPass.add(src);
                return card;
            }
            card = card.replace(THUMB_RE, ''); // foto repetida: se sustituye
        }
        let img = preferredImages.get(i);
        if (!img || used.has(img) || seenInPass.has(img) || !IMAGE_CATALOG.includes(img)) {
            const category = (card.match(/data-category="([^"]*)"/) || [])[1];
            const pool = category === 'Modelos'
                ? [...IMAGE_CATALOG.filter(f => f.startsWith('/img/modelo/')), ...IMAGE_CATALOG]
                : IMAGE_CATALOG;
            img = pool.find(f => !used.has(f) && !seenInPass.has(f)) || IMAGE_CATALOG[0];
        }
        used.add(img);
        seenInPass.add(img);
        const thumb = `\n                <div class="news-thumb"><img src="${img}" alt="" loading="lazy"></div>`;
        return card.replace(/^(<div class="news-card"[^>]*>)/, `$1${thumb}`);
    });
}

// ---------- main ----------

async function main() {
    const res = await fetch(FEED_URL);
    if (!res.ok) throw new Error(`No se pudo descargar el feed (HTTP ${res.status})`);
    const entries = parseEntries(await res.text());
    if (entries.length === 0) {
        throw new Error('El feed no contiene entradas legibles; puede haber cambiado de formato. No se modifica la página.');
    }

    const seen = loadSeen();
    const seenSet = new Set(seen);
    const candidates = entries.filter(e => !seenSet.has(e.id));
    console.log(`Feed: ${entries.length} entradas, ${candidates.length} sin publicar.`);
    if (candidates.length === 0) {
        console.log('No hay entradas nuevas; no se modifica la página.');
        return;
    }

    const result = await callGemini(candidates);

    // Validamos contra el feed: URL, fecha y fuente salen siempre del feed, nunca del modelo.
    const byId = new Map(candidates.map(c => [c.id, c]));
    const chosen = [];
    const usedIds = new Set();
    for (const raw of (result.items || [])) {
        const src = byId.get(raw.id);
        if (!src || usedIds.has(raw.id)) continue;
        if (!CATEGORIES.includes(raw.category)) raw.category = 'Análisis';
        if (![raw.headline, raw.excerpt, raw.shortTitle, raw.note].every(v => typeof v === 'string' && v.trim())) continue;
        usedIds.add(raw.id);
        chosen.push({
            id: src.id,
            url: src.url,
            published: src.published,
            source: src.source || (() => { try { return new URL(src.url).hostname.replace(/^www\./, ''); } catch { return ''; } })(),
            headline: raw.headline.trim(),
            excerpt: raw.excerpt.trim(),
            category: raw.category,
            shortTitle: raw.shortTitle.trim(),
            note: raw.note.trim(),
            image: raw.image
        });
        if (chosen.length === MAX_NEW) break;
    }

    if (chosen.length === 0 || !result.summary || !result.summary.trim()) {
        console.log('Ninguna noticia con valor real esta vez; no se modifica la página.');
        return;
    }
    console.log(`Gemini (${MODEL}) eligió ${chosen.length} noticias:`);
    chosen.forEach(c => console.log(` - [${c.category}] ${c.headline}`));

    // Más nuevas arriba: ordenamos por fecha de publicación descendente.
    chosen.sort((a, b) => new Date(b.published || 0) - new Date(a.published || 0));

    let html = fs.readFileSync(TENDENCIAS_PATH, 'utf8');

    html = replaceBetween(html, '<!-- RSS-SUMMARY:START -->', '<!-- RSS-SUMMARY:END -->',
        () => buildSummaryHtml(result.summary.trim(), chosen));

    html = replaceBetween(html, '<!-- RSS-NEWS-CARDS:START -->', '<!-- RSS-NEWS-CARDS:END -->', inner => {
        const existing = inner.match(CARD_RE) || [];
        const newCards = chosen.map(buildCardHtml);
        const all = [...newCards, ...existing].slice(0, MAX_CARDS);
        const preferred = new Map();
        chosen.forEach((c, i) => { if (i < all.length) preferred.set(i, c.image); });
        const fixed = enforceThumbs(all, preferred);
        return '\n                ' + fixed.join('\n                ') + '\n                ';
    });

    const isoDate = new Date().toISOString().slice(0, 10);
    const sitemap = updateSitemapLastmod(fs.readFileSync(SITEMAP_PATH, 'utf8'), SITEMAP_LOC, isoDate);

    const newSeen = [...seen, ...chosen.map(c => c.id)].slice(-MAX_SEEN);

    if (DRY_RUN) {
        console.log('--dry-run: no se escribe ningún archivo.');
        return;
    }
    fs.writeFileSync(TENDENCIAS_PATH, html, 'utf8');
    fs.writeFileSync(SITEMAP_PATH, sitemap, 'utf8');
    fs.mkdirSync(path.dirname(SEEN_PATH), { recursive: true });
    fs.writeFileSync(SEEN_PATH, JSON.stringify(newSeen, null, 2) + '\n', 'utf8');
    console.log('Página, sitemap y estado actualizados.');
}

main().catch(err => {
    console.error(err.message);
    process.exit(1);
});
