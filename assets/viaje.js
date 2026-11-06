(function () {
    var KEY = 'mi-viaje';
    function get() { try { var a = JSON.parse(localStorage.getItem(KEY)); return Array.isArray(a) ? a : []; } catch (e) { return []; } }
    function put(a) { try { localStorage.setItem(KEY, JSON.stringify(a)); } catch (e) { } update(); }
    function has(r) { return get().indexOf(r) !== -1; }
    function toggle(r) { var a = get(), i = a.indexOf(r); if (i === -1) a.push(r); else a.splice(i, 1); put(a); }
    function update() {
        var a = get();
        document.querySelectorAll('.save').forEach(function (b) {
            var on = a.indexOf(b.dataset.ref) !== -1;
            b.setAttribute('aria-pressed', String(on));
            b.textContent = on ? b.dataset.on : b.dataset.off;
        });
        document.querySelectorAll('.trip-count').forEach(function (s) { s.hidden = !a.length; s.textContent = a.length ? ' (' + a.length + ')' : ''; });
        if (window.renderTrip) window.renderTrip();
    }
    document.addEventListener('click', function (ev) {
        var b = ev.target.closest && ev.target.closest('.save');
        if (b) { ev.preventDefault(); toggle(b.dataset.ref); }
    });
    window.miViaje = { get: get, put: put, has: has, toggle: toggle, update: update };

    var root = document.getElementById('trip');
    if (root) {
        var cats = JSON.parse(root.dataset.cats), data = null, shared = null;
        var list = document.getElementById('trip-list'), msg = document.getElementById('trip-msg'), count = document.getElementById('trip-count');
        var q = new URLSearchParams(location.search).get('l');
        if (q) shared = q.split(',').map(decodeURIComponent).filter(Boolean);
        function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
        window.renderTrip = function () {
            if (!data) return;
            var refs = shared || get();
            var rows = refs.map(function (r) { return data[r]; }).filter(Boolean);
            document.getElementById('trip-shared').hidden = !shared;
            document.getElementById('trip-actions').hidden = !rows.length;
            document.getElementById('trip-clear').hidden = !!shared;
            document.getElementById('trip-save').hidden = !shared;
            msg.hidden = !!rows.length;
            count.textContent = rows.length === 1 ? root.dataset.count1 : root.dataset.count.replace('{n}', rows.length);
            count.hidden = !rows.length;
            var order = Object.keys(cats), out = '';
            order.forEach(function (c) {
                var g = rows.filter(function (d) { return d.c === c; });
                if (!g.length) return;
                out += '<li class="trip-group"><h2>' + esc(cats[c]) + '</h2><ul class="dealers">' + g.map(function (d) {
                    return '<li class="dealer"><p class="city">' + esc(d.p) + '</p><h3><a href="' + esc(d.u) + '">' + esc(d.n) + '</a></h3>' +
                        (d.s ? '<p class="muted">' + esc(d.s) + '</p>' : '') +
                        (shared ? '' : '<button type="button" class="link-btn no-print" data-remove="' + esc(d.id) + '">' + esc(root.dataset.rm) + '</button>') + '</li>';
                }).join('') + '</ul></li>';
            });
            list.innerHTML = out;
        };
        list.addEventListener('click', function (ev) {
            var b = ev.target.closest('[data-remove]');
            if (b) toggle(b.dataset.remove);
        });
        document.getElementById('trip-print').addEventListener('click', function () { window.print(); });
        document.getElementById('trip-clear').addEventListener('click', function () { put([]); });
        document.getElementById('trip-save').addEventListener('click', function () {
            var a = get(); (shared || []).forEach(function (r) { if (a.indexOf(r) === -1) a.push(r); });
            put(a); history.replaceState(null, '', location.pathname); shared = null; window.renderTrip();
        });
        document.getElementById('trip-copy').addEventListener('click', function () {
            var link = location.origin + location.pathname + '?l=' + (shared || get()).map(encodeURIComponent).join(',');
            var done = function () { var b = document.getElementById('trip-copy'); var t = b.textContent; b.textContent = root.dataset.copied; setTimeout(function () { b.textContent = t; }, 1800); };
            if (navigator.clipboard) navigator.clipboard.writeText(link).then(done, function () { window.prompt('', link); });
            else window.prompt('', link);
        });
        fetch(root.dataset.index).then(function (r) { return r.json(); }).then(function (rows) {
            data = {}; rows.forEach(function (d) { data[d.id] = d; });
            window.renderTrip();
        });
    }
    update();
})();

/* Tiras de la portada: flechas laterales (el deslizamiento táctil es nativo) */
(function () {
    var L = {
        es: ['Anterior', 'Siguiente'], en: ['Previous', 'Next'], fr: ['Précédent', 'Suivant'],
        de: ['Zurück', 'Weiter'], pt: ['Anterior', 'Seguinte'], it: ['Precedente', 'Successivo']
    };
    var lab = L[(document.documentElement.lang || 'es').slice(0, 2)] || L.es;
    var chev = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false"><path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="square"/></svg>';
    document.querySelectorAll('.strip-scroll').forEach(function (sc) {
        var rail = document.createElement('div');
        rail.className = 'strip-rail';
        sc.parentNode.insertBefore(rail, sc);
        rail.appendChild(sc);
        function mk(dir) {
            var b = document.createElement('button');
            b.type = 'button';
            b.className = 'strip-arrow ' + (dir < 0 ? 'prev' : 'next');
            b.setAttribute('aria-label', lab[dir < 0 ? 0 : 1]);
            b.innerHTML = chev;
            b.addEventListener('click', function () {
                var li = sc.querySelector('li');
                var step = li ? li.getBoundingClientRect().width + 20 : sc.clientWidth * 0.8;
                sc.scrollBy({ left: dir * step * 2, behavior: 'smooth' });
            });
            rail.appendChild(b);
            return b;
        }
        var prev = mk(-1), next = mk(1);
        function upd() {
            var max = sc.scrollWidth - sc.clientWidth - 2;
            prev.hidden = sc.scrollLeft <= 2;
            next.hidden = sc.scrollLeft >= max;
        }
        sc.addEventListener('scroll', upd, { passive: true });
        window.addEventListener('resize', upd);
        upd();
    });
})();

/* Menú móvil: botón hamburguesa que agrupa navegación e idiomas */
(function () {
    var h = document.querySelector('.site-header');
    var nav = h && h.querySelector('.main-nav');
    if (!nav) return;
    var L = { es: 'Menú', en: 'Menu', fr: 'Menu', de: 'Menü', pt: 'Menu', it: 'Menu' };
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'nav-toggle';
    b.setAttribute('aria-label', L[(document.documentElement.lang || 'es').slice(0, 2)] || 'Menú');
    b.setAttribute('aria-expanded', 'false');
    b.innerHTML = '<span></span><span></span><span></span>';
    nav.id = nav.id || 'main-nav';
    b.setAttribute('aria-controls', nav.id);
    h.insertBefore(b, nav);
    h.classList.add('has-toggle');
    function set(o) { h.classList.toggle('open', o); b.setAttribute('aria-expanded', String(o)); }
    b.addEventListener('click', function () { set(!h.classList.contains('open')); });
    nav.addEventListener('click', function (e) { if (e.target.closest('a')) set(false); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') set(false); });
})();

/* Botón flotante: volver arriba */
(function () {
    var L = { es: 'Volver arriba', en: 'Back to top', fr: 'Haut de page', de: 'Nach oben', pt: 'Voltar ao topo', it: 'Torna su' };
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'to-top';
    b.setAttribute('aria-label', L[(document.documentElement.lang || 'es').slice(0, 2)] || L.es);
    b.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false"><path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="square"/></svg>';
    b.addEventListener('click', function () { window.scrollTo({ top: 0, behavior: 'smooth' }); });
    document.body.appendChild(b);
    function upd() { b.classList.toggle('show', window.scrollY > 600); }
    window.addEventListener('scroll', upd, { passive: true });
    upd();
})();
