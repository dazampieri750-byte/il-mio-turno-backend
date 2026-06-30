# =====================================================================
#  Il mio server — passo 3: parla anche in JSON e sceglie il database
# ---------------------------------------------------------------------
#  Novità di questo passo:
#   1) Il server capisce DA SOLO dove sta girando:
#        - sul tuo Mac (in locale)  -> usa un piccolo file SQLite
#        - su Render (online)       -> usa il Postgres vero
#      Tu non devi cambiare niente: il codice se ne accorge da solo.
#   2) Nuovo indirizzo /api/messaggi: come /elenco, ma risponde in JSON
#      (dati con etichette), cioe' nella "lingua" che capiscono le app.
# =====================================================================

import os
from datetime import datetime
from flask import Flask, jsonify, request   # request = legge i dati "nel pacco" della richiesta

app = Flask(__name__)

# L'indirizzo del database "vero" arriva da fuori (lo imposta Render).
# Sul tuo Mac questa variabile NON esiste, quindi resta None.
DATABASE_URL = os.environ.get("DATABASE_URL")

# Decidiamo quale database usare in base a DOVE gira il server:
#   - se DATABASE_URL esiste  -> siamo su Render -> Postgres
#   - se NON esiste           -> siamo sul Mac   -> file SQLite locale
USA_POSTGRES = bool(DATABASE_URL)

if USA_POSTGRES:
    import psycopg2
    PH = "%s"          # "segnaposto" per i valori, stile Postgres
else:
    import sqlite3      # SQLite e' gia' dentro Python: niente da installare
    PH = "?"           # "segnaposto" per i valori, stile SQLite
    DB_FILE = "locale.db"   # il mini-database: un semplice file accanto ad app.py


def get_conn():
    """Apre una connessione al database giusto (Postgres o SQLite)."""
    if USA_POSTGRES:
        return psycopg2.connect(DATABASE_URL)
    return sqlite3.connect(DB_FILE)


def init_db():
    """Crea la tabella 'messaggi' se non esiste ancora.
    La riga della tabella e' leggermente diversa tra i due database,
    quindi la scriviamo nei due modi."""
    con = get_conn(); cur = con.cursor()
    if USA_POSTGRES:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS messaggi ("
            " id SERIAL PRIMARY KEY,"
            " testo TEXT,"
            " quando TIMESTAMP DEFAULT NOW())"
        )
    else:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS messaggi ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " testo TEXT,"
            " quando TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
    con.commit(); cur.close(); con.close()


def fmt_quando(q):
    """Mostra la data/ora in modo leggibile.
    Postgres la restituisce gia' come data Python; SQLite come testo:
    questa funzione gestisce bene entrambi i casi."""
    if isinstance(q, datetime):
        return q.strftime("%d/%m %H:%M")
    try:
        return datetime.strptime(str(q)[:16], "%Y-%m-%d %H:%M").strftime("%d/%m %H:%M")
    except Exception:
        return str(q)


# --- indirizzi base ---
@app.route("/")
def home():
    return "Ciao! Il tuo server con database e' attivo. 🎉  Prova /scrivi/ciao e poi /elenco"


@app.route("/saluto/<nome>")
def saluto(nome):
    return f"Ciao {nome}, benvenuto nel tuo server!"


# --- PRIMO assaggio di JSON (una risposta sola, fissa) ---
@app.route("/api/ciao")
def api_ciao():
    return jsonify({
        "messaggio": "Ciao Davide",
        "stato": "ok",
        "tipo_risposta": "JSON"
    })


# --- SALVA un messaggio nel database (per ora ancora con GET, lo cambieremo) ---
@app.route("/scrivi/<testo>")
def scrivi(testo):
    con = get_conn(); cur = con.cursor()
    cur.execute(f"INSERT INTO messaggi (testo) VALUES ({PH})", (testo,))
    con.commit(); cur.close(); con.close()
    return f"Salvato nel database: «{testo}». Vai su /elenco oppure /api/messaggi."


# --- RILEGGE i messaggi, versione per UMANI (testo) ---
@app.route("/elenco")
def elenco():
    con = get_conn(); cur = con.cursor()
    cur.execute("SELECT testo, quando FROM messaggi ORDER BY id DESC")
    righe = cur.fetchall(); cur.close(); con.close()
    if not righe:
        return "Nessun messaggio salvato. Prova prima /scrivi/ciao"
    return "<br>".join(f"{fmt_quando(q)} — {t}" for (t, q) in righe)


# --- /api/messaggi: stesso indirizzo, due azioni decise dal "verbo" ---
#   GET  = dammi la lista dei messaggi (in JSON)
#   POST = aggiungi un messaggio (i dati arrivano "nel pacco", in JSON)
@app.route("/api/messaggi", methods=["GET", "POST"])
def api_messaggi():

    # --- POST: qualcuno ci CONSEGNA un messaggio da salvare ---
    if request.method == "POST":
        dati = request.get_json(silent=True) or {}   # leggo il JSON arrivato nel pacco
        testo = (dati.get("testo") or "").strip()     # prendo il campo "testo"
        if not testo:
            # niente testo? rispondo con un errore chiaro (codice 400 = richiesta sbagliata)
            return jsonify({"stato": "errore", "motivo": "manca il campo 'testo'"}), 400
        con = get_conn(); cur = con.cursor()
        cur.execute(f"INSERT INTO messaggi (testo) VALUES ({PH})", (testo,))
        con.commit(); cur.close(); con.close()
        # codice 201 = "creato": il modo giusto per dire "ho salvato la cosa nuova"
        return jsonify({"stato": "salvato", "testo": testo}), 201

    # --- GET: qualcuno ci CHIEDE la lista (come prima) ---
    con = get_conn(); cur = con.cursor()
    cur.execute("SELECT id, testo, quando FROM messaggi ORDER BY id DESC")
    righe = cur.fetchall(); cur.close(); con.close()
    messaggi = [
        {"id": r[0], "testo": r[1], "quando": fmt_quando(r[2])}
        for r in righe
    ]
    return jsonify({
        "quanti": len(messaggi),
        "messaggi": messaggi
    })


# --- PAGINETTA DI PROVA (servita dal server stesso) ---
# La apri su /prova. Ha una casella e un bottone "Salva": quando clicchi,
# manda il messaggio al server con un POST (nel pacco) e poi ricarica la lista.
# E' un piccolo esempio di come la tua APP vera parlera' col server.
PAGINA_PROVA = """
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Prova messaggi</title>
  <style>
    body { font-family: -apple-system, sans-serif; max-width: 600px;
           margin: 40px auto; padding: 0 16px; color: #222; }
    h1 { font-size: 22px; }
    input { padding: 10px; width: 70%; font-size: 16px; }
    button { padding: 10px 16px; font-size: 16px; cursor: pointer; }
    #esito { min-height: 20px; color: #0a7d28; }
    ul { padding-left: 18px; }
    li { margin: 4px 0; }
  </style>
</head>
<body>
  <h1>Prova: salva un messaggio</h1>
  <p>Scrivi qualcosa e premi Salva. Il messaggio viene mandato al server
     con un POST, non nell'indirizzo.</p>
  <input id="testo" placeholder="Scrivi qui...">
  <button onclick="salva()">Salva</button>
  <p id="esito"></p>

  <h2>Messaggi salvati</h2>
  <ul id="lista"></ul>

  <script>
    // manda il messaggio al server con un POST
    async function salva() {
      const testo = document.getElementById('testo').value;
      const r = await fetch('/api/messaggi', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ testo: testo })   // il "pacco" in JSON
      });
      const d = await r.json();
      document.getElementById('esito').textContent =
        r.ok ? ('Salvato: ' + d.testo) : ('Errore: ' + (d.motivo || ''));
      document.getElementById('testo').value = '';
      carica();   // ricarico la lista aggiornata
    }
    // chiede al server la lista (GET) e la mostra
    async function carica() {
      const r = await fetch('/api/messaggi');
      const d = await r.json();
      const ul = document.getElementById('lista');
      ul.innerHTML = '';
      d.messaggi.forEach(function (m) {
        const li = document.createElement('li');
        li.textContent = m.quando + ' — ' + m.testo;
        ul.appendChild(li);
      });
    }
    carica();   // appena apro la pagina, mostro subito i messaggi gia' salvati
  </script>
</body>
</html>
"""


@app.route("/prova")
def prova():
    return PAGINA_PROVA


# crea la tabella all'avvio (vale anche quando gira con gunicorn su Render)
try:
    init_db()
except Exception as e:
    print("Attenzione, init_db non riuscito:", e)


# serve solo per provare in locale sul tuo Mac
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
