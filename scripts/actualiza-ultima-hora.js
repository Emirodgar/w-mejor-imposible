#!/usr/bin/env node
// Actualiza el bloque "Noticias de última hora" de porsche/tendencias.html
// a partir del feed Atom de Google Alerts. Pensado para correr sin
// supervisión (GitHub Actions), cada 5 horas.

const fs = require('fs');
const path = require('path');

const FEED_URL = 'https://www.google.es/alerts/feeds/05845247816632936990/13600355039029436216';
const TENDENCIAS_PATH = path.join(__dirname, '..', 'porsche', 'tendencias.html');
const SITEMAP_PATH = path.join(__dirname, '..', 'sitemap.xml');
const SITEMAP_LOC = 'https://mejorimposible.es/porsche/tendencias';
const MAX_ITEMS = 10;

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
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function extractRealUrl(googleUrl) {
    try {
        const u = new URL(googleUrl);
        const real = u.searchParams.get('url'); // URLSearchParams ya decodifica el %-encoding
        return real || googleUrl;
    } catch {
        return googleUrl;
    }
}

function parseEntries(xml) {
    const entries = [];
    const blocks = xml.match(/<entry>[\s\S]*?<\/entry>/g) || [];
    for (const block of blocks) {
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

        const description = contentMatch ? decodeEntities(stripTags(decodeEntities(contentMatch[1]))) : '';
        const url = extractRealUrl(decodeEntities(linkMatch[1]));
        const published = publishedMatch ? publishedMatch[1] : null;

        entries.push({ id: idMatch[1], title, source, description, url, published });
    }
    return entries;
}

function mentionsPorsche(entry) {
    const haystack = `${entry.title} ${entry.description}`.toLowerCase();
    return haystack.includes('porsche');
}

function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleDateString('es-ES', { day: '2-digit', month: 'long', year: 'numeric' });
}

function buildItemsHtml(entries) {
    return entries.map(e => {
        const metaParts = [e.source, formatDate(e.published)].filter(Boolean);
        const meta = metaParts.length
            ? `\n                    <span class="latest-news-meta">${escapeHtml(metaParts.join(' · '))}</span>`
            : '';
        return `                <li>
                    <a href="${escapeHtml(e.url)}" target="_blank" rel="noopener">${escapeHtml(e.title)}</a>${meta}
                    <p>${escapeHtml(e.description)}</p>
                </li>`;
    }).join('\n');
}

function replaceBetweenMarkers(html, startMarker, endMarker, replacement, { inline = false } = {}) {
    const re = new RegExp(`${startMarker}[\\s\\S]*?${endMarker}`);
    if (!re.test(html)) {
        throw new Error(`No se encontraron los marcadores ${startMarker} / ${endMarker} en tendencias.html`);
    }
    const wrapped = inline
        ? `${startMarker}${replacement}${endMarker}`
        : `${startMarker}\n${replacement}\n                ${endMarker}`;
    return html.replace(re, wrapped);
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

async function main() {
    const res = await fetch(FEED_URL);
    if (!res.ok) {
        throw new Error(`No se pudo descargar el feed (HTTP ${res.status})`);
    }
    const xml = await res.text();

    const entries = parseEntries(xml)
        .filter(mentionsPorsche)
        .slice(0, MAX_ITEMS);

    if (entries.length === 0) {
        console.log('El feed no trajo noticias relevantes de Porsche esta vez; no se modifica la página.');
        return;
    }

    let html = fs.readFileSync(TENDENCIAS_PATH, 'utf8');

    const itemsHtml = buildItemsHtml(entries);
    html = replaceBetweenMarkers(html, '<!-- LATEST-NEWS-ITEMS:START -->', '<!-- LATEST-NEWS-ITEMS:END -->', itemsHtml);

    const now = new Date();
    const updatedLabel = now.toLocaleString('es-ES', {
        timeZone: 'Europe/Madrid',
        day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit'
    });
    html = replaceBetweenMarkers(html, '<!-- LATEST-NEWS-UPDATED:START -->', '<!-- LATEST-NEWS-UPDATED:END -->', updatedLabel, { inline: true });

    fs.writeFileSync(TENDENCIAS_PATH, html, 'utf8');

    const isoDate = now.toISOString().slice(0, 10);
    let sitemap = fs.readFileSync(SITEMAP_PATH, 'utf8');
    sitemap = updateSitemapLastmod(sitemap, SITEMAP_LOC, isoDate);
    fs.writeFileSync(SITEMAP_PATH, sitemap, 'utf8');

    console.log(`Actualizadas ${entries.length} noticias de última hora (${updatedLabel}).`);
}

main().catch(err => {
    console.error(err.message);
    process.exit(1);
});
