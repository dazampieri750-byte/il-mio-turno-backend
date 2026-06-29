# =====================================================================
#  Il mio server — passo 2: con DATABASE (ricorda i dati)
# ---------------------------------------------------------------------
#  Ora il server non solo risponde, ma SALVA e RILEGGE dati da un
#  database Postgres (che creiamo su Render).
#  L'indirizzo del database NON è scritto qui dentro: lo prendiamo da una
#  "variabile d'ambiente" (DATABASE_URL), così resta fuori dal codice.
#  È il modo serio e sicuro di tenere password/indirizzi (utile anche per GDPR).
# =====================================================================

import os
from flask import Flask
import psycopg2          # il "ponte" che fa parlare Python col database Postgres

app = Flask(__name__)

# l'indirizzo del database arriva da fuori (lo imposteremo su Render)
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_conn():
    """Apre una connessione al database."""
    return psycopg2.connect(DATABASE_URL)


def init_db():
    """Crea la tabella 'messaggi' se non esiste ancora."""
    if not DATABASE_URL:
        return
    con = get_conn(); cur = con.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS messaggi ("
        " id SERIAL PRIMARY KEY,"
        " testo TEXT,"
        " quando TIMESTAMP DEFAULT NOW())"
    )
    con.commit(); cur.close(); con.close()


# --- indirizzi base (come prima) ---
@app.route("/")
def home():
    return "Ciao! Il tuo server con database è attivo. 🎉  Prova /scrivi/ciao e poi /elenco"


@app.route("/saluto/<nome>")
def saluto(nome):
    return f"Ciao {nome}, benvenuto nel tuo server!"


# --- SALVA un messaggio nel database ---
@app.route("/scrivi/<testo>")
def scrivi(testo):
    if not DATABASE_URL:
        return "Database non collegato (manca DATABASE_URL)."
    con = get_conn(); cur = con.cursor()
    cur.execute("INSERT INTO messaggi (testo) VALUES (%s)", (testo,))
    con.commit(); cur.close(); con.close()
    return f"Salvato nel database: «{testo}». Vai su /elenco per vederli tutti."


# --- RILEGGE tutti i messaggi salvati ---
@app.route("/elenco")
def elenco():
    if not DATABASE_URL:
        return "Database non collegato (manca DATABASE_URL)."
    con = get_conn(); cur = con.cursor()
    cur.execute("SELECT testo, quando FROM messaggi ORDER BY id DESC")
    righe = cur.fetchall(); cur.close(); con.close()
    if not righe:
        return "Nessun messaggio salvato. Prova prima /scrivi/ciao"
    return "<br>".join(f"{q:%d/%m %H:%M} — {t}" for (t, q) in righe)


# crea la tabella all'avvio (vale anche quando gira con gunicorn)
try:
    init_db()
except Exception as e:
    print("Attenzione, init_db non riuscito:", e)


# serve solo per provare in locale sul tuo Mac
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
