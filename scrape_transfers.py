#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-updater dei trasferimenti/prestiti REALI per MANAGER26.

Genera il file  data/market_updates.json  che il gioco legge in automatico
ogni 10 giorni reali. NON devi toccare nulla a mano: lo esegue la GitHub Action.

Fonte dati: API-FOOTBALL (https://www.api-sports.io/) -> piano FREE (100 richieste/giorno).
1) Crea un account gratis su api-sports.io e copia la tua API KEY.
2) Su GitHub, nel tuo repo del sito: Settings > Secrets and variables > Actions
   -> New repository secret:  nome = APISPORTS_KEY , valore = la tua chiave.
La GitHub Action fara' girare questo script da sola ogni 10 giorni.

Output: lista di mosse nel formato letto dal gioco:
  [{"player":"Nome","to":"Squadra destinazione","from":"Squadra origine","loan":true/false,"fee":12.0,"date":"2026-01-15"}]
"""
import os, json, time, datetime, urllib.request, urllib.parse

API_KEY = os.environ.get("APISPORTS_KEY", "").strip()
BASE = "https://v3.football.api-sports.io"
SEASON = int(os.environ.get("SEASON", datetime.date.today().year))
# leghe da monitorare (id API-Football). Riduci la lista se superi le 100 richieste/giorno.
# 135=Serie A, 39=Premier, 140=LaLiga, 78=Bundesliga, 61=Ligue1
LEAGUES = [int(x) for x in os.environ.get("LEAGUES", "135,39,140,78,61").split(",") if x.strip()]
DAYS_BACK = int(os.environ.get("DAYS_BACK", "20"))
MAX_CALLS = int(os.environ.get("MAX_CALLS", "95"))  # resta sotto il limite free giornaliero

# Mappa nomi API -> nomi usati nel database del gioco (aggiungine se qualche squadra non combacia)
NAME_MAP = {
  "Paris Saint Germain": "Paris SG", "Manchester United": "Manchester Utd",
  "Internazionale": "Inter", "Bayern Munchen": "Bayern Munich",
  "Borussia Dortmund": "Borussia Dortmund", "Atletico Madrid": "Atl\u00e9tico Madrid",
}

_calls = 0
def api(path, **params):
    global _calls
    if _calls >= MAX_CALLS:
        return None
    _calls += 1
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"x-apisports-key": API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("WARN api", path, params, e)
        return None

def mapname(n):
    return NAME_MAP.get(n, n)

def main():
    if not API_KEY:
        print("ERRORE: manca APISPORTS_KEY. Aggiungila come secret su GitHub.")
        # scrive comunque un file vuoto valido cosi' il gioco non da errore
        write([])
        return
    cutoff = datetime.date.today() - datetime.timedelta(days=DAYS_BACK)
    seen = set(); moves = []
    for lg in LEAGUES:
        data = api("/teams", league=lg, season=SEASON)
        if not data or not data.get("response"): continue
        for t in data["response"]:
            tid = t.get("team", {}).get("id")
            if not tid: continue
            tr = api("/transfers", team=tid)
            if not tr or not tr.get("response"): continue
            for row in tr["response"]:
                pname = (row.get("player") or {}).get("name")
                for mv in (row.get("transfers") or []):
                    d = mv.get("date") or ""
                    try:
                        dd = datetime.date.fromisoformat(d)
                    except Exception:
                        continue
                    if dd < cutoff: continue
                    tin = (mv.get("teams", {}).get("in") or {}).get("name")
                    tout = (mv.get("teams", {}).get("out") or {}).get("name")
                    if not pname or not tin: continue
                    typ = (mv.get("type") or "").lower()
                    is_loan = "loan" in typ or "prest" in typ
                    fee = 0.0
                    if "\u20ac" in typ or "m" in typ:
                        for tok in typ.replace("\u20ac"," ").replace("m"," ").split():
                            try: fee = float(tok.replace(",",".")); break
                            except: pass
                    key = (pname, tin, d)
                    if key in seen: continue
                    seen.add(key)
                    moves.append({"player": pname, "to": mapname(tin), "from": mapname(tout or ""),
                                  "loan": is_loan, "fee": round(fee,1), "date": d})
            time.sleep(0.2)
            if _calls >= MAX_CALLS: break
        if _calls >= MAX_CALLS: break
    write(moves)
    print("Scritti", len(moves), "trasferimenti reali (chiamate API:", _calls, ")")

def write(moves):
    os.makedirs("data", exist_ok=True)
    with open("data/market_updates.json", "w", encoding="utf-8") as f:
        json.dump(moves, f, ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
