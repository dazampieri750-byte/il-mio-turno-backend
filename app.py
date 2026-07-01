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
import secrets                               # per generare i "gettoni" (token) di accesso
from datetime import datetime
from zoneinfo import ZoneInfo                # per convertire l'ora UTC in ora italiana
from flask import Flask, jsonify, request, Response   # request = legge i dati "nel pacco"
from werkzeug.security import generate_password_hash, check_password_hash  # password protette

# fuso orario italiano (gestisce da solo ora legale/solare)
FUSO_ITALIA = ZoneInfo("Europe/Rome")

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
        # guasti: lista di segnalazioni (nessun blocco). id_client UNIQUE = anti-doppione
        cur.execute(
            "CREATE TABLE IF NOT EXISTS guasti ("
            " id SERIAL PRIMARY KEY,"
            " id_client TEXT UNIQUE,"
            " mezzo TEXT,"
            " data TEXT,"
            " tipo TEXT,"
            " nota TEXT,"
            " segnalato_da TEXT,"
            " quando TIMESTAMP DEFAULT NOW())"
        )
        # diario dei mezzi usati (storico personale per matricola)
        cur.execute(
            "CREATE TABLE IF NOT EXISTS mezzi_usati ("
            " id SERIAL PRIMARY KEY,"
            " id_client TEXT UNIQUE,"
            " matricola TEXT,"
            " data TEXT,"
            " turno TEXT,"
            " pezzo TEXT,"
            " ora_inizio TEXT,"
            " ora_fine TEXT,"
            " mezzo TEXT,"
            " nota TEXT,"
            " quando TIMESTAMP DEFAULT NOW())"
        )
        # elenco matricole valide (chi puo' registrarsi), separato per azienda
        cur.execute(
            "CREATE TABLE IF NOT EXISTS matricole_valide ("
            " id SERIAL PRIMARY KEY,"
            " azienda_id INTEGER,"
            " matricola TEXT,"
            " attiva BOOLEAN DEFAULT TRUE,"
            " aggiornata TIMESTAMP DEFAULT NOW(),"
            " UNIQUE (azienda_id, matricola))"
        )
        # utenti registrati (password SEMPRE hashata). Ogni utente appartiene a
        # un'azienda (il master ha azienda_id NULL). La stessa matricola puo'
        # esistere in aziende diverse -> unica solo dentro la stessa azienda.
        cur.execute(
            "CREATE TABLE IF NOT EXISTS utenti ("
            " id SERIAL PRIMARY KEY,"
            " azienda_id INTEGER,"
            " matricola TEXT,"
            " password_hash TEXT,"
            " ruolo TEXT DEFAULT 'autista',"
            " attivo BOOLEAN DEFAULT TRUE,"
            " creato TIMESTAMP DEFAULT NOW(),"
            " UNIQUE (azienda_id, matricola))"
        )
        # sessioni: il "gettone" (token) che identifica chi ha fatto il login
        cur.execute(
            "CREATE TABLE IF NOT EXISTS sessioni ("
            " token TEXT PRIMARY KEY,"
            " matricola TEXT,"
            " azienda_id INTEGER,"
            " ruolo TEXT,"
            " creato TIMESTAMP DEFAULT NOW())"
        )
        # aziende (i clienti della piattaforma): ogni dato apparterra' a un'azienda
        cur.execute(
            "CREATE TABLE IF NOT EXISTS aziende ("
            " id SERIAL PRIMARY KEY,"
            " nome TEXT,"
            " attiva BOOLEAN DEFAULT TRUE,"
            " creata TIMESTAMP DEFAULT NOW())"
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
        cur.execute(
            "CREATE TABLE IF NOT EXISTS guasti ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " id_client TEXT UNIQUE,"
            " mezzo TEXT,"
            " data TEXT,"
            " tipo TEXT,"
            " nota TEXT,"
            " segnalato_da TEXT,"
            " quando TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS mezzi_usati ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " id_client TEXT UNIQUE,"
            " matricola TEXT,"
            " data TEXT,"
            " turno TEXT,"
            " pezzo TEXT,"
            " ora_inizio TEXT,"
            " ora_fine TEXT,"
            " mezzo TEXT,"
            " nota TEXT,"
            " quando TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS matricole_valide ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " azienda_id INTEGER,"
            " matricola TEXT,"
            " attiva INTEGER DEFAULT 1,"
            " aggiornata TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            " UNIQUE (azienda_id, matricola))"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS utenti ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " azienda_id INTEGER,"
            " matricola TEXT,"
            " password_hash TEXT,"
            " ruolo TEXT DEFAULT 'autista',"
            " attivo INTEGER DEFAULT 1,"
            " creato TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            " UNIQUE (azienda_id, matricola))"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS sessioni ("
            " token TEXT PRIMARY KEY,"
            " matricola TEXT,"
            " azienda_id INTEGER,"
            " ruolo TEXT,"
            " creato TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS aziende ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " nome TEXT,"
            " attiva INTEGER DEFAULT 1,"
            " creata TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
    # migrazione: aggiunge ai guasti le colonne di INVIO anche se la tabella
    # esisteva gia' (cosi' non serve ricreare il database)
    nuove_colonne = [("stato", "TEXT DEFAULT 'nuovo'"),
                     ("inviato_quando", "TIMESTAMP"),
                     ("inviato_da", "TEXT")]
    for col, tipo in nuove_colonne:
        try:
            if USA_POSTGRES:
                cur.execute(f"ALTER TABLE guasti ADD COLUMN IF NOT EXISTS {col} {tipo}")
            else:
                cur.execute("PRAGMA table_info(guasti)")
                esistenti = [r[1] for r in cur.fetchall()]
                if col not in esistenti:
                    cur.execute(f"ALTER TABLE guasti ADD COLUMN {col} {tipo}")
        except Exception as e:
            print("migrazione guasti:", e)
    con.commit(); cur.close(); con.close()


def fmt_quando(q):
    """Mostra la data/ora in modo leggibile e in ORA ITALIANA.
    Nel database il tempo e' salvato in UTC (standard mondiale); qui lo
    convertiamo nel fuso italiano. Gestisce sia il formato di Postgres
    (data Python) sia quello di SQLite (testo)."""
    if isinstance(q, datetime):
        dt = q
    else:
        dt = None
        for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                dt = datetime.strptime(str(q)[:19], formato); break
            except Exception:
                continue
        if dt is None:
            return str(q)
    try:
        # il tempo salvato e' UTC -> lo convertiamo in ora italiana
        dt = dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(FUSO_ITALIA)
    except Exception:
        pass
    return dt.strftime("%d/%m %H:%M")


def data_valida(d):
    """Controlla che la data sia scritta come aaaa-mm-gg (es. 2026-06-28)."""
    try:
        datetime.strptime(d, "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def registra_matricole(matricole, azienda_id):
    """Aggiunge le matricole all'elenco valide DI QUELL'AZIENDA (se non ci sono).
    NON toglie mai nessuno (i dimissionari li rimuove l'amministratore a mano)."""
    if not azienda_id:
        return
    puliti = [str(m).strip() for m in (matricole or []) if str(m).strip()]
    if not puliti:
        return
    con = get_conn(); cur = con.cursor()
    for m in puliti:
        try:
            if USA_POSTGRES:
                cur.execute("INSERT INTO matricole_valide (azienda_id, matricola) VALUES (%s,%s) "
                            "ON CONFLICT (azienda_id, matricola) DO NOTHING", (azienda_id, m))
            else:
                cur.execute("INSERT OR IGNORE INTO matricole_valide (azienda_id, matricola) VALUES (?,?)",
                            (azienda_id, m))
        except Exception as e:
            print("registra_matricole:", e)
    con.commit(); cur.close(); con.close()


def matricola_e_valida(m, azienda_id):
    """Vero se la matricola e' valida e attiva PER quell'azienda (puo' registrarsi)."""
    m = str(m or "").strip()
    if not m or not azienda_id:
        return False
    con = get_conn(); cur = con.cursor()
    if USA_POSTGRES:
        cur.execute("SELECT 1 FROM matricole_valide WHERE azienda_id=%s AND matricola=%s AND attiva",
                    (azienda_id, m))
    else:
        cur.execute("SELECT 1 FROM matricole_valide WHERE azienda_id=? AND matricola=? AND attiva=1",
                    (azienda_id, m))
    ok = cur.fetchone() is not None
    cur.close(); con.close()
    return ok


def utente_corrente():
    """Chi ha fatto il login? Legge il 'gettone' (token) dalla richiesta e
    ritorna {matricola, ruolo}, oppure None se non c'e' o non e' valido."""
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip() if auth else ""
    if not token:
        token = (request.args.get("token") or "").strip()   # comodo per le prove nel browser
    if not token:
        return None
    con = get_conn(); cur = con.cursor()
    cur.execute(f"SELECT matricola, azienda_id, ruolo FROM sessioni WHERE token = {PH}", (token,))
    riga = cur.fetchone(); cur.close(); con.close()
    if not riga:
        return None
    return {"matricola": riga[0], "azienda_id": riga[1], "ruolo": riga[2]}


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


# =====================================================================
#  GUASTI — segnalazioni guasti mezzi (lista condivisa, senza blocco)
#   GET  = dammi tutte le segnalazioni
#   POST = aggiungi una segnalazione {mezzo, data, tipo, nota, segnalato_da, id}
#  L'id (generato dall'app) serve a NON registrare due volte lo stesso guasto.
# =====================================================================

@app.route("/api/guasti", methods=["GET", "POST"])
def api_guasti():

    # --- POST: aggiungi una segnalazione ---
    if request.method == "POST":
        dati = request.get_json(silent=True) or {}
        mezzo = str(dati.get("mezzo") or "").strip()
        data = str(dati.get("data") or "").strip()
        tipo = str(dati.get("tipo") or "").strip()
        nota = str(dati.get("nota") or "").strip()
        segnalato_da = str(dati.get("segnalato_da") or "").strip()
        id_client = str(dati.get("id") or "").strip()

        if not mezzo:
            return jsonify({"stato": "errore", "motivo": "manca il mezzo"}), 400
        if not data_valida(data):
            return jsonify({"stato": "errore",
                            "motivo": "data mancante o non valida (aaaa-mm-gg)"}), 400
        if not id_client:   # se l'app non manda un id, lo creiamo noi
            id_client = datetime.utcnow().strftime("g%Y%m%d%H%M%S%f")

        con = get_conn(); cur = con.cursor()
        # anti-doppione: se questo id c'e' gia', non lo reinserisco
        cur.execute(f"SELECT id FROM guasti WHERE id_client = {PH}", (id_client,))
        if cur.fetchone():
            cur.close(); con.close()
            return jsonify({"stato": "gia_presente", "id": id_client})
        try:
            cur.execute(
                f"INSERT INTO guasti (id_client, mezzo, data, tipo, nota, segnalato_da) "
                f"VALUES ({PH},{PH},{PH},{PH},{PH},{PH})",
                (id_client, mezzo, data, tipo, nota, segnalato_da))
            con.commit()
        except Exception:
            con.rollback(); cur.close(); con.close()
            return jsonify({"stato": "gia_presente", "id": id_client})
        cur.close(); con.close()
        return jsonify({"stato": "salvato", "id": id_client}), 201

    # --- GET: elenca tutte le segnalazioni (con stato di invio) ---
    con = get_conn(); cur = con.cursor()
    cur.execute("SELECT id_client, mezzo, data, tipo, nota, segnalato_da, quando, "
                "stato, inviato_quando, inviato_da "
                "FROM guasti ORDER BY data DESC, id DESC")
    righe = cur.fetchall(); cur.close(); con.close()
    guasti = [
        {"id": r[0], "mezzo": r[1], "data": r[2], "tipo": r[3],
         "nota": r[4], "segnalato_da": r[5],
         "quando": fmt_quando(r[6]),                                   # data segnalazione
         "stato": r[7] or "nuovo",
         "inviato_quando": fmt_quando(r[8]) if r[8] else None,         # data invio officina
         "inviato_da": r[9] or ""}
        for r in righe
    ]
    return jsonify({"quanti": len(guasti), "guasti": guasti})


# --- INVIA un guasto all'officina (per ora segna solo lo stato; il canale
#     reale verso il gestionale si collega in futuro) ---
@app.route("/api/guasti/<id_client>/invia", methods=["POST"])
def api_guasti_invia(id_client):
    dati = request.get_json(silent=True) or {}
    inviato_da = str(dati.get("inviato_da") or "").strip()
    adesso = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    con = get_conn(); cur = con.cursor()
    cur.execute(f"SELECT stato FROM guasti WHERE id_client = {PH}", (id_client,))
    riga = cur.fetchone()
    if not riga:
        cur.close(); con.close()
        return jsonify({"stato": "errore", "motivo": "guasto non trovato"}), 404
    if (riga[0] or "") == "inviato":
        cur.close(); con.close()
        return jsonify({"stato": "gia_inviato", "id": id_client})
    cur.execute(
        f"UPDATE guasti SET stato='inviato', inviato_quando={PH}, inviato_da={PH} "
        f"WHERE id_client={PH}",
        (adesso, inviato_da, id_client))
    con.commit(); cur.close(); con.close()
    return jsonify({"stato": "inviato", "id": id_client})


# =====================================================================
#  MATRICOLE VALIDE — l'elenco di chi potra' registrarsi.
#   GET  = vedi l'elenco
#   POST {matricole:[...]} = aggiungi a mano un elenco (es. caricamento iniziale)
#  Si aggiorna anche DA SOLO ad ogni caricamento di variazioni.
# =====================================================================
@app.route("/api/matricole", methods=["GET", "POST"])
def api_matricole():
    if request.method == "POST":
        u = utente_corrente()
        if not u or u["ruolo"] not in ("master", "azienda"):
            return jsonify({"stato": "errore", "motivo": "serve un account master o azienda"}), 403
        dati = request.get_json(silent=True) or {}
        # l'azienda usa la propria; il master indica quale
        grezzo = u["azienda_id"] if u["ruolo"] == "azienda" else dati.get("azienda_id")
        try:
            azienda_id = int(grezzo)
        except (TypeError, ValueError):
            azienda_id = None
        if not azienda_id:
            return jsonify({"stato": "errore", "motivo": "manca l'azienda"}), 400
        elenco = dati.get("matricole") or []
        registra_matricole(elenco, azienda_id)
        return jsonify({"stato": "ok", "azienda_id": azienda_id, "ricevute": len(elenco)})

    # GET: elenco delle matricole di una azienda (?azienda_id=)
    try:
        azienda_id = int(request.args.get("azienda_id"))
    except (TypeError, ValueError):
        azienda_id = None
    if not azienda_id:
        return jsonify({"quante": 0, "matricole": [], "nota": "indica ?azienda_id="})
    con = get_conn(); cur = con.cursor()
    if USA_POSTGRES:
        cur.execute("SELECT matricola FROM matricole_valide WHERE azienda_id=%s AND attiva ORDER BY matricola",
                    (azienda_id,))
    else:
        cur.execute("SELECT matricola FROM matricole_valide WHERE azienda_id=? AND attiva=1 ORDER BY matricola",
                    (azienda_id,))
    righe = cur.fetchall(); cur.close(); con.close()
    matricole = [r[0] for r in righe]
    return jsonify({"quante": len(matricole), "matricole": matricole})


# =====================================================================
#  ACCOUNT — registrazione (matricola valida + password protetta)
# =====================================================================
@app.route("/api/registrati", methods=["POST"])
def api_registrati():
    dati = request.get_json(silent=True) or {}
    try:
        azienda_id = int(dati.get("azienda_id"))
    except (TypeError, ValueError):
        azienda_id = None
    matricola = str(dati.get("matricola") or "").strip()
    password = str(dati.get("password") or "")

    if not azienda_id:
        return jsonify({"stato": "errore", "motivo": "scegli l'azienda"}), 400
    if not matricola:
        return jsonify({"stato": "errore", "motivo": "manca la matricola"}), 400
    if len(password) < 6:
        return jsonify({"stato": "errore",
                        "motivo": "la password deve avere almeno 6 caratteri"}), 400
    # la matricola deve risultare tra i dipendenti DI QUELL'AZIENDA
    if not matricola_e_valida(matricola, azienda_id):
        return jsonify({"stato": "errore",
                        "motivo": "matricola non riconosciuta per questa azienda"}), 403

    con = get_conn(); cur = con.cursor()
    cur.execute(f"SELECT id FROM utenti WHERE azienda_id={PH} AND matricola={PH}", (azienda_id, matricola))
    if cur.fetchone():
        cur.close(); con.close()
        return jsonify({"stato": "gia_registrato",
                        "motivo": "questa matricola ha gia' un account in questa azienda"}), 409
    # la password NON viene mai salvata leggibile: salviamo solo la sua "impronta"
    ph = generate_password_hash(password)
    cur.execute(f"INSERT INTO utenti (azienda_id, matricola, password_hash, ruolo) "
                f"VALUES ({PH},{PH},{PH},'autista')", (azienda_id, matricola, ph))
    con.commit(); cur.close(); con.close()
    return jsonify({"stato": "registrato", "matricola": matricola,
                    "azienda_id": azienda_id, "ruolo": "autista"}), 201


# --- PAGINETTA DI PROVA della registrazione ---
PAGINA_PROVA_REGISTRAZIONE = """
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Prova registrazione</title>
  <style>
    body { font-family: -apple-system, sans-serif; max-width: 480px;
           margin: 40px auto; padding: 0 16px; color: #222; }
    h1 { font-size: 22px; }
    label { display: inline-block; width: 90px; }
    input { padding: 9px; font-size: 16px; margin: 5px 0; width: 60%; }
    button { padding: 10px 16px; font-size: 15px; cursor: pointer; margin-top: 8px; }
    #esito { min-height: 22px; font-weight: bold; margin-top: 12px; }
  </style>
</head>
<body>
  <h1>Prova: crea un account</h1>
  <p>Scegli l'azienda e inserisci una matricola che risulti tra i suoi dipendenti.</p>
  <div><label>Azienda</label><select id="az"></select></div>
  <div><label>Matricola</label><input id="matr" placeholder="es. 111"></div>
  <div><label>Password</label><input id="pwd" type="password" placeholder="almeno 6 caratteri"></div>
  <button onclick="registrati()">Registrati</button>
  <p id="esito"></p>

  <script>
    async function caricaAziende(){
      const r = await fetch('/api/aziende'); const d = await r.json();
      const s = document.getElementById('az'); s.innerHTML = '';
      (d.aziende||[]).forEach(function(a){ const o=document.createElement('option'); o.value=a.id; o.textContent=a.nome; s.appendChild(o); });
    }
    caricaAziende();
    async function registrati(){
      const r = await fetch('/api/registrati', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          azienda_id: document.getElementById('az').value,
          matricola: document.getElementById('matr').value.trim(),
          password: document.getElementById('pwd').value
        })
      });
      const d = await r.json();
      const e = document.getElementById('esito');
      if (d.stato === 'registrato') e.textContent = '✓ Account creato per la matricola ' + d.matricola + ' (ruolo: ' + d.ruolo + ')';
      else if (d.stato === 'gia_registrato') e.textContent = 'ℹ ' + (d.motivo || 'ha già un account');
      else e.textContent = '⚠ ' + (d.motivo || 'errore');
    }
  </script>
</body>
</html>
"""


@app.route("/prova-registrazione")
def prova_registrazione():
    return PAGINA_PROVA_REGISTRAZIONE


# =====================================================================
#  LOGIN — verifica password e rilascia un "gettone" (token)
# =====================================================================
@app.route("/api/login", methods=["POST"])
def api_login():
    dati = request.get_json(silent=True) or {}
    matricola = str(dati.get("matricola") or "").strip()
    password = str(dati.get("password") or "")
    if not matricola or not password:
        return jsonify({"stato": "errore", "motivo": "servono matricola e password"}), 400

    try:
        azienda_id = int(dati.get("azienda_id"))   # assente/None = login del master
    except (TypeError, ValueError):
        azienda_id = None
    con = get_conn(); cur = con.cursor()
    if azienda_id:
        cur.execute(f"SELECT password_hash, ruolo, attivo, azienda_id FROM utenti "
                    f"WHERE azienda_id={PH} AND matricola={PH}", (azienda_id, matricola))
    else:
        cur.execute(f"SELECT password_hash, ruolo, attivo, azienda_id FROM utenti "
                    f"WHERE azienda_id IS NULL AND matricola={PH}", (matricola,))
    riga = cur.fetchone()
    # stessa risposta se non esiste o la password e' sbagliata (piu' sicuro)
    if not riga or not check_password_hash(riga[0] or "", password):
        cur.close(); con.close()
        return jsonify({"stato": "errore", "motivo": "dati di accesso sbagliati"}), 401
    if not riga[2]:
        cur.close(); con.close()
        return jsonify({"stato": "errore", "motivo": "account disattivato"}), 403

    ruolo = riga[1] or "autista"; az = riga[3]
    token = secrets.token_urlsafe(24)   # gettone casuale, difficile da indovinare
    cur.execute(f"INSERT INTO sessioni (token, matricola, azienda_id, ruolo) VALUES ({PH},{PH},{PH},{PH})",
                (token, matricola, az, ruolo))
    con.commit(); cur.close(); con.close()
    return jsonify({"stato": "ok", "token": token, "matricola": matricola,
                    "azienda_id": az, "ruolo": ruolo})


# Chi sono? (serve il gettone). Utile per verificare che il login "regga".
@app.route("/api/io")
def api_io():
    u = utente_corrente()
    if not u:
        return jsonify({"stato": "errore", "motivo": "non hai fatto il login"}), 401
    return jsonify({"stato": "ok", "matricola": u["matricola"],
                    "azienda_id": u["azienda_id"], "ruolo": u["ruolo"]})


# --- PAGINETTA DI PROVA del login ---
PAGINA_PROVA_LOGIN = """
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Prova login</title>
  <style>
    body { font-family: -apple-system, sans-serif; max-width: 480px;
           margin: 40px auto; padding: 0 16px; color: #222; }
    h1 { font-size: 22px; }
    label { display: inline-block; width: 90px; }
    input { padding: 9px; font-size: 16px; margin: 5px 0; width: 60%; }
    button { padding: 10px 16px; font-size: 15px; cursor: pointer; margin: 8px 6px 0 0; }
    #esito { min-height: 22px; font-weight: bold; margin-top: 12px; }
    code { background:#eee; padding:1px 5px; border-radius:4px; word-break:break-all; }
  </style>
</head>
<body>
  <h1>Prova: entra nel tuo account</h1>
  <div><label>Azienda</label><select id="az"><option value="">— Master (nessuna azienda) —</option></select></div>
  <div><label>Matricola</label><input id="matr" placeholder="es. 111 (o nome master)"></div>
  <div><label>Password</label><input id="pwd" type="password"></div>
  <button onclick="entra()">Entra</button>
  <button onclick="chiSono()">Chi sono?</button>
  <p id="esito"></p>
  <p id="tok"></p>

  <script>
    let TOKEN = '';
    async function caricaAziende(){
      const r = await fetch('/api/aziende'); const d = await r.json();
      const s = document.getElementById('az');
      (d.aziende||[]).forEach(function(a){ const o=document.createElement('option'); o.value=a.id; o.textContent=a.nome; s.appendChild(o); });
    }
    caricaAziende();
    async function entra(){
      const az = document.getElementById('az').value;
      const body = { matricola: document.getElementById('matr').value.trim(), password: document.getElementById('pwd').value };
      if (az) body.azienda_id = az;
      const r = await fetch('/api/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const d = await r.json();
      const e = document.getElementById('esito');
      if (d.stato === 'ok') {
        TOKEN = d.token;
        e.textContent = '✓ Sei entrato come ' + d.matricola + ' (ruolo: ' + d.ruolo + ')';
        document.getElementById('tok').innerHTML = 'Il tuo gettone: <code>' + d.token + '</code>';
      } else {
        e.textContent = '⚠ ' + (d.motivo || 'errore');
        document.getElementById('tok').textContent = '';
      }
    }
    async function chiSono(){
      const r = await fetch('/api/io', { headers: { 'Authorization': 'Bearer ' + TOKEN } });
      const d = await r.json();
      document.getElementById('esito').textContent =
        (d.stato === 'ok') ? ('Il server mi riconosce: ' + d.matricola + ' (' + d.ruolo + ')')
                           : ('⚠ ' + (d.motivo || 'non riconosciuto'));
    }
  </script>
</body>
</html>
"""


@app.route("/prova-login")
def prova_login():
    return PAGINA_PROVA_LOGIN


# =====================================================================
#  MASTER e AZIENDE (multi-azienda)
# =====================================================================

# Crea il PRIMO account master. Protetto da un codice segreto (SETUP_CODE),
# che imposti tu su Render. Funziona una volta sola: se un master esiste gia', rifiuta.
@app.route("/api/setup-master", methods=["POST"])
def api_setup_master():
    dati = request.get_json(silent=True) or {}
    codice = str(dati.get("codice") or "")
    utente = str(dati.get("utente") or "").strip()
    password = str(dati.get("password") or "")
    atteso = os.environ.get("SETUP_CODE", "")
    if not atteso or codice != atteso:
        return jsonify({"stato": "errore", "motivo": "codice di setup errato o non impostato"}), 403
    if not utente or len(password) < 6:
        return jsonify({"stato": "errore", "motivo": "servono nome utente e password (min 6)"}), 400
    con = get_conn(); cur = con.cursor()
    cur.execute("SELECT 1 FROM utenti WHERE ruolo='master' LIMIT 1")
    if cur.fetchone():
        cur.close(); con.close()
        return jsonify({"stato": "errore", "motivo": "esiste gia' un account master"}), 409
    cur.execute(f"SELECT 1 FROM utenti WHERE azienda_id IS NULL AND matricola={PH}", (utente,))
    if cur.fetchone():
        cur.close(); con.close()
        return jsonify({"stato": "errore", "motivo": "nome utente gia' in uso"}), 409
    ph = generate_password_hash(password)
    cur.execute(f"INSERT INTO utenti (azienda_id, matricola, password_hash, ruolo) "
                f"VALUES (NULL,{PH},{PH},'master')", (utente, ph))
    con.commit(); cur.close(); con.close()
    return jsonify({"stato": "ok", "utente": utente, "ruolo": "master"}), 201


@app.route("/api/aziende", methods=["GET", "POST"])
def api_aziende():
    # POST: crea un'azienda (solo il master puo')
    if request.method == "POST":
        u = utente_corrente()
        if not u or u["ruolo"] != "master":
            return jsonify({"stato": "errore", "motivo": "solo il master puo' creare aziende"}), 403
        dati = request.get_json(silent=True) or {}
        nome = str(dati.get("nome") or "").strip()
        if not nome:
            return jsonify({"stato": "errore", "motivo": "manca il nome azienda"}), 400
        con = get_conn(); cur = con.cursor()
        if USA_POSTGRES:
            cur.execute("INSERT INTO aziende (nome) VALUES (%s) RETURNING id", (nome,))
            new_id = cur.fetchone()[0]
        else:
            cur.execute("INSERT INTO aziende (nome) VALUES (?)", (nome,))
            new_id = cur.lastrowid
        con.commit(); cur.close(); con.close()
        return jsonify({"stato": "ok", "id": new_id, "nome": nome}), 201

    # GET: elenco pubblico (serve alla tendina della registrazione)
    con = get_conn(); cur = con.cursor()
    if USA_POSTGRES:
        cur.execute("SELECT id, nome FROM aziende WHERE attiva ORDER BY nome")
    else:
        cur.execute("SELECT id, nome FROM aziende WHERE attiva=1 ORDER BY nome")
    righe = cur.fetchall(); cur.close(); con.close()
    return jsonify({"aziende": [{"id": r[0], "nome": r[1]} for r in righe]})


# --- PAGINETTA per creare il primo master ---
PAGINA_SETUP_MASTER = """
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Setup master</title>
  <style>
    body { font-family: -apple-system, sans-serif; max-width: 480px;
           margin: 40px auto; padding: 0 16px; color: #222; }
    h1 { font-size: 22px; }
    label { display: inline-block; width: 110px; }
    input { padding: 9px; font-size: 16px; margin: 5px 0; width: 55%; }
    button { padding: 10px 16px; font-size: 15px; cursor: pointer; margin-top: 8px; }
    #esito { min-height: 22px; font-weight: bold; margin-top: 12px; }
    .nota { background:#fff7e0; border:1px solid #f0d97a; padding:10px; border-radius:6px; font-size:14px; }
  </style>
</head>
<body>
  <h1>Crea l'account master</h1>
  <p class="nota">Serve il <b>codice di setup</b> che hai impostato su Render (SETUP_CODE).
     Funziona una volta sola: crea il primo amministratore della piattaforma (tu).</p>
  <div><label>Codice setup</label><input id="codice" type="password"></div>
  <div><label>Nome utente</label><input id="utente" placeholder="es. davide"></div>
  <div><label>Password</label><input id="pwd" type="password" placeholder="min 6 caratteri"></div>
  <button onclick="crea()">Crea master</button>
  <p id="esito"></p>

  <script>
    async function crea(){
      const r = await fetch('/api/setup-master', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          codice: document.getElementById('codice').value,
          utente: document.getElementById('utente').value.trim(),
          password: document.getElementById('pwd').value
        })
      });
      const d = await r.json();
      document.getElementById('esito').textContent =
        (d.stato === 'ok') ? ('✓ Master creato: ' + d.utente) : ('⚠ ' + (d.motivo || 'errore'));
    }
  </script>
</body>
</html>
"""


@app.route("/setup-master")
def setup_master_page():
    return PAGINA_SETUP_MASTER


# --- PAGINETTA MASTER: entra e gestisci le aziende ---
PAGINA_PROVA_MASTER = """
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pannello master</title>
  <style>
    body { font-family: -apple-system, sans-serif; max-width: 560px;
           margin: 40px auto; padding: 0 16px; color: #222; }
    h1 { font-size: 22px; } h2 { font-size: 17px; margin-top: 24px; }
    label { display: inline-block; width: 90px; }
    input { padding: 9px; font-size: 16px; margin: 4px 0; }
    button { padding: 9px 14px; font-size: 15px; cursor: pointer; margin: 6px 6px 6px 0; }
    #esito { min-height: 22px; font-weight: bold; }
    ul { padding-left: 18px; } li { margin: 4px 0; }
    .box { border:1px solid #ddd; border-radius:8px; padding:12px; margin-top:12px; }
  </style>
</head>
<body>
  <h1>Pannello master</h1>

  <div class="box">
    <h2>1) Entra</h2>
    <div><label>Utente</label><input id="u" placeholder="il tuo nome master"></div>
    <div><label>Password</label><input id="p" type="password"></div>
    <button onclick="entra()">Entra</button>
  </div>

  <div class="box">
    <h2>2) Aziende</h2>
    <div><label>Nome</label><input id="nome" placeholder="es. ATC La Spezia"></div>
    <button onclick="crea()">Crea azienda</button>
    <button onclick="elenca()">Elenca aziende</button>
    <ul id="lista"></ul>
  </div>

  <div class="box">
    <h2>3) Matricole valide di un'azienda</h2>
    <div><label>Azienda</label><select id="azSel"></select></div>
    <div><label>Matricole</label><input id="matr" placeholder="es. 111, 222, 333 (separate da virgola)" style="width:70%"></div>
    <button onclick="caricaMatricole()">Carica matricole</button>
    <button onclick="vediMatricole()">Vedi matricole</button>
    <ul id="listaMatr"></ul>
  </div>

  <p id="esito"></p>

  <script>
    let TOKEN = '';
    async function entra(){
      const r = await fetch('/api/login', { method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ matricola: document.getElementById('u').value.trim(), password: document.getElementById('p').value }) });
      const d = await r.json();
      if (d.stato === 'ok' && d.ruolo === 'master') { TOKEN = d.token; document.getElementById('esito').textContent = '✓ Entrato come master'; elenca(); }
      else if (d.stato === 'ok') document.getElementById('esito').textContent = '⚠ Questo account non è master';
      else document.getElementById('esito').textContent = '⚠ ' + (d.motivo || 'errore');
    }
    async function crea(){
      if (!TOKEN) { document.getElementById('esito').textContent = 'Prima entra come master'; return; }
      const r = await fetch('/api/aziende', { method:'POST', headers:{'Content-Type':'application/json','Authorization':'Bearer '+TOKEN},
        body: JSON.stringify({ nome: document.getElementById('nome').value.trim() }) });
      const d = await r.json();
      document.getElementById('esito').textContent = (d.stato==='ok') ? ('✓ Azienda creata: '+d.nome) : ('⚠ '+(d.motivo||'errore'));
      document.getElementById('nome').value=''; elenca();
    }
    async function elenca(){
      const r = await fetch('/api/aziende'); const d = await r.json();
      const ul = document.getElementById('lista'); ul.innerHTML='';
      const sel = document.getElementById('azSel'); sel.innerHTML='';
      (d.aziende||[]).forEach(function(a){
        const li=document.createElement('li'); li.textContent = '#'+a.id+' — '+a.nome; ul.appendChild(li);
        const o=document.createElement('option'); o.value=a.id; o.textContent=a.nome; sel.appendChild(o);
      });
    }
    async function caricaMatricole(){
      if (!TOKEN) { document.getElementById('esito').textContent = 'Prima entra come master'; return; }
      const matr = document.getElementById('matr').value.split(',').map(function(x){return x.trim();}).filter(function(x){return x;});
      const r = await fetch('/api/matricole', { method:'POST', headers:{'Content-Type':'application/json','Authorization':'Bearer '+TOKEN},
        body: JSON.stringify({ azienda_id: document.getElementById('azSel').value, matricole: matr }) });
      const d = await r.json();
      document.getElementById('esito').textContent = (d.stato==='ok') ? ('✓ '+d.ricevute+' matricole caricate') : ('⚠ '+(d.motivo||'errore'));
      document.getElementById('matr').value=''; vediMatricole();
    }
    async function vediMatricole(){
      const az = document.getElementById('azSel').value;
      const r = await fetch('/api/matricole?azienda_id='+az); const d = await r.json();
      const ul = document.getElementById('listaMatr'); ul.innerHTML='';
      (d.matricole||[]).forEach(function(m){ const li=document.createElement('li'); li.textContent=m; ul.appendChild(li); });
    }
  </script>
</body>
</html>
"""


@app.route("/prova-master")
def prova_master_page():
    return PAGINA_PROVA_MASTER


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


# --- PAGINETTA DI PROVA dei guasti (servita dal server) ---
PAGINA_PROVA_GUASTI = """
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Prova guasti</title>
  <style>
    body { font-family: -apple-system, sans-serif; max-width: 640px;
           margin: 40px auto; padding: 0 16px; color: #222; }
    h1 { font-size: 22px; }
    label { display: inline-block; width: 95px; }
    input { padding: 8px; font-size: 16px; margin: 4px 0; }
    button { padding: 9px 14px; font-size: 15px; cursor: pointer; margin: 6px 6px 6px 0; }
    #esito { min-height: 22px; font-weight: bold; }
    pre { background: #f4f4f4; padding: 12px; border-radius: 6px; overflow:auto; }
  </style>
</head>
<body>
  <h1>Prova: segnalazione guasti</h1>
  <p>Segnala un guasto di un mezzo. Ogni segnalazione si aggiunge alla lista
     condivisa (niente blocco).</p>

  <div><label>Mezzo</label><input id="mezzo" placeholder="es. 1234"></div>
  <div><label>Data</label><input type="date" id="data"></div>
  <div><label>Tipo</label><input id="tipo" placeholder="es. Freni"></div>
  <div><label>Nota</label><input id="nota" placeholder="descrizione (facoltativa)"></div>
  <div><label>Matricola</label><input id="matr" placeholder="chi segnala"></div>

  <button onclick="segnala()">Segnala guasto</button>
  <button onclick="elenca()">Elenca i guasti</button>

  <p id="esito"></p>
  <div id="lista"></div>
  <pre id="out"></pre>

  <script>
    function mostra(o){ document.getElementById('out').textContent = JSON.stringify(o, null, 2); }

    async function segnala(){
      const g = {
        id: Date.now().toString(36) + Math.random().toString(36).slice(2,6),
        mezzo: document.getElementById('mezzo').value.trim(),
        data: document.getElementById('data').value,
        tipo: document.getElementById('tipo').value.trim(),
        nota: document.getElementById('nota').value.trim(),
        segnalato_da: document.getElementById('matr').value.trim()
      };
      const r = await fetch('/api/guasti', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(g)
      });
      const d = await r.json();
      const e = document.getElementById('esito');
      if (d.stato === 'salvato') e.textContent = '✓ Guasto segnalato per il mezzo ' + g.mezzo;
      else if (d.stato === 'gia_presente') e.textContent = 'ℹ Questa segnalazione era già registrata';
      else e.textContent = '⚠ ' + (d.motivo || 'errore');
      mostra(d);
    }

    async function elenca(){
      const r = await fetch('/api/guasti');
      const d = await r.json();
      document.getElementById('esito').textContent = 'Segnalazioni totali: ' + d.quanti;
      const box = document.getElementById('lista');
      box.innerHTML = '';
      d.guasti.forEach(function(g){
        const div = document.createElement('div');
        div.style = 'border:1px solid #ddd;border-radius:6px;padding:8px;margin:6px 0';
        const stato = (g.stato === 'inviato')
          ? '<b style="color:#0a7d28">✅ inviato all\\'officina</b> il ' + g.inviato_quando + (g.inviato_da ? (' da ' + g.inviato_da) : '')
          : '<b style="color:#b26b00">🕒 da inviare</b>';
        div.innerHTML =
          '<b>Mezzo ' + g.mezzo + '</b> — ' + (g.tipo || '?') + ' (' + g.data + ')<br>' +
          (g.nota || '<i>senza nota</i>') +
          '<br><small>segnalato il ' + g.quando + (g.segnalato_da ? (' da ' + g.segnalato_da) : '') + '</small><br>' +
          stato;
        if (g.stato !== 'inviato') {
          const b = document.createElement('button');
          b.textContent = "Invia all'officina";
          b.onclick = function(){ invia(g.id); };
          div.appendChild(document.createElement('br'));
          div.appendChild(b);
        }
        box.appendChild(div);
      });
      mostra(d);
    }

    async function invia(id){
      const chi = document.getElementById('matr').value.trim();
      const r = await fetch('/api/guasti/' + encodeURIComponent(id) + '/invia', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ inviato_da: chi })
      });
      const d = await r.json();
      document.getElementById('esito').textContent =
        (d.stato === 'inviato') ? '✅ Segnalazione inviata all\\'officina' :
        (d.stato === 'gia_inviato') ? 'Era già stata inviata' : ('⚠ ' + (d.motivo || 'errore'));
      elenca();
    }
  </script>
</body>
</html>
"""


@app.route("/prova-guasti")
def prova_guasti():
    return PAGINA_PROVA_GUASTI


# crea la tabella all'avvio (vale anche quando gira con gunicorn su Render)
try:
    init_db()
except Exception as e:
    print("Attenzione, init_db non riuscito:", e)


# serve solo per provare in locale sul tuo Mac
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
