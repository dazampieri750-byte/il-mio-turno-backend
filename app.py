# =====================================================================
#  Il mio primo server — passo 1 (per imparare)
# ---------------------------------------------------------------------
#  Un "server" è semplicemente un programma che resta in ascolto e
#  RISPONDE quando qualcuno (di solito il browser) gli chiede qualcosa
#  a un certo indirizzo. Niente di magico.
# =====================================================================

from flask import Flask          # Flask = lo strumento che ci fa fare un server in poche righe

app = Flask(__name__)            # creo l'applicazione (il "server")


# Quando qualcuno apre l'indirizzo "/" (la home), eseguo questa funzione
@app.route("/")
def home():
    return "Ciao! Il tuo primo server funziona. 🎉"


# Un indirizzo con una parte VARIABILE: <nome> cambia in base a cosa scrivi
# Esempio: aprendo /saluto/Davide  ->  risponde "Ciao Davide, ..."
@app.route("/saluto/<nome>")
def saluto(nome):
    return f"Ciao {nome}, benvenuto nel tuo server!"


# Questa parte avvia il server quando lanci il file.
# Resterà in ascolto sulla porta 5050 del tuo computer.
# (Sul Mac la 5000 è occupata da "AirPlay Receiver", quindi usiamo la 5050.)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
