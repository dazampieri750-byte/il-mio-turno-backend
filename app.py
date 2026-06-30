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
import json                                  # per impacchettare/spacchettare i dati JSON
from datetime import datetime
from flask import Flask, jsonify, request, Response   # request = legge i dati "nel pacco"

app = Flask(__name__)


# --- CORS: permette a una webapp (su un altro indirizzo) di chiamare questo server ---
# Senza questo, il browser bloccherebbe le chiamate dell'app verso onrender.com.
# Apriamo a tutti ("*") perche' il registro e' condiviso; si stringe col prodotto vero.
@app.after_request
def aggiungi_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


# Prima di un POST "vero", il browser manda una domanda di controllo (OPTIONS):
# "posso chiamarti?". Rispondiamo subito di si', cosi' poi parte la chiamata vera.
@app.before_request
def gestisci_preflight():
    if request.method == "OPTIONS":
        return Response(status=200)

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
        # registro variazioni: 'data' e' UNIQUE -> il database stesso
        # impedisce due righe con lo stesso giorno (rete di sicurezza del blocco)
        cur.execute(
            "CREATE TABLE IF NOT EXISTS variazioni ("
            " id SERIAL PRIMARY KEY,"
            " data TEXT UNIQUE,"
            " mappa TEXT,"
            " caricato_da TEXT,"
            " quando TIMESTAMP DEFAULT NOW())"
        )
    else:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS messaggi ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " testo TEXT,"
            " quando TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS variazioni ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " data TEXT UNIQUE,"
            " mappa TEXT,"
            " caricato_da TEXT,"
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


def data_valida(d):
    """Controlla che la data sia scritta come aaaa-mm-gg (es. 2026-06-28)."""
    try:
        datetime.strptime(d, "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


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


# =====================================================================
#  REGISTRO VARIAZIONI
#  Un "giorno" = una data (aaaa-mm-gg) + un blocco di dati (la "mappa"
#  delle variazioni, che il server NON apre: per lui e' una scatola
#  chiusa) + chi l'ha caricato.
#  Regola decisa: il primo che carica un giorno lo "congela" (blocco
#  doppioni). Per ora non si sovrascrive; piu' avanti aggiungeremo un
#  modo per aggiornare di proposito.
# =====================================================================

@app.route("/api/variazioni", methods=["GET", "POST"])
def api_variazioni():

    # --- POST: salva un giorno, con il BLOCCO se esiste gia' ---
    if request.method == "POST":
        dati = request.get_json(silent=True) or {}
        data = str(dati.get("data") or "").strip()
        mappa = dati.get("mappa")
        caricato_da = str(dati.get("caricato_da") or "").strip()

        if not data_valida(data):
            return jsonify({"stato": "errore",
                            "motivo": "data mancante o non valida (serve aaaa-mm-gg)"}), 400
        if mappa is None:
            return jsonify({"stato": "errore",
                            "motivo": "manca il campo 'mappa'"}), 400

        con = get_conn(); cur = con.cursor()

        # 1a difesa (il caso normale): guardo se il giorno c'e' gia'
        cur.execute(f"SELECT caricato_da FROM variazioni WHERE data = {PH}", (data,))
        gia_presente = cur.fetchone()
        if gia_presente:
            cur.close(); con.close()
            # codice 409 = "conflitto": esiste gia', non tocco niente
            return jsonify({"stato": "esiste",
                            "data": data,
                            "caricato_da": gia_presente[0] or ""}), 409

        # la mappa la trasformo in testo e la salvo cosi' com'e' (scatola chiusa)
        mappa_testo = json.dumps(mappa, ensure_ascii=False)
        try:
            cur.execute(
                f"INSERT INTO variazioni (data, mappa, caricato_da) "
                f"VALUES ({PH}, {PH}, {PH})",
                (data, mappa_testo, caricato_da)
            )
            con.commit()
        except Exception:
            # 2a difesa (rara): due caricamenti nello stesso istante.
            # Il vincolo UNIQUE sulla data fa fallire il secondo -> "esiste".
            con.rollback(); cur.close(); con.close()
            return jsonify({"stato": "esiste", "data": data}), 409
        cur.close(); con.close()
        return jsonify({"stato": "salvato", "data": data}), 201

    # --- GET (senza data): elenca i giorni presenti ---
    con = get_conn(); cur = con.cursor()
    cur.execute("SELECT data, caricato_da, quando FROM variazioni ORDER BY data DESC")
    righe = cur.fetchall(); cur.close(); con.close()
    giorni = [
        {"data": r[0], "caricato_da": r[1] or "", "quando": fmt_quando(r[2])}
        for r in righe
    ]
    return jsonify({"quanti": len(giorni), "giorni": giorni})


@app.route("/api/variazioni/<data>", methods=["GET", "PUT"])
def api_variazioni_giorno(data):
    """GET = legge UN giorno (es. /api/variazioni/2026-06-28).
    PUT = AGGIORNA/sovrascrive quel giorno di proposito (se non c'e', lo crea)."""
    if not data_valida(data):
        return jsonify({"stato": "errore",
                        "motivo": "data non valida (serve aaaa-mm-gg)"}), 400

    # --- PUT: rimpiazza il giorno (aggiornamento voluto, senza blocco) ---
    if request.method == "PUT":
        dati = request.get_json(silent=True) or {}
        mappa = dati.get("mappa")
        caricato_da = str(dati.get("caricato_da") or "").strip()
        if mappa is None:
            return jsonify({"stato": "errore", "motivo": "manca il campo 'mappa'"}), 400
        mappa_testo = json.dumps(mappa, ensure_ascii=False)
        adesso = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        con = get_conn(); cur = con.cursor()
        cur.execute(f"SELECT id FROM variazioni WHERE data = {PH}", (data,))
        if cur.fetchone():
            cur.execute(
                f"UPDATE variazioni SET mappa={PH}, caricato_da={PH}, quando={PH} WHERE data={PH}",
                (mappa_testo, caricato_da, adesso, data))
            stato = "aggiornato"
        else:
            cur.execute(
                f"INSERT INTO variazioni (data, mappa, caricato_da, quando) VALUES ({PH},{PH},{PH},{PH})",
                (data, mappa_testo, caricato_da, adesso))
            stato = "creato"
        con.commit(); cur.close(); con.close()
        return jsonify({"stato": stato, "data": data})

    # --- GET: legge il giorno ---
    con = get_conn(); cur = con.cursor()
    cur.execute(f"SELECT mappa, caricato_da, quando FROM variazioni WHERE data = {PH}", (data,))
    riga = cur.fetchone(); cur.close(); con.close()
    if not riga:
        # giorno non ancora caricato: rispondo in modo chiaro, senza errore
        return jsonify({"stato": "assente", "data": data, "mappa": None})
    mappa = json.loads(riga[0]) if riga[0] else None   # riapro la scatola per il cliente
    return jsonify({
        "stato": "ok",
        "data": data,
        "caricato_da": riga[1] or "",
        "quando": fmt_quando(riga[2]),
        "mappa": mappa
    })


# --- PAGINETTA DI PROVA del registro variazioni (servita dal server) ---
# La apri su /prova-registro. Scegli una data, metti una matricola e un
# turno di prova, e premi Salva. Riprova lo stesso giorno: vedrai il BLOCCO.
PAGINA_PROVA_REGISTRO = """
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Prova registro variazioni</title>
  <style>
    body { font-family: -apple-system, sans-serif; max-width: 640px;
           margin: 40px auto; padding: 0 16px; color: #222; }
    h1 { font-size: 22px; }
    label { display: inline-block; width: 90px; }
    input { padding: 8px; font-size: 16px; margin: 4px 0; }
    button { padding: 9px 14px; font-size: 15px; cursor: pointer; margin: 6px 6px 6px 0; }
    #esito { min-height: 22px; font-weight: bold; }
    pre { background: #f4f4f4; padding: 12px; border-radius: 6px; overflow:auto; }
  </style>
</head>
<body>
  <h1>Prova: registro variazioni</h1>
  <p>Salva un "giorno" di prova. Se riprovi lo stesso giorno, il server
     lo blocca (non sovrascrive).</p>

  <div><label>Data</label><input type="date" id="data"></div>
  <div><label>Matricola</label><input id="matr" placeholder="es. 12345"></div>
  <div><label>Turno</label><input id="turno" placeholder="es. 101"></div>

  <button onclick="salva()">Salva giorno</button>
  <button onclick="aggiorna()">Aggiorna (forza)</button>
  <button onclick="leggi()">Leggi questo giorno</button>
  <button onclick="elenca()">Elenca i giorni</button>

  <p id="esito"></p>
  <pre id="out"></pre>

  <script>
    function mostra(obj){ document.getElementById('out').textContent =
        JSON.stringify(obj, null, 2); }

    async function salva(){
      const data = document.getElementById('data').value;
      const matr = document.getElementById('matr').value.trim();
      const turno = document.getElementById('turno').value.trim();
      // costruisco una "mappa" di prova: { matricola: { turno: ... } }
      const mappa = {}; if (matr) mappa[matr] = { turno: turno };
      const r = await fetch('/api/variazioni', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data: data, mappa: mappa, caricato_da: matr })
      });
      const d = await r.json();
      const e = document.getElementById('esito');
      if (r.status === 201) e.textContent = '✓ Salvato il giorno ' + d.data;
      else if (r.status === 409) e.textContent =
        '⛔ Bloccato: il giorno ' + d.data + ' era gia stato caricato da ' + (d.caricato_da || 'qualcuno');
      else e.textContent = '⚠ ' + (d.motivo || 'errore');
      mostra(d);
    }

    async function aggiorna(){
      const data = document.getElementById('data').value;
      const matr = document.getElementById('matr').value.trim();
      const turno = document.getElementById('turno').value.trim();
      const mappa = {}; if (matr) mappa[matr] = { turno: turno };
      const r = await fetch('/api/variazioni/' + data, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mappa: mappa, caricato_da: matr })
      });
      const d = await r.json();
      document.getElementById('esito').textContent =
        (d.stato === 'aggiornato') ? ('✏️ Giorno ' + d.data + ' aggiornato (sovrascritto)')
        : (d.stato === 'creato') ? ('✓ Giorno ' + d.data + ' creato')
        : ('⚠ ' + (d.motivo || 'errore'));
      mostra(d);
    }

    async function leggi(){
      const data = document.getElementById('data').value;
      const r = await fetch('/api/variazioni/' + data);
      const d = await r.json();
      document.getElementById('esito').textContent =
        (d.stato === 'ok') ? ('Giorno ' + d.data + ' trovato') : ('Giorno ' + data + ': ' + d.stato);
      mostra(d);
    }

    async function elenca(){
      const r = await fetch('/api/variazioni');
      const d = await r.json();
      document.getElementById('esito').textContent = 'Giorni nel registro: ' + d.quanti;
      mostra(d);
    }
  </script>
</body>
</html>
"""


@app.route("/prova-registro")
def prova_registro():
    return PAGINA_PROVA_REGISTRO


# crea la tabella all'avvio (vale anche quando gira con gunicorn su Render)
try:
    init_db()
except Exception as e:
    print("Attenzione, init_db non riuscito:", e)


# serve solo per provare in locale sul tuo Mac
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
