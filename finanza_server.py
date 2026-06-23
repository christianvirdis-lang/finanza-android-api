"""Servizio Flask minimale e standalone: espone solo l'API JSON del report finanziario
del giorno, pensato per essere distribuito online (es. Render) e richiamato dall'app
Android. Indipendente dal progetto principale (calcio/stanze): repo e deploy separati
per non avere conflitti con quel progetto. Protetto da un token condiviso (header
X-Api-Key) — senza, chiunque trovasse l'URL potrebbe far scattare chiamate a pagamento
verso l'API Anthropic."""
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file

import finanza

load_dotenv()

app = Flask(__name__)

API_TOKEN = os.getenv("FINANZA_API_TOKEN", "")
APK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "AnalisiFinanziaria.apk")


def _autorizzato():
    return bool(API_TOKEN) and request.headers.get("X-Api-Key") == API_TOKEN


@app.route("/")
def health():
    return jsonify({"status": "ok", "servizio": "finanza-api"})


@app.route("/download")
def download_apk():
    if not os.path.exists(APK_PATH):
        return "APK non trovato sul server.", 404
    return send_file(APK_PATH, as_attachment=True, download_name="AnalisiFinanziaria.apk",
                      mimetype="application/vnd.android.package-archive")


@app.route("/api/report")
def api_report():
    if not _autorizzato():
        return jsonify({"error": "unauthorized"}), 401
    report = finanza.genera_e_salva_report_oggi()
    if report and report.get("errore"):
        report = None
    return jsonify({
        "report": report,
        "disclaimer": finanza.DISCLAIMER,
        "categorie": dict(finanza.CATEGORIE),
        "orizzonti": dict(finanza.ORIZZONTI),
    })


@app.route("/api/regenera", methods=["POST"])
def api_regenera():
    if not _autorizzato():
        return jsonify({"error": "unauthorized"}), 401
    report = finanza.genera_e_salva_report_oggi(force=True)
    return jsonify({"ok": bool(report and not report.get("errore"))})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5050"))
    app.run(host="0.0.0.0", port=port)
