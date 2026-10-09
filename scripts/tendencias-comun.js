// Lógica compartida de la sección /porsche/tendencias: catálogo de modelos y enlaces
// internos, render de tarjetas, semanas ISO y generación de las páginas semanales.
// La usan scripts/actualiza-tendencias-gemini.js (ejecución automática) y cualquier
// backfill manual.
//
// Fuente de verdad acumulativa (nunca se borra, solo se añade):
//   porsche/tendencias-editorial.json   noticias curadas, con modelos, impacto y enlaces
//   porsche/tendencias-semanas.json     resumen y destacados por semana ISO
// Derivadas (se regeneran a partir de las dos anteriores):
//   porsche/tendencias/semana-AAAA-WW.html

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const EDITORIAL_PATH = path.join(ROOT, 'porsche', 'tendencias-editorial.json');
const SEMANAS_PATH = path.join(ROOT, 'porsche', 'tendencias-semanas.json');
const SEMANAS_DIR = path.join(ROOT, 'porsche', 'tendencias');
const SITE = 'https://mejorimposible.es';

const MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
    'septiembre', 'octubre', 'noviembre', 'diciembre'];

// Etiquetas de modelo (enum del schema de Gemini). 718 incluye Boxster y Cayman.
const MODELS = {
    '911': { label: '911', sheet: '/porsche/modelos/911' },
    '718': { label: '718 (Boxster/Cayman)', sheet: '/porsche/modelos/718' },
    macan: { label: 'Macan', sheet: '/porsche/modelos/macan' },
    cayenne: { label: 'Cayenne', sheet: '/porsche/modelos/cayenne' },
    panamera: { label: 'Panamera', sheet: '/porsche/modelos/panamera' },
    taycan: { label: 'Taycan', sheet: '/porsche/modelos/taycan' },
    marca: { label: 'Marca y mercado', sheet: null }
};

// Solo se enlaza a páginas que existen; Gemini elige claves, nunca URLs.
const LINK_CATALOG = {
    precios_ocasion: { label: 'Precios de segunda mano', url: '/porsche/precio-segunda-mano', about: 'precios de ocasión y su evolución' },
    coste_real: { label: 'Coste real de propiedad', url: '/porsche/coste-real', about: 'cuánto cuesta realmente tener un Porsche' },
    fallos: { label: 'Fallos habituales', url: '/porsche/fallos', about: 'averías y fiabilidad por modelo' },
    opiniones: { label: 'Opinión de propietarios', url: '/porsche/analisis', about: 'ranking de modelos según propietarios en Reddit' },
    comparador: { label: 'Comparador de modelos', url: '/porsche/comparador', about: 'comparar modelos' },
    comparativas: { label: 'Comparativas con rivales', url: '/porsche/comparativas', about: 'Porsche frente a BMW, Mercedes, Audi…' },
    financiacion: { label: 'Simulador de financiación', url: '/porsche/financiacion', about: 'cuotas y financiación' },
    renting_leasing: { label: 'Comprar, renting o leasing', url: '/porsche/comprar-renting-leasing', about: 'fórmulas de adquisición' },
    garantia_approved: { label: 'Garantía Porsche Approved', url: '/porsche/garantia-porsche-approved', about: 'garantía oficial de ocasión' },
    inspeccion: { label: 'Checklist de inspección', url: '/porsche/checklist-inspecciones-segunda-mano', about: 'qué revisar al comprar usado' },
    importacion: { label: 'Importar desde Alemania', url: '/porsche/importacion-alemania', about: 'importación' },
    vender: { label: 'Cómo vender tu Porsche', url: '/porsche/como-vender-tu-porsche', about: 'venta de un Porsche' },
    sm_911: { label: '911 de segunda mano', url: '/porsche/911-segunda-mano', about: 'guía de compra de un 911 usado' },
    sm_boxster: { label: 'Boxster de segunda mano', url: '/porsche/boxster-segunda-mano', about: 'guía de compra de un Boxster usado' },
    sm_cayman: { label: 'Cayman de segunda mano', url: '/porsche/cayman-segunda-mano', about: 'guía de compra de un Cayman usado' },
    sm_macan: { label: 'Macan de segunda mano', url: '/porsche/macan-segunda-mano', about: 'guía de compra de un Macan usado' },
    sm_cayenne: { label: 'Cayenne de segunda mano', url: '/porsche/cayenne-segunda-mano', about: 'guía de compra de un Cayenne usado' },
    sm_panamera: { label: 'Panamera de segunda mano', url: '/porsche/panamera-segunda-mano', about: 'guía de compra de un Panamera usado' },
    sm_taycan: { label: 'Taycan de segunda mano', url: '/porsche/taycan-segunda-mano', about: 'guía de compra de un Taycan usado' }
};

function escapeHtml(str) {
    return String(str == null ? '' : str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// ---------- fechas y semanas ISO (siempre en hora de Madrid) ----------

function madridParts(iso) {
    const d = iso ? new Date(iso) : new Date();
    const date = Number.isNaN(d.getTime()) ? new Date() : d;
    const parts = new Intl.DateTimeFormat('en-GB', {
        timeZone: 'Europe/Madrid', day: 'numeric', month: 'numeric', year: 'numeric'
    }).formatToParts(date);
    const get = t => Number(parts.find(p => p.type === t).value);
    return { y: get('year'), m: get('month'), d: get('day') };
}

// Devuelve { key: '2026-W41', year: 2026, week: 41, start: Date(UTC lunes), end: Date(UTC domingo) }
function isoWeek(iso) {
    const { y, m, d } = madridParts(iso);
    const date = new Date(Date.UTC(y, m - 1, d));
    const dow = date.getUTCDay() || 7; // lunes=1 … domingo=7
    const start = new Date(date); start.setUTCDate(date.getUTCDate() - (dow - 1));
    const end = new Date(start); end.setUTCDate(start.getUTCDate() + 6);
    const thursday = new Date(start); thursday.setUTCDate(start.getUTCDate() + 3);
    const year = thursday.getUTCFullYear();
    const jan1 = new Date(Date.UTC(year, 0, 1));
    const week = Math.floor(((thursday - jan1) / 86400000) / 7) + 1;
    return { key: `${year}-W${String(week).padStart(2, '0')}`, year, week, start, end };
}

function weekSlug(key) { // '2026-W41' -> 'semana-2026-41'
    return 'semana-' + key.replace('-W', '-');
}

function weekUrl(key) {
    return `/porsche/tendencias/${weekSlug(key)}`;
}

function fmtDay(date, withYear) {
    const base = `${date.getUTCDate()} de ${MONTHS[date.getUTCMonth()]}`;
    return withYear ? `${base} de ${date.getUTCFullYear()}` : base;
}

function weekLabel(w) { // "5 al 11 de octubre de 2026"
    const s = w.start, e = w.end;
    if (s.getUTCMonth() === e.getUTCMonth()) {
        return `${s.getUTCDate()} al ${fmtDay(e, true)}`;
    }
    return `${fmtDay(s, false)} al ${fmtDay(e, true)}`;
}

function formatDateCard(iso) { // "7 de Octubre, 2026" (formato histórico de las tarjetas)
    const { y, m, d } = madridParts(iso);
    const name = MONTHS[m - 1];
    return `${d} de ${name.charAt(0).toUpperCase()}${name.slice(1)}, ${y}`;
}

// ---------- almacenamiento ----------

function readJson(file, fallback) {
    try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return fallback; }
}

function loadEditorial() { return readJson(EDITORIAL_PATH, []); }
function loadSemanas() { return readJson(SEMANAS_PATH, {}); }

function saveJson(file, data) {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify(data, null, 2) + '\n', 'utf8');
}

// Añade items nuevos (por id) sin tocar los existentes. Devuelve la lista completa, nuevas primero.
function mergeEditorial(existing, newItems) {
    const ids = new Set(existing.map(i => i.id));
    const urls = new Set(existing.map(i => i.url));
    const fresh = newItems.filter(i => !ids.has(i.id) && !urls.has(i.url));
    return [...fresh, ...existing].sort((a, b) => new Date(b.published || 0) - new Date(a.published || 0));
}

// ---------- enlaces internos de una noticia ----------

function itemLinks(item) {
    const out = [];
    const seen = new Set();
    const push = (label, url) => { if (url && !seen.has(url)) { seen.add(url); out.push({ label, url }); } };
    for (const key of (item.links || [])) {
        const l = LINK_CATALOG[key];
        if (l) push(l.label, l.url);
    }
    for (const m of (item.models || [])) {
        const mod = MODELS[m];
        if (mod && mod.sheet) push(`Ficha del ${mod.label.split(' ')[0]}`, mod.sheet);
    }
    return out.slice(0, 4);
}

function impactHtml(item, indent) {
    if (!item.impact) return '';
    const links = itemLinks(item).map(l => `<a href="${l.url}">${escapeHtml(l.label)}</a>`).join('');
    return `${indent}<div class="impact">
${indent}    <span class="impact-label">Nuestra lectura</span>
${indent}    <p>${escapeHtml(item.impact)}</p>${links ? `\n${indent}    <div class="impact-links">${links}</div>` : ''}
${indent}</div>\n`;
}

// Tarjeta de la página principal (sin miniatura: la añade enforceThumbs).
function buildCardHtml(item) {
    const models = (item.models || []).join(',');
    return `<div class="news-card" data-category="${item.category}" data-models="${escapeHtml(models)}">
                <div class="source">${escapeHtml(item.source)}</div>
                <h3>${escapeHtml(item.headline)}</h3>
                <p class="excerpt">${escapeHtml(item.excerpt)}</p>
${impactHtml(item, '                ')}                <div class="meta">
                    <span>${formatDateCard(item.published)}</span>
                    <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener" class="read-more-link">Leer más →</a>
                </div>
                </div>`;
}

// ---------- páginas semanales ----------

const WEEK_CSS = `
        :root {
            --porsche-red: #B12B28; --porsche-gold: #E3AB37; --porsche-grey: #464C47;
            --light-bg: #f6f6f6; --light-card-bg: #ffffff; --light-text: #1a1a1a; --hairline: #e5e5e5;
        }
        body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; background: var(--light-bg); color: var(--light-text); -webkit-font-smoothing: antialiased; }
        .container { max-width: 900px; margin: auto; padding: 20px; }
        .site-header { padding: 18px 32px; background: #fff; border-bottom: 1px solid var(--hairline); position: sticky; top: 0; z-index: 100; box-sizing: border-box; }
        .site-header-inner { display: flex; justify-content: space-between; align-items: center; max-width: 1400px; margin: 0 auto; }
        .site-logo { display: flex; align-items: center; gap: 12px; text-decoration: none; color: var(--light-text); }
        .site-logo-mark { height: 26px; width: auto; display: block; }
        .site-logo-text { font-size: 14px; font-weight: 600; letter-spacing: 2px; text-transform: uppercase; }
        .site-logo-text span { color: var(--porsche-red); }
        .site-nav { display: flex; align-items: center; gap: 28px; }
        .site-nav a { text-decoration: none; color: var(--light-text); font-weight: 500; font-size: 12px; letter-spacing: 1px; text-transform: uppercase; }
        .site-nav a:hover { color: var(--porsche-red); }
        .site-footer { text-align: center; padding: 40px 20px; margin-top: 40px; border-top: 1px solid var(--hairline); font-size: 0.85rem; color: var(--porsche-grey); }
        .site-footer p { margin: 6px 0; }
        .nav-toggle { display: none; background: none; border: 1px solid var(--porsche-grey); color: inherit; width: 34px; height: 34px; border-radius: 4px; cursor: pointer; font-size: 16px; align-items: center; justify-content: center; flex-shrink: 0; }
        @media (max-width: 600px) {
            .site-logo-text { display: none; } .site-nav { display: none; } .nav-toggle { display: flex; }
            .site-nav.is-open { display: flex; flex-direction: column; align-items: flex-start; gap: 0; position: absolute; top: 100%; left: 0; width: 100%; background: #fff; padding: 6px 32px 16px; box-sizing: border-box; border-bottom: 1px solid var(--hairline); }
            .site-nav.is-open a { width: 100%; padding: 14px 0; border-bottom: 1px solid var(--hairline); }
        }
        .page-back { display: inline-block; margin-bottom: 18px; font-size: 0.85rem; color: var(--porsche-red); text-decoration: none; font-weight: 600; }
        .page-back:hover { text-decoration: underline; }
        .eyebrow { display: block; font-size: 12px; letter-spacing: 2px; text-transform: uppercase; font-weight: 600; color: var(--porsche-red); margin-bottom: 8px; }
        h1 { margin: 0 0 14px 0; font-size: 1.8rem; line-height: 1.25; }
        .week-summary { background: var(--light-card-bg); border: 1px solid var(--hairline); border-radius: 8px; padding: 22px 26px; margin-bottom: 26px; }
        .week-summary p { margin: 0 0 12px 0; line-height: 1.65; }
        .week-summary ul { margin: 0; padding-left: 20px; }
        .week-summary li { margin-bottom: 6px; line-height: 1.5; }
        .week-summary li a { color: var(--porsche-red); font-weight: 600; text-decoration: none; }
        .week-summary li a:hover { text-decoration: underline; }
        .week-item { background: var(--light-card-bg); border: 1px solid var(--hairline); border-radius: 8px; padding: 20px 24px; margin-bottom: 16px; }
        .week-item .meta-line { font-size: 12px; font-weight: 600; color: var(--porsche-gold); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
        .week-item h2 { margin: 0 0 8px 0; font-size: 1.2rem; line-height: 1.35; }
        .week-item p.excerpt { margin: 0 0 12px 0; line-height: 1.6; opacity: 0.85; }
        .impact { border-left: 3px solid var(--porsche-red); background: #faf3f3; padding: 10px 14px; border-radius: 0 6px 6px 0; margin-bottom: 12px; }
        .impact-label { display: block; font-size: 11px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: var(--porsche-red); margin-bottom: 4px; }
        .impact p { margin: 0; font-size: 0.93rem; line-height: 1.55; }
        .impact-links { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-top: 8px; }
        .impact-links a { font-size: 0.85rem; font-weight: 600; color: var(--porsche-red); text-decoration: none; }
        .impact-links a:hover { text-decoration: underline; }
        .read-more-link { color: var(--porsche-red); font-weight: 600; text-decoration: none; font-size: 0.9rem; }
        .week-nav { display: flex; justify-content: space-between; gap: 12px; margin-top: 28px; font-size: 0.9rem; font-weight: 600; }
        .week-nav a { color: var(--porsche-red); text-decoration: none; }
        .week-nav a:hover { text-decoration: underline; }
`;

function buildWeekPageHtml(key, items, semana, neighbours) {
    const [yy, ww] = key.split('-W').map(Number);
    const { start, end } = weekRangeFromKey(key);
    const label = weekLabel({ start, end });

    const title = `Tendencias Porsche: semana del ${label} | Mejor Imposible`;
    const summary = (semana && semana.summary) || '';
    const desc = (summary || `Las noticias de Porsche de la semana del ${label}, con lo que significan para quien compra o tiene uno.`)
        .replace(/\s+/g, ' ').slice(0, 200);

    const highlights = ((semana && semana.highlights) || []).map(h =>
        `                <li><a href="${escapeHtml(h.url)}" target="_blank" rel="noopener">${escapeHtml(h.shortTitle)}</a> — ${escapeHtml(h.note)}</li>`
    ).join('\n');

    const itemsHtml = items.map(it => `
        <article class="week-item">
            <div class="meta-line">${escapeHtml(it.source)} · ${formatDateCard(it.published)} · ${escapeHtml(it.category)}</div>
            <h2>${escapeHtml(it.headline)}</h2>
            <p class="excerpt">${escapeHtml(it.excerpt)}</p>
${impactHtml(it, '            ')}            <a class="read-more-link" href="${escapeHtml(it.url)}" target="_blank" rel="noopener">Leer la noticia original →</a>
        </article>`).join('\n');

    const nav = [
        neighbours.prev ? `<a href="${weekUrl(neighbours.prev.key)}">&larr; Semana del ${neighbours.prev.label}</a>` : '<span></span>',
        neighbours.next ? `<a href="${weekUrl(neighbours.next.key)}">Semana del ${neighbours.next.label} &rarr;</a>` : '<span></span>'
    ].join('');

    const ld = {
        '@context': 'https://schema.org',
        '@type': 'CollectionPage',
        name: `Tendencias Porsche: semana del ${label}`,
        url: `${SITE}${weekUrl(key)}`,
        inLanguage: 'es',
        isPartOf: { '@type': 'WebSite', name: 'Mejor Imposible', url: SITE },
        hasPart: items.map(it => ({ '@type': 'NewsArticle', headline: it.headline, url: it.url, datePublished: it.published }))
    };

    return `---
---
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${escapeHtml(title)}</title>
    <meta name="description" content="${escapeHtml(desc)}">
    <link rel="canonical" href="${SITE}${weekUrl(key)}">
    <link rel="icon" type="image/png" sizes="32x32" href="/img/favicon.png">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>${WEEK_CSS}    </style>
    <script type="application/ld+json">${JSON.stringify(ld).replace(/</g, '\\u003c')}</script>
</head>
<body>
    <header class="site-header">
        <div class="site-header-inner">
            <a href="/" class="site-logo">
                <img src="/img/logo_mi_transparent.png" alt="" class="site-logo-mark">
                <span class="site-logo-text">mejor <span>imposible</span></span>
            </a>
            <nav class="site-nav">
                <a href="/#tools">Herramientas</a>
                <a href="/porsche/modelos">Modelos</a>
                <a href="/porsche/analisis">Opiniones</a>
                <a href="/porsche/concesionarios">Concesionarios</a>
            </nav>
            <button class="nav-toggle" id="nav-toggle" aria-label="Abrir menu">&#9776;</button>
        </div>
    </header>
    <div class="container">
        <a class="page-back" href="/porsche/tendencias">&larr; Volver a tendencias</a>
        <span class="eyebrow">Resumen semanal · semana ${ww} de ${yy}</span>
        <h1>Tendencias Porsche: semana del ${label}</h1>
${summary ? `        <div class="week-summary">
            <p>${escapeHtml(summary)}</p>${highlights ? `\n            <ul>\n${highlights}\n            </ul>` : ''}
        </div>` : ''}
${itemsHtml}
        <div class="week-nav">${nav}</div>
    </div>
    <footer class="site-footer">
        <p>&copy; <span id="current-year"></span> mejorimposible.es - Una guía no oficial creada por y para entusiastas de Porsche.</p>
        <p>Todos los nombres de productos, logotipos y marcas son propiedad de sus respectivos dueños.</p>
    </footer>
    <script>document.getElementById('current-year').textContent = new Date().getFullYear();
        (function () { var t = document.getElementById('nav-toggle'), n = document.querySelector('.site-nav'); if (t && n) t.addEventListener('click', function () { n.classList.toggle('is-open'); }); })();</script>
</body>
</html>
`;
}

function weekRangeFromKey(key) {
    const [yy, ww] = key.split('-W').map(Number);
    const jan4 = new Date(Date.UTC(yy, 0, 4));
    const mondayW1 = new Date(jan4); mondayW1.setUTCDate(jan4.getUTCDate() - ((jan4.getUTCDay() || 7) - 1));
    const start = new Date(mondayW1); start.setUTCDate(mondayW1.getUTCDate() + (ww - 1) * 7);
    const end = new Date(start); end.setUTCDate(start.getUTCDate() + 6);
    return { start, end, label: weekLabel({ start, end }) };
}

// Escribe una página por cada semana con noticias curadas y actualiza tendencias-semanas.json.
// Devuelve la lista de claves de semana (más reciente primero).
function writeWeeklyPages(editorial, semanas, { dryRun = false } = {}) {
    const byWeek = new Map();
    for (const it of editorial) {
        const k = isoWeek(it.published).key;
        if (!byWeek.has(k)) byWeek.set(k, []);
        byWeek.get(k).push(it);
    }
    const keys = [...byWeek.keys()].sort().reverse(); // más reciente primero
    keys.forEach((key, idx) => {
        const items = byWeek.get(key).sort((a, b) => new Date(b.published) - new Date(a.published));
        const prevKey = keys[idx + 1];
        const nextKey = keys[idx - 1];
        const neighbours = {
            prev: prevKey ? { key: prevKey, label: weekRangeFromKey(prevKey).label } : null,
            next: nextKey ? { key: nextKey, label: weekRangeFromKey(nextKey).label } : null
        };
        const html = buildWeekPageHtml(key, items, semanas[key], neighbours);
        const file = path.join(SEMANAS_DIR, `${weekSlug(key)}.html`);
        if (!dryRun) {
            fs.mkdirSync(SEMANAS_DIR, { recursive: true });
            fs.writeFileSync(file, html, 'utf8');
        }
    });
    return keys;
}

// Entradas del sitemap para las páginas semanales (se añaden si faltan; nunca se quitan).
function ensureSitemapWeeks(sitemap, keys, editorial) {
    let out = sitemap;
    for (const key of keys) {
        const loc = `${SITE}${weekUrl(key)}`;
        if (out.includes(`<loc>${loc}</loc>`)) continue;
        const last = editorial.filter(i => isoWeek(i.published).key === key)
            .map(i => i.published).sort().pop();
        const mod = (last ? new Date(last) : new Date()).toISOString().slice(0, 10);
        const block = `  <url>\n    <loc>${loc}</loc>\n    <lastmod>${mod}</lastmod>\n    <changefreq>yearly</changefreq>\n    <priority>0.5</priority>\n  </url>\n`;
        out = out.replace('</urlset>', block + '</urlset>');
    }
    return out;
}

// Lista HTML del archivo semanal (se pinta en la página principal entre marcadores).
function buildArchiveHtml(keys, editorial, semanas) {
    const lis = keys.map(key => {
        const n = editorial.filter(i => i.week === key).length;
        const sum = ((semanas[key] && semanas[key].summary) || '').replace(/\s+/g, ' ');
        const short = sum.length > 190 ? sum.slice(0, 187).replace(/\s+\S*$/, '') + '…' : sum;
        return `                    <li>
                        <a href="${weekUrl(key)}">Semana del ${weekRangeFromKey(key).label}</a>
                        <span class="weeks-count">${n} ${n === 1 ? 'noticia' : 'noticias'}</span>${short ? `
                        <p>${escapeHtml(short)}</p>` : ''}
                    </li>`;
    }).join('\n');
    return `
${lis}
                    `;
}

module.exports = {
    ROOT, EDITORIAL_PATH, SEMANAS_PATH, MODELS, LINK_CATALOG, MONTHS,
    escapeHtml, isoWeek, weekSlug, weekUrl, weekLabel, weekRangeFromKey, formatDateCard,
    loadEditorial, loadSemanas, saveJson, mergeEditorial,
    itemLinks, impactHtml, buildCardHtml, buildArchiveHtml, writeWeeklyPages, ensureSitemapWeeks
};
