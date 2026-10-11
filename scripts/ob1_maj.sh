#!/bin/bash
# Corre no ob1 (cron). Ping Pocket bloqueia os servidores do GitHub, por isso a recolha e' feita aqui e publicada no repo.
#   ob1_maj.sh novos  -> de 10 em 10 min: so' os pedidos "ajouter licence" abertos no GitHub (do dono do repo)
#   ob1_maj.sh todos  -> de manha e nas noites de fim de semana: todos os jogadores de licences.txt
set -e
cd /root/ping-virtual
exec 9>/tmp/ping-virtual.lock; flock -n 9 || exit 0
git pull -q --rebase
DONO=jppenixe-del
NOVOS=$(curl -s --max-time 30 "https://api.github.com/repos/$DONO/ping-virtual/issues?state=open&per_page=50" | python3 -c "
import sys, json, re
try: d = json.load(sys.stdin)
except Exception: d = []
for i in d if isinstance(d, list) else []:
    if i.get('user', {}).get('login') == '$DONO' and 'ajouter licence' in i.get('title', '').lower():
        m = re.search(r'\d{5,8}', i['title'])
        if m: print(m.group(0))" | sort -u)
for L in $NOVOS; do grep -qx "$L" licences.txt || echo "$L" >> licences.txt; done
if [ "$1" = "todos" ]; then
  python3 scripts/pingpocket.py
else
  FALTA=""; for L in $NOVOS; do [ -f "data/$L.json" ] || FALTA="$FALTA $L"; done
  [ -z "$FALTA" ] && exit 0
  python3 scripts/pingpocket.py $FALTA
fi
git add licences.txt data
git diff --cached --quiet && exit 0
git -c user.name="ping-virtual-bot" -c user.email="ping-virtual-bot@users.noreply.github.com" commit -qm "Mise à jour Ping Pocket"
git push -q
