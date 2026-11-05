(function () {
    var form = document.getElementById('search');
    if (!form) return;
    var q = form.querySelector('#q'), cat = form.querySelector('#cat'), zone = form.querySelector('#zone');
    var list = document.getElementById('results'), count = document.getElementById('count');
    var cats = JSON.parse(form.dataset.cats), zones = JSON.parse(form.dataset.zones);
    var data = [];
    function norm(s) { return (s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, ''); }
    function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
    function render() {
        var terms = norm(q.value).split(/\s+/).filter(Boolean);
        var out = data.filter(function (d) {
            if (cat.value && d.c !== cat.value) return false;
            if (zone.value && d.z !== zone.value) return false;
            return terms.every(function (t) { return d.h.indexOf(t) !== -1; });
        });
        var shown = out.slice(0, 80);
        list.innerHTML = shown.map(function (d) {
            return '<li class="dealer"><p class="city">' + esc(cats[d.c] || d.c) + ' · ' + esc(d.p) + '</p>' +
                '<h3><a href="' + esc(d.u) + '">' + esc(d.n) + '</a></h3><p>' + esc(d.w) + '</p>' +
                (d.s ? '<p class="muted">' + esc(d.s) + '</p>' : '') +
                '<button type="button" class="save" data-ref="' + esc(d.id) + '" data-on="' + esc(form.dataset.saved) + '" data-off="' + esc(form.dataset.save) + '" aria-pressed="false">' + esc(form.dataset.save) + '</button></li>';
        }).join('');
        count.textContent = out.length === 0 ? form.dataset.none : (out.length === 1 ? form.dataset.count1 : form.dataset.count.replace('{n}', out.length));
        var p = new URLSearchParams();
        if (q.value) p.set('q', q.value);
        if (cat.value) p.set('cat', cat.value);
        if (zone.value) p.set('zone', zone.value);
        if (window.miViaje) window.miViaje.update();
        var s = p.toString();
        try { history.replaceState(null, '', location.pathname + (s ? '?' + s : '')); } catch (e) { }
    }
    form.addEventListener('submit', function (ev) { ev.preventDefault(); });
    [q, cat, zone].forEach(function (el) { el.addEventListener('input', render); el.addEventListener('change', render); });
    var init = new URLSearchParams(location.search);
    q.value = init.get('q') || '';
    fetch(form.dataset.index).then(function (r) { return r.json(); }).then(function (rows) {
        data = rows.map(function (d) { d.h = norm([d.n, d.p, cats[d.c], zones[d.z], d.s, d.w].join(' ')); return d; });
        if (init.get('cat')) cat.value = init.get('cat');
        if (init.get('zone')) zone.value = init.get('zone');
        render();
    }).catch(function () { count.textContent = form.dataset.none; });
})();
