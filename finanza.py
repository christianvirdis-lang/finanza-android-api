"""Blueprint Flask per l'analisi finanziaria giornaliera (AI + ricerca web).
Strategia multi-fattore ispirata ai criteri dei grandi investitori (macro, valore,
crescita, momentum, asimmetria rischio/rendimento): ogni giorno 3 segnali ad alta
convinzione, scelti tra tutti gli strumenti (non uno a forza per categoria). I segnali
restano in un registro "aperti" fino alla scadenza del loro orizzonte temporale e
vengono rivisti ogni giorno con ricerche aggiornate: se è successo qualcosa di
rilevante (notizie, dati macro, interventi inattesi) viene generato un alert legato
al segnale originale. Nessun accesso a conti reali e nessun ordine viene mai piazzato:
solo analisi informativa che l'utente esegue manualmente (es. su eToro/Plus500).

Copia indipendente per il deploy cloud (finanza-cloud/): stessa logica del file
omonimo nella cartella principale, ma senza le dipendenze dal resto dell'app
desktop (Flask Blueprint montato su app.py). Le due copie vanno tenute in sync
manualmente se si modifica il motore di analisi."""
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"), timeout=300.0)

BASE_DIR = Path(__file__).resolve().parent
CACHE_FILE = BASE_DIR / "cache_finanza.json"
STORICO_FILE = BASE_DIR / "storico_finanza.jsonl"
SEGNALI_APERTI_FILE = BASE_DIR / "segnali_aperti.json"

CATEGORIE = [
    ("azioni", "Azioni"),
    ("forex", "Forex / Valute"),
    ("crypto", "Criptovalute"),
    ("commodities", "Materie Prime e Indici"),
]

ORIZZONTI = [
    ("breve", "Breve termine (1-5 giorni)"),
    ("medio", "Medio termine (2-8 settimane)"),
    ("lungo", "Lungo termine (3-12 mesi)"),
]

ORIZZONTE_GIORNI = {"breve": 5, "medio": 56, "lungo": 365}

DISCLAIMER = (
    "Analisi generata da intelligenza artificiale a scopo informativo personale. "
    "Non è consulenza finanziaria professionale, non garantisce alcun profitto e non "
    "sostituisce il parere di un consulente abilitato. Nessun ordine viene eseguito "
    "automaticamente: l'esecuzione su eToro/Plus500 resta sempre una tua scelta manuale. "
    "Investi solo capitale che puoi permetterti di perdere."
)


def _today_str():
    return datetime.now().strftime("%Y-%m-%d")


def load_cache():
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache_entry(date_str, report):
    cache = load_cache()
    cache[date_str] = report
    try:
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def save_to_storico(date_str, report):
    record = {"timestamp": datetime.now().isoformat(timespec="seconds"), "data": date_str, "report": report}
    try:
        with open(STORICO_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def carica_segnali_aperti():
    if SEGNALI_APERTI_FILE.exists():
        try:
            return json.loads(SEGNALI_APERTI_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def salva_segnali_aperti(lista):
    try:
        SEGNALI_APERTI_FILE.write_text(json.dumps(lista, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _calcola_scadenza(orizzonte, data_emissione_str):
    giorni = ORIZZONTE_GIORNI.get(orizzonte, 5)
    data_emissione = datetime.strptime(data_emissione_str, "%Y-%m-%d")
    return (data_emissione + timedelta(days=giorni)).strftime("%Y-%m-%d")


def _aggiorna_registro_segnali(nuovi_segnali, date_str):
    """Aggiunge i nuovi segnali al registro (con id e scadenza) e rimuove quelli scaduti.
    Muta in-place i dict in nuovi_segnali per arricchirli con id/data_emissione/scadenza,
    cosi' anche il report mostrato all'utente li riporta."""
    aperti = carica_segnali_aperti()
    oggi = datetime.strptime(date_str, "%Y-%m-%d")
    aperti = [
        s for s in aperti
        if datetime.strptime(s["scadenza"], "%Y-%m-%d") >= oggi and s.get("data_emissione") != date_str
    ]

    for i, s in enumerate(nuovi_segnali, start=1):
        if not isinstance(s, dict):
            continue
        s["id"] = f"{date_str}-{i}"
        s["data_emissione"] = date_str
        s["scadenza"] = _calcola_scadenza(s.get("orizzonte", "breve"), date_str)
        aperti.append(dict(s))

    salva_segnali_aperti(aperti)


def _extract_json(full_text):
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", full_text)
    if fence:
        return fence.group(1)
    raw = re.search(r"\{[\s\S]*\}", full_text)
    if raw:
        return raw.group()
    return None


def build_system_prompt(date_str):
    head = f"""Sei un comitato di analisi quantitativa che applica i criteri dei più grandi investitori della storia per selezionare un numero ristretto di segnali ad altissima convinzione. Oggi è {date_str}. Usa SEMPRE la ricerca web per dati e notizie reali e aggiornate: non basarti solo su conoscenza pregressa.

Applica questi filtri, nello stile di chi li ha rese famose:
1. MACRO (Ray Dalio): in che regime ci troviamo (crescita/inflazione, politica delle banche centrali, ciclo del credito)? Il segnale è coerente con questo regime o lo sfrutta?
2. VALORE E QUALITÀ (Warren Buffett, Benjamin Graham): per le azioni, c'è un margine di sicurezza tra prezzo e valore intrinseco, un vantaggio competitivo duraturo, ROE solido, debito contenuto, free cash flow positivo?
3. CRESCITA A PREZZO RAGIONEVOLE (Peter Lynch): se è una storia di crescita, il prezzo la sconta già troppo (rapporto PEG)?
4. MOMENTUM E TREND (trend-following, Jesse Livermore): il prezzo e i volumi confermano la direzione? Non proporre mai un'idea contro il trend dominante senza una ragione fortissima e specifica.
5. ASIMMETRIA RISCHIO/RENDIMENTO (Stanley Druckenmiller, George Soros): il rapporto reward/rischio è interessante (almeno 1.5)? Lo stop loss implica un rischio gestibile?
6. CATALIZZATORE CONCRETO: deve esistere una notizia, un dato macro, un evento societario, una decisione di banca centrale o un fatto geopolitico SPECIFICO e RECENTE che giustifica l'idea adesso — non un'opinione generica.

PARTE 1 — REVISIONE SEGNALI APERTI
Ti vengono forniti (se presenti) i segnali ancora aperti emessi nei giorni scorsi, con il loro id. Per ciascuno, cerca online notizie, dati o eventi successivi alla loro emissione — incluso qualunque intervento inatteso (banca centrale, governo, regolatore, dichiarazioni societarie, eventi geopolitici) — che potrebbero invalidare o modificare la tesi originale. Se non è successo nulla di rilevante, NON includerlo nella lista di alert: meglio nessun alert che un alert inutile. Se invece qualcosa di rilevante è cambiato, crea un alert con un'azione consigliata chiara (es. chiudere subito, spostare lo stop loss, prendere profitto in anticipo, oppure semplicemente monitorare con attenzione).

PARTE 2 — NUOVI SEGNALI DI OGGI
Seleziona ESATTAMENTE 3 nuovi segnali in totale — non uno a forza per categoria, ma i 3 migliori in assoluto tra azioni, forex, crypto e materie prime/indici, a qualunque orizzonte temporale (breve 1-5 giorni, medio 2-8 settimane, lungo 3-12 mesi) — applicando rigorosamente i 6 filtri sopra. Per ciascuno indica quali filtri sono stati decisivi.

Per ogni segnale indica anche quanto capitale investire, come percentuale del capitale totale disponibile (campo "capitale_percentuale", es. "5%"), in linea con la gestione del rischio di Druckenmiller/Soros: tra il 2% e il 15%, più alta quando convinzione e rapporto reward/rischio sono migliori e il rischio è Basso/Medio, più bassa quando il rischio è Alto o la convinzione è minore. Tieni conto che ci sono anche altri segnali aperti contemporaneamente: la somma delle percentuali su tutte le posizioni aperte non deve mai superare il 100% del capitale.

Rispondi ESCLUSIVAMENTE con un blocco JSON valido, senza alcun testo prima o dopo, in questo formato esatto:
"""
    schema = """{
  "sintesi_giornaliera": "1-2 paragrafi sul contesto macro/mercati di oggi",
  "alert_su_segnali_precedenti": [
    {"id_segnale": "id del segnale aperto a cui si riferisce", "cosa_e_cambiato": "", "azione_consigliata": "", "gravita": "Bassa, Media o Alta"}
  ],
  "segnali": [
    {"strumento":"","ticker":"","categoria":"azioni, forex, crypto o commodities","direzione":"Long o Short","orizzonte":"breve, medio o lungo","prezzo_attuale":"","entry":"","stop_loss":"","take_profit":"","rischio":"Basso, Medio o Alto","capitale_percentuale":"es. 5%","criteri":"quali dei 6 filtri sono stati decisivi, in breve","motivazione":""}
  ]
}"""
    tail = (
        "\n\nQuesta analisi è generata da intelligenza artificiale a scopo informativo personale: "
        "non è consulenza finanziaria professionale e non garantisce alcun risultato. "
        '"alert_su_segnali_precedenti" deve restare vuoto se non c\'è nulla di rilevante da segnalare. '
        '"segnali" deve contenere ESATTAMENTE 3 elementi, non di più non di meno.'
    )
    return head + schema + tail


def build_user_message(date_str, segnali_aperti):
    if not segnali_aperti:
        return f"Genera il report finanziario giornaliero del {date_str}. Non ci sono segnali aperti precedenti da rivedere (lista vuota)."
    righe = [
        f"- id={s.get('id')} | {s.get('strumento')} ({s.get('ticker', '')}) | {s.get('direzione')} | "
        f"emesso il {s.get('data_emissione')} | orizzonte {s.get('orizzonte')} | entry {s.get('entry')} | "
        f"stop loss {s.get('stop_loss')} | take profit {s.get('take_profit')} | "
        f"capitale impegnato: {s.get('capitale_percentuale', 'n/d')}"
        for s in segnali_aperti
    ]
    elenco = "\n".join(righe)
    return (
        f"Genera il report finanziario giornaliero del {date_str}.\n\n"
        f"Segnali aperti da rivedere (controlla se è successo qualcosa di rilevante da quando sono stati emessi):\n{elenco}"
    )


def genera_report(date_str=None):
    """Chiama Claude con ricerca web e ritorna il report come dict, oppure None se fallisce."""
    date_str = date_str or _today_str()
    segnali_aperti = carica_segnali_aperti()
    response = None
    for tentativo in (1, 2):
        try:
            response = client.messages.create(
                model="claude-opus-4-8", max_tokens=14000,
                system=[{"type": "text", "text": build_system_prompt(date_str), "cache_control": {"type": "ephemeral"}}],
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 30}],
                messages=[{"role": "user", "content": build_user_message(date_str, segnali_aperti)}],
            )
            break
        except Exception as e:
            print(f"[finanza] Errore chiamata API (tentativo {tentativo}): {e}")
    if response is None:
        return None

    full_text = "".join(block.text for block in response.content if hasattr(block, "text") and block.text)
    json_str = _extract_json(full_text)
    if not json_str:
        print("[finanza] Nessun JSON trovato nella risposta del modello.")
        return None
    try:
        report = json.loads(json_str)
    except Exception as e:
        print(f"[finanza] Errore parsing JSON: {e}")
        return None

    segnali = report.get("segnali")
    if not isinstance(segnali, list):
        segnali = []
    _aggiorna_registro_segnali(segnali, date_str)

    usage = getattr(response, "usage", None)
    if usage:
        print(f"[finanza] token input: {usage.input_tokens} | output: {usage.output_tokens} | "
              f"cache letti: {getattr(usage, 'cache_read_input_tokens', 0) or 0}")

    report["data"] = date_str
    report["generato_alle"] = datetime.now().isoformat(timespec="seconds")
    return report


def genera_e_salva_report_oggi(force=False):
    """Ritorna il report di oggi: dalla cache se già presente, altrimenti lo genera.
    Se la generazione fallisce, memorizza un marcatore di errore per non ritentare
    (costoso) ad ogni richiesta della pagina fino al giorno dopo o a un rigenera manuale."""
    date_str = _today_str()
    cache = load_cache()
    if not force and date_str in cache:
        return cache[date_str]

    report = genera_report(date_str)
    if report:
        save_cache_entry(date_str, report)
        save_to_storico(date_str, report)
        return report

    # Generazione fallita: se oggi avevamo già un report buono (es. un rigenera
    # forzato che poi è andato in errore di rete), non lo sovrascriviamo con un
    # marcatore di errore — meglio mostrare l'ultimo report valido che uno vuoto.
    esistente = cache.get(date_str)
    if esistente and not esistente.get("errore"):
        return esistente

    save_cache_entry(date_str, {"data": date_str, "errore": True})
    return None
