#!/usr/bin/env python3
"""Va chercher sur Ping Pocket (pages publiques) les points et les matchs d'un licencié et écrit data/<licence>.json.
Une seule visite par licencié et par jour (lancé par .github/workflows/maj.yml). Pas de noms d'adversaires dans le
fichier publié : seulement date, épreuve, points gagnés/perdus et s'ils sont déjà dans les points mensuels."""
import json, re, sys, time, html, datetime, urllib.request, os

UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/128 Mobile Safari/537.36"
BASE = "https://www.pingpocket.fr/app/fftt/licencies/"
MOIS = {"jan": 1, "fév": 2, "fev": 2, "feb": 2, "mar": 3, "avr": 4, "apr": 4, "mai": 5, "may": 5, "jun": 6, "juin": 6,
        "jul": 7, "juil": 7, "aoû": 8, "aou": 8, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "déc": 12, "dec": 12}

def get(url, essais=4):
    for k in range(essais):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            print("essai", k + 1, url, e, file=sys.stderr); time.sleep(10*(k + 1))
    raise SystemExit("Ping Pocket ne répond pas: " + url)

def txt(s): return html.unescape(re.sub(r"<[^>]+>", " ", s)).strip()
def num(s):
    m = re.search(r"-?\d+(?:[.,]\d+)?", s or ""); return float(m.group(0).replace(",", ".")) if m else None

def date_iso(s):
    m = re.match(r"(\d{1,2})\s+(\S+)\s+(\d{4})", s.strip())
    if not m: return ""
    mois = MOIS.get(m.group(2).lower().rstrip(".")[:4]) or MOIS.get(m.group(2).lower()[:3])
    return f"{m.group(3)}-{mois:02d}-{int(m.group(1)):02d}" if mois else ""

def fiche(lic):
    t = get(BASE + lic)
    val = {}
    for rotulo, chave in ((r"Classement officiel", "classement"), (r"Points mensuels", "mensuels"),
                          (r"Points officiels phase \d", "officielsPhase"), (r"Progression mensuelle", "progMensuelle")):
        m = re.search(rotulo, t)
        if m: val[chave] = num(txt(t[m.end():m.end() + 400]))
    m = re.search(r"<h1>([^<]+)</h1>", t); val["nom"] = html.unescape(m.group(1)).strip() if m else ""
    return val

def matchs(lic):
    t = get(BASE + lic + "/matchs/?SORT=DAY_NUMBER")
    out, data, epreuve = [], "", ""
    for bloco in re.split(r"<li ", t)[1:]:
        if bloco.startswith('class="sep"'):
            spans = re.findall(r"<span>([^<]*)</span>", bloco)
            if len(spans) >= 2: data, epreuve = date_iso(html.unescape(spans[0])), html.unescape(spans[1]).strip()
            continue
        c = re.search(r'<small class="counter([^"]*)"[^>]*>([^<]*)</small>', bloco)
        if not c or not data: continue
        classes, pts = c.group(1), num(c.group(2))
        if pts is None: continue
        v = True if "pos" in classes else False if "neg" in classes else None
        out.append({"date": data, "epreuve": epreuve, "pts": pts, "v": v, "officiel": "not-official" not in classes})
    return out

def main(licences):
    os.makedirs("data", exist_ok=True)
    for lic in licences:
        lic = lic.strip()
        if not re.fullmatch(r"\d{5,8}", lic): continue
        f = fiche(lic); time.sleep(3); ms = matchs(lic)
        f.pop("nom", None)          # pas de nom dans le fichier public
        doc = {"licence": lic, "maj": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"), **f, "matchs": ms}
        json.dump(doc, open(f"data/{lic}.json", "w"), ensure_ascii=False, indent=1)
        nao = sum(m["pts"] for m in ms if not m["officiel"])
        print(lic, len(ms), "matchs;", f.get("mensuels"), "+", round(nao, 2), "=", round((f.get("mensuels") or 0) + nao, 1))
        time.sleep(5)

if __name__ == "__main__":
    main(sys.argv[1:] or open("licences.txt").read().split())
