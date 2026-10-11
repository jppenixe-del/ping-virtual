#!/usr/bin/env python3
"""Top por pontos virtuais (corre no ob1 todos os dias, depois da atualizacao da manha). Para cada categoria de
CATEGORIAS pega nos N melhores da Bretanha pelos pontos mensais (classement_bretagne.json) e calcula os virtuais como a
app: mensais + jogos validados + jogos em espera recalculados com (mensais + validados) e os pontos dos adversarios.
Fica em /root/ping-virtual-cache/top_virtuel.json (fora do GitHub); servido por /api/classement?mode=virtuel."""
import json, os, sys, time, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pingpocket as pp

CACHE = "/root/ping-virtual-cache"
CATEGORIAS = {"Benjamin": 25}          # prefixo da categoria -> quantos jogadores (os melhores pelos pontos mensais)

def virtuais(lic, adv_cache):
    f = pp.fiche(lic); time.sleep(1.5)
    ms = pp.completa(pp.matchs(lic), f.get("mensuels"), adv_cache); time.sleep(1.5)
    mens = f.get("mensuels") or 0
    val = sum(m["pts"] for m in ms if m["officiel"]); ref = mens + val
    pend = 0.0
    for m in ms:
        if m["officiel"]: continue
        if m.get("advPts") is not None and m.get("v") is not None:
            pend += pp.base(ref, m["advPts"], m["v"])*m.get("coef", 1)
        else: pend += m["pts"]
    return {"mensuels": mens, "valides": round(val, 3), "attente": round(pend, 3), "virtuels": round(ref + pend, 2), "matchs": len(ms)}

def main():
    clas = json.load(open(f"{CACHE}/classement_bretagne.json"))
    adv = {}; saida = {"maj": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "categories": {}}
    antigo = {}
    try: antigo = json.load(open(f"{CACHE}/top_virtuel.json")).get("categories", {})
    except OSError: pass
    for cat, n in CATEGORIAS.items():
        vistos, base = set(), []
        for j in sorted((j for j in clas["joueurs"] if j["cat"].lower().startswith(cat.lower())), key=lambda j: -j["pts"]):
            if j["lic"] in vistos: continue
            vistos.add(j["lic"]); base.append(j)
            if len(base) >= n: break
        lista = []
        for j in base:
            try: v = virtuais(j["lic"], adv)
            except SystemExit as e:
                print("falhou", j["lic"], e, file=sys.stderr)
                v = next((x for x in antigo.get(cat, []) if x["lic"] == j["lic"]), None)
                if not v: continue
            lista.append({**{k: j[k] for k in ("lic", "nom", "club", "cat", "sexe", "dep")}, **{k: v[k] for k in ("mensuels", "valides", "attente", "virtuels", "matchs")}})
            print(cat, j["nom"], v["virtuels"], flush=True)
        saida["categories"][cat] = lista
    tmp = f"{CACHE}/top_virtuel.json.tmp"; json.dump(saida, open(tmp, "w"), ensure_ascii=False); os.replace(tmp, f"{CACHE}/top_virtuel.json")

if __name__ == "__main__":
    main()
