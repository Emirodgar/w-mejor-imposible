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
