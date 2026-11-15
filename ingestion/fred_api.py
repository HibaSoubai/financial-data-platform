"""Ingestion des indicateurs macroéconomiques depuis FRED (couche Bronze).

Plan A : API officielle avec clé. Plan B : export CSV public de FRED (sans clé).
La clé n'est jamais écrite dans les logs.
"""
import io
import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

SERIES = {
    "FEDFUNDS": "Taux directeur effectif (Fed funds), mensuel",
    "CPIAUCSL": "Indice des prix à la consommation, mensuel",
    "DGS10": "Rendement des bons du Trésor à 10 ans, quotidien",
    "UNRATE": "Taux de chômage américain, mensuel",
    "VIXCLS": "Indice de volatilité VIX, quotidien",
}
API_URL = "https://api.stlouisfed.org/fred/series/observations"
CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
START_DATE = "2020-01-01"
RAW_DIR = Path("data/raw")
TIMEOUT = 30
MAX_RETRIES = 3
RETRY_WAIT = 10
PAUSE_BETWEEN_SERIES = 1.0   # largement sous la limite de 120 requêtes par minute


def _status(exc: Exception):
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def fetch_from_api(series_id: str, api_key: str) -> pd.DataFrame:
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": START_DATE,
    }
    response = requests.get(API_URL, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    observations = response.json().get("observations", [])
    if not observations:
        raise ValueError("réponse vide")
    return pd.DataFrame(observations)[["date", "value"]]


def fetch_from_public_csv(series_id: str) -> pd.DataFrame:
    response = requests.get(
        CSV_URL, params={"id": series_id, "cosd": START_DATE}, timeout=TIMEOUT
    )
    response.raise_for_status()
    df = pd.read_csv(io.StringIO(response.text))
    if df.shape[1] < 2 or df.empty:
        raise ValueError("CSV inattendu ou vide")
    df = df.iloc[:, :2]
    df.columns = ["date", "value"]
    return df


def fetch_series(series_id: str, api_key: str | None) -> pd.DataFrame:
    """Tente l'API officielle, puis le CSV public ; plusieurs essais pour chacun."""
    sources = []
    if api_key:
        sources.append(("API officielle", lambda: fetch_from_api(series_id, api_key)))
    else:
        logger.warning("FRED_API_KEY absente : utilisation du CSV public uniquement")
    sources.append(("CSV public", lambda: fetch_from_public_csv(series_id)))

    for label, fetch in sources:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info("%s | %s (tentative %d/%d)", series_id, label, attempt, MAX_RETRIES)
                return fetch()
            except Exception as exc:  # on ne logue JAMAIS le texte de l'exception (URL avec clé)
                logger.warning(
                    "%s | %s échec : %s, statut HTTP %s",
                    series_id, label, type(exc).__name__, _status(exc),
                )
                time.sleep(RETRY_WAIT)
        logger.warning("%s | %s abandonnée, on passe à la source suivante", series_id, label)
    raise RuntimeError(f"Aucune source disponible pour {series_id}")


def save_raw(df: pd.DataFrame, series_id: str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    df["series_id"] = series_id
    path = RAW_DIR / f"fred_{series_id}.csv"
    df.to_csv(path, index=False)
    logger.info("Fichier écrit : %s (%d lignes)", path, len(df))
    return path


def main() -> None:
    api_key = os.getenv("FRED_API_KEY")
    failures = []
    for series_id in SERIES:
        try:
            save_raw(fetch_series(series_id, api_key), series_id)
        except Exception as exc:
            logger.error("Échec pour %s : %s", series_id, type(exc).__name__)
            failures.append(series_id)
        time.sleep(PAUSE_BETWEEN_SERIES)

    if failures:
        logger.error("Séries en échec : %s", failures)
        sys.exit(1)


if __name__ == "__main__":
    main()