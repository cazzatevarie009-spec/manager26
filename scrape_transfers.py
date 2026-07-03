#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-updater trasferimenti/prestiti REALI per MANAGER26 (versione con DIAGNOSTICA).
Genera  data/market_updates.json  che il gioco legge da solo.

IMPORTANTISSIMO sulla chiave:
- Deve essere la chiave del sito DIRETTO  https://dashboard.api-football.com/ (api-sports.io),
  NON quella di RapidAPI. Con RapidAPI l'host e gli header sono diversi e non funziona.
- Mettila come secret GitHub:  APISPORTS_KEY

Lo script stampa nel log dell'Action: stato del piano, errori API, quante squadre e
quanti trasferimenti trova. Se qualcosa non va, il log te lo dice.
"""
import os, json, time, datetime, urllib.request, urllib.parse, urllib.error

KEY = os.environ.get("APISPORTS_KEY", "").strip()
BASE = "https://v3.football.api-sports.io"
today = datetime.date.today()
# stagione calcistica: da luglio in poi = anno corrente, altrimenti anno-1
SEASON = int(os.environ.get("SEASON", str(today.year if today.month >= 7 else today.year - 1)))
LEAGUES = [int(x) for x in os.environ.get("LEAGUES", "135,39,140,78,61").split(",") if x.strip()]
DAYS_BACK = int(os.environ.get("DAYS_BACK", "60"))
MAX_CALLS = int(os.environ.get("MAX_CALLS", "95"))

NAME_MAP = {
  "Paris Saint Germain": "Paris SG", "Manchester United": "Manchester Utd",
  "Internazionale": "Inter", "Atletico Madrid": "Atl\u00e9tico Madrid",
  "Barcelona": "FC Barcelona", "Bayern M\u00fcnchen": "Bayern Munich",
}

_calls = 0
def api(path, **params):
    global _calls
    if _calls >= MAX_CALLS:
        print("  (stop: raggiunto MAX_CALLS)"); return {}, 0
    _calls += 1
    url = BASE + path + (("?" + urllib.parse.urlencode(params)) if params else "")
    req = urllib.request.Request(url, headers={"x-apisports-key": KEY, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8")), r.status
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode("utf-8")
        except Exception: pass
        return {"_http": e.code, "_body": body[:300]}, e.code
    except Exception as e:
        return {"_err": str(e)}, 0

def mapname(n):
    n = (n or "").strip()
    return NAME_MAP.get(n, n)

def write(moves):
    os.makedirs("data", exist_ok=True)
    with open("data/market_updates.json", "w", encoding="utf-8") as f:
        json.dump(moves, f, ensure_ascii=False, indent=1)

def main():
    print("=== MANAGER26 transfer updater ===")
    print("Data:", today, "| Stagione usata:", SEASON, "| Leghe:", LEAGUES, "| Giorni indietro:", DAYS_BACK)
    print("APISPORTS_KEY presente:", bool(KEY), "| lunghezza:", len(KEY))
    if not KEY:
        print("ERRORE: manca la chiave APISPORTS_KEY (secret GitHub). Scrivo file vuoto.")
        write([]); return

    st, code = api("/status")
    print("/status HTTP:", code)
    print("/status risposta:", json.dumps(st.get("response", st), ensure_ascii=False)[:600])
    if st.get("errors"):
        print("ATTENZIONE /status errors:", st["errors"])
        print(">>> Se qui vedi un errore di 'token'/'plan', la chiave e' sbagliata (forse di RapidAPI) o il piano non copre questi dati.")

    cutoff = today - datetime.timedelta(days=DAYS_BACK)
    seen = set(); moves = []; tot_teams = 0; tot_tr = 0

    def gather(season):
        nonlocal tot_teams, tot_tr
        found_any = False
        for lg in LEAGUES:
            if _calls >= MAX_CALLS: break
            data, c = api("/teams", league=lg, season=season)
            resp = data.get("response") or []
            if data.get("errors"): print("  /teams league", lg, "errors:", data["errors"])
            print("  Lega", lg, "stagione", season, "-> squadre trovate:", len(resp))
            if resp: found_any = True
            for t in resp:
                if _calls >= MAX_CALLS: break
                tid = (t.get("team") or {}).get("id")
                if not tid: continue
                tot_teams += 1
                tr, c2 = api("/transfers", team=tid)
                rows = tr.get("response") or []
                for row in rows:
                    pname = (row.get("player") or {}).get("name")
                    for mv in (row.get("transfers") or []):
                        tot_tr += 1
                        d = mv.get("date") or ""
                        try: dd = datetime.date.fromisoformat(d)
                        except Exception: continue
                        if dd < cutoff: continue
                        tin = ((mv.get("teams") or {}).get("in") or {}).get("name")
                        tout = ((mv.get("teams") or {}).get("out") or {}).get("name")
                        if not pname or not tin: continue
                        typ = (mv.get("type") or "").lower()
                        is_loan = ("loan" in typ) or ("prest" in typ)
                        fee = 0.0
                        for tok in typ.replace("\u20ac", " ").replace("m", " ").split():
                            try: fee = float(tok.replace(",", ".")); break
                            except Exception: pass
                        key = (pname, tin, d)
                        if key in seen: continue
                        seen.add(key)
                        moves.append({"player": pname, "to": mapname(tin), "from": mapname(tout or ""),
                                      "loan": is_loan, "fee": round(fee, 1), "date": d})
                time.sleep(0.15)
        return found_any

    ok = gather(SEASON)
    if not ok and _calls < MAX_CALLS:
        print("Nessuna squadra per la stagione", SEASON, "- riprovo con", SEASON - 1)
        gather(SEASON - 1)

    print("RIEPILOGO -> squadre lette:", tot_teams, "| transfer grezzi:", tot_tr,
          "| mosse recenti (ultimi", DAYS_BACK, "gg):", len(moves), "| chiamate API:", _calls)
    if not moves:
        print(">>> Nessuna mossa recente trovata. Possibili cause: piano API senza dati sulla stagione,")
        print(">>> nessun trasferimento negli ultimi", DAYS_BACK, "giorni, o chiave non valida (vedi /status sopra).")
    write(moves)
    print("Scritto data/market_updates.json con", len(moves), "mosse.")

if __name__ == "__main__":
    main()
