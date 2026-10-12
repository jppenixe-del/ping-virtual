#!/usr/bin/env python3
"""Pre-carregamento das fichas mais abertas (ob1, cron 06:30 UTC, depois do top virtual): os 60 melhores Benjamins da
Bretanha pelos pontos mensais e os adversarios dos favoritos. Pede-as ao backoffice local, que as guarda em disco."""
import json, glob, os, time, urllib.request
CACHE = "/root/ping-virtual-cache"; REPO = "/root/ping-virtual"
lics = []
try:
    c = json.load(open(f"{CACHE}/classement_bretagne.json"))
    vistos = set()
    for j in sorted((j for j in c["joueurs"] if j["cat"].lower().startswith("benjamin") and not j.get("loisir")), key=lambda j: -j["pts"]):
        if j["lic"] not in vistos: vistos.add(j["lic"]); lics.append(j["lic"])
        if len(lics) >= 400: break      # todos os Benjamins com pontos (~350)
except OSError: pass
for f in glob.glob(f"{REPO}/data/[0-9]*.json"):
    for m in json.load(open(f))["matchs"]:
        if m.get("advLic") and m["advLic"] not in lics: lics.append(m["advLic"])
feitas = 0
for lic in lics:
    fx = f"{CACHE}/fiches/{lic}.json"
    if os.path.exists(fx) and time.time() - os.path.getmtime(fx) < 20*3600: continue
    try: os.remove(fx)                       # obriga a recalcular
    except OSError: pass
    try:
        urllib.request.urlopen(f"http://127.0.0.1:8790/api/joueur/{lic}/fiche", timeout=200).read(); feitas += 1
    except Exception as e: print("falhou", lic, e)
    time.sleep(1)
print(time.strftime("%F %T"), len(lics), "fichas;", feitas, "recalculadas")
