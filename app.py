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
from flask import Flask, jsonify   # jsonify = costruisce una risposta JSON

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


# --- RILEGGE i messaggi, versione per APP (JSON) ---
# Stessi dati di /elenco, ma "impacchettati" con le etichette:
# un'app puo' leggere ogni campo senza dover interpretare del testo.
@app.route("/api/messaggi")
def api_messaggi():
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


# crea la tabella all'avvio (vale anche quando gira con gunicorn su Render)
try:
    init_db()
except Exception as e:
    print("Attenzione, init_db non riuscito:", e)


# serve solo per provare in locale sul tuo Mac
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
