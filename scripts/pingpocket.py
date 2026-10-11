#!/usr/bin/env python3
"""Va chercher sur Ping Pocket (pages publiques) les points et les matchs d'un licencié et écrit data/<licence>.json.
Une seule visite par licencié et par jour (lancé par .github/workflows/maj.yml): date, épreuve, adversaire, points
gagnés/perdus et s'ils sont déjà validés par la FFTT."""
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

def conserta(s):
    """alguns nomes vêm duplamente codificados na Ping Pocket (« RÃ©mi » em vez de « Rémi »)"""
    if "Ã" in s or "Â" in s:
        try: return s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError): pass
    return s

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
    m = re.search(r"<h1>([^<]+)</h1>", t); val["nom"] = conserta(html.unescape(m.group(1)).strip()) if m else ""
    info = re.search(r'<div class="info[^"]*">(.*?)</div>', t, re.S)
    if info:
        sp = [conserta(html.unescape(x).strip()) for x in re.findall(r"<span>([^<]*)</span>", info.group(1))]
        if len(sp) >= 3: val["categorie"], val["club"] = sp[0], sp[2]
    return val

def matchs(lic):
    t = get(BASE + lic + "/matchs/?SORT=DAY_NUMBER")
    out, data, epreuve = [], "", ""
    for bloco in re.split(r"<li ", t)[1:]:
        if bloco.startswith('class="sep"'):
            spans = re.findall(r"<span>([^<]*)</span>", bloco)
            if len(spans) >= 2: data, epreuve = date_iso(html.unescape(spans[0])), conserta(html.unescape(spans[1]).strip())
            continue
        c = re.search(r'<small class="counter([^"]*)"[^>]*>([^<]*)</small>', bloco)
        if not c or not data: continue
        classes, pts = c.group(1), num(c.group(2))
        if pts is None: continue
        pts = round(pts*8)/8          # a Ping Pocket mostra 1 casa decimal (3,8 para 3,75): os valores reais sao multiplos de 1/8
        v = True if "pos" in classes else False if "neg" in classes else None
        nome = re.search(r'<div class="labels">\s*<p>([^<]*)</p>', bloco)
        lk = re.search(r'href="/app/fftt/licencies/(\d+)"', bloco)
        out.append({"date": data, "epreuve": epreuve, "adv": conserta(html.unescape(nome.group(1)).strip()) if nome else "",
                    "pts": pts, "v": v, "officiel": "not-official" not in classes, "_lic": lk.group(1) if lk else ""})
    return out

TR = [(25, 6, -5, 6, -5), (50, 5.5, -4.5, 7, -6), (100, 5, -4, 8, -7), (150, 4, -3, 10, -8), (200, 3, -2, 13, -10),
      (300, 2, -1, 17, -12.5), (400, 1, -0.5, 22, -16), (500, 0.5, 0, 28, -20), (10**9, 0, 0, 40, -29)]
def base(moi, adv, v):
    e = abs(moi - adv); t = next(x for x in TR if e < x[0])
    return (t[1] if moi >= adv else t[3]) if v else (t[2] if moi <= adv else t[4])

def completa(ms, mens):
    """Jogos ainda em espera: pontos mensais do adversario (1 visita por adversario), vitoria/derrota nos jogos a 0
    e o coeficiente da prova deduzido dos pontos mostrados pela Ping Pocket (calculados com os pontos mensais)."""
    vistos = {}
    for m in ms:
        lic = m.pop("_lic", "")
        if m["officiel"] or not lic or not mens: continue
        if lic not in vistos:
            f = fiche(lic); vistos[lic] = f.get("mensuels"); time.sleep(3)
        adv = vistos[lic]
        if adv is None: continue
        m["advPts"] = adv
        if m["v"] is None: m["v"] = adv < mens          # 0 pontos: o favorito ganhou
        b = base(mens, adv, m["v"])
        if b: m["coef"] = round(m["pts"]/b, 3)
    for m in ms: m.pop("_lic", None)
    return ms

def indice():
    """data/index.json: os jogadores seguidos (para a lista da app)"""
    lista = []
    for nome in sorted(os.listdir("data")):
        if not re.fullmatch(r"\d+\.json", nome): continue
        d = json.load(open("data/" + nome))
        lista.append({k: d.get(k) for k in ("licence", "nom", "club", "categorie", "mensuels", "maj")})
    json.dump(lista, open("data/index.json", "w"), ensure_ascii=False, indent=1)

def main(licences):
    os.makedirs("data", exist_ok=True)
    for lic in licences:
        lic = lic.strip()
        if not re.fullmatch(r"\d{5,8}", lic): continue
        f = fiche(lic); time.sleep(3); ms = completa(matchs(lic), f.get("mensuels"))
        doc = {"licence": lic, "maj": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"), **f, "matchs": ms}
        json.dump(doc, open(f"data/{lic}.json", "w"), ensure_ascii=False, indent=1)
        val = sum(m["pts"] for m in ms if m["officiel"]); nao = sum(m["pts"] for m in ms if not m["officiel"])
        print(lic, len(ms), "matchs;", f.get("mensuels"), "+ validés", round(val, 2), "+ en attente", round(nao, 2))
        time.sleep(5)
    indice()

if __name__ == "__main__":
    main(sys.argv[1:] or open("licences.txt").read().split())
