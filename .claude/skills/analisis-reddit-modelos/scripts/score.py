#!/usr/bin/env python3
"""Agrega las clasificaciones de comentarios y genera porsche/analisis-reddit.json.

Reglas (las mismas que describe la web en su apartado de metodologia):
  1. Solo cuentan comentarios con experiencia propia (basis = owner | driven).
  2. Cada usuario cuenta UNA vez por modelo, haga los comentarios que haga.
  3. Si el comentario no precisa el modelo/generacion, el voto se reparte (1/n) entre los candidatos.
     Si el usuario precisa en algun comentario, su peso para ese modelo es el del comentario mas preciso.
  4. Ranking = limite inferior de Wilson (95 %) x log2(1 + votos netos positivos): hace falta
     volumen y apoyo consistente a la vez.
Sin dependencias (Python 3.9+). No escribe nombres de usuario: solo hashes en el estado interno.
"""
import json, math, os, sys, datetime
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
ROOT = os.path.abspath(os.path.join(SKILL, "..", "..", ".."))
STATE = os.path.join(ROOT, ".claude", "state", "analisis-reddit")
OUT = os.path.join(ROOT, "porsche", "analisis-reddit.json")
SIGN = {"pos": 1, "neg": -1, "neu": 0}
COUNTS = ("owner", "driven")
Z = 1.96


def wilson_lb(pos, n):
    if n <= 0:
        return 0.0
    p = pos / n
    d = 1 + Z * Z / n
    c = p + Z * Z / (2 * n)
    m = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n))
    return max(0.0, (c - m) / d)


def confidence(n):
    return "insuficiente" if n < 5 else "baja" if n < 15 else "media" if n < 40 else "alta"


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def aggregate(votes, aspects_votes, quotes_src, label):
    """votes: {(user, key): [(sign, w)]} -> fila de ranking por key."""
    per = defaultdict(lambda: {"pos": 0.0, "neg": 0.0, "neu": 0.0, "users": set()})
    for (user, key), lst in votes.items():
        w = max(x[1] for x in lst)
        s = sum(x[0] * x[1] for x in lst)
        side = "pos" if s > 0 else "neg" if s < 0 else "neu"
        per[key][side] += w
        per[key]["users"].add(user)
    rows = []
    for key, d in per.items():
        n = d["pos"] + d["neg"]
        net = d["pos"] - d["neg"]
        wl = wilson_lb(d["pos"], n)
        asp = defaultdict(lambda: {"pos": 0.0, "neg": 0.0})
        for (user, k, a), lst in aspects_votes.items():
            if k != key:
                continue
            w = max(x[1] for x in lst)
            s = sum(x[0] * x[1] for x in lst)
            if s:
                asp[a]["pos" if s > 0 else "neg"] += w
        pros = sorted(((a, v["pos"]) for a, v in asp.items() if v["pos"] >= 1), key=lambda x: -x[1])[:3]
        cons = sorted(((a, v["neg"]) for a, v in asp.items() if v["neg"] >= 1), key=lambda x: -x[1])[:3]
        qs = {"pos": [], "neg": []}
        seen_users = set()
        for q in sorted(quotes_src.get(key, []), key=lambda q: -q["score"]):
            if q["user"] in seen_users or len(qs[q["sentiment"]]) >= 3:
                continue
            seen_users.add(q["user"])
            qs[q["sentiment"]].append({"text": q["text"], "url": q["url"], "score": q["score"], "basis": q["basis"]})
        rows.append({
            "id": key, "label": label(key),
            "users": len(d["users"]), "votes_effective": round(n + d["neu"], 1),
            "pos": round(d["pos"], 1), "neg": round(d["neg"], 1), "neu": round(d["neu"], 1),
            "net": round(net, 1), "pct_positive": round(100 * d["pos"] / n) if n else None,
            "wilson": round(wl, 3), "rank_score": round(wl * math.log2(1 + max(net, 0)), 3),
            "confidence": confidence(n + d["neu"]),
            "pros": [{"aspect": a, "users": round(v, 1)} for a, v in pros],
            "cons": [{"aspect": a, "users": round(v, 1)} for a, v in cons],
            "quotes_pos": qs["pos"], "quotes_neg": qs["neg"],
        })
    rows.sort(key=lambda r: (r["confidence"] == "insuficiente", -r["rank_score"], -r["users"]))
    return rows


def main():
    with open(os.path.join(SKILL, "models.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    models = {m["id"]: m for m in cfg["models"]}
    idx = os.path.join(STATE, "comments-index.jsonl")  # sin texto: es lo unico que se versiona
    comments = {c["id"]: c for c in load_jsonl(idx if os.path.exists(idx) else os.path.join(STATE, "comments.jsonl"))}
    threads = json.load(open(os.path.join(STATE, "threads.json"), encoding="utf-8"))
    cdir = os.path.join(STATE, "classified")
    entries = []
    for fn in sorted(os.listdir(cdir)) if os.path.isdir(cdir) else []:
        entries += json.load(open(os.path.join(cdir, fn), encoding="utf-8"))

    mvotes, mdefault_asp, mquotes = defaultdict(list), defaultdict(list), defaultdict(list)
    fvotes, fasp, fquotes = defaultdict(list), defaultdict(list), defaultdict(list)
    n_valid = n_skipped = 0
    users_counted = set()
    seen_ids = set()
    for e in entries:
        if e["id"] in seen_ids:
            continue
        seen_ids.add(e["id"])
        c = comments.get(e["id"].split("#")[0])
        ms = [m for m in e.get("models", []) if m in models]
        if not c or not ms or e.get("sentiment") not in SIGN or e.get("basis") not in COUNTS:
            n_skipped += 1
            continue
        n_valid += 1
        sign, user, n = SIGN[e["sentiment"]], c["user"], len(ms)
        users_counted.add(user)
        url = f"https://www.reddit.com/comments/{c['thread']}/_/{c['id']}/"
        fams = sorted({models[m]["family"] for m in ms})
        for m in ms:
            mvotes[(user, m)].append((sign, 1.0 / n))
            for a in e.get("aspects", []):
                if a.get("p") in ("pos", "neg") and a.get("a") in cfg["aspects"]:
                    mdefault_asp[(user, m, a["a"])].append((SIGN[a["p"]], 1.0 / n))
            if n == 1 and e.get("resumen_es") and e["sentiment"] in ("pos", "neg"):
                mquotes[m].append({"user": user, "sentiment": e["sentiment"], "text": e["resumen_es"], "url": url,
                                   "score": c["score"], "basis": e["basis"]})
        for f in fams:
            fvotes[(user, f)].append((sign, 1.0 / len(fams)))
            for a in e.get("aspects", []):
                if a.get("p") in ("pos", "neg") and a.get("a") in cfg["aspects"]:
                    fasp[(user, f, a["a"])].append((SIGN[a["p"]], 1.0 / len(fams)))
            if len(fams) == 1 and e.get("resumen_es") and e["sentiment"] in ("pos", "neg"):
                fquotes[f].append({"user": user, "sentiment": e["sentiment"], "text": e["resumen_es"], "url": url,
                                   "score": c["score"], "basis": e["basis"]})

    by_model = aggregate(mvotes, mdefault_asp, mquotes, lambda k: models[k]["label"])
    for r in by_model:
        r["family"] = models[r["id"]]["family"]
    by_family = aggregate(fvotes, fasp, fquotes, lambda k: k)

    created = [t["created"] for t in threads if t.get("created")]
    out = {
        "generated": datetime.date.today().isoformat(),
        "stats": {
            "threads": len(threads), "comments_fetched": len(comments),
            "comments_classified": len(entries), "comments_counted": n_valid,
            "users_counted": len(users_counted),
            "period_from": datetime.date.fromtimestamp(min(created)).isoformat() if created else None,
            "period_to": datetime.date.fromtimestamp(max(created)).isoformat() if created else None,
        },
        "aspects_es": cfg["aspects_es"],
        "families": by_family,
        "models": by_model,
        "threads": sorted(({"title": t["title"], "sub": t["sub"], "url": t["url"], "comments": t["num_comments"]}
                           for t in threads if t.get("title")), key=lambda t: -t["comments"]),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[score] {n_valid} comentarios validos ({n_skipped} descartados por base/modelo), {len(users_counted)} usuarios -> {OUT}")
    for r in by_family:
        print(f"  {r['label']:10} usuarios={r['users']:3} pos={r['pos']:5} neg={r['neg']:5} wilson={r['wilson']} rank={r['rank_score']} [{r['confidence']}]")


if __name__ == "__main__":
    main()
