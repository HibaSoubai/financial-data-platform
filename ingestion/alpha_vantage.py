"""Ingestion de cours journaliers depuis Alpha Vantage (couche Bronze), pour recouper yfinance.

Compte gratuit : 25 requêtes par jour, 5 par minute, mode 'compact' = 100 derniers jours.
1 requête par ticker. Si Alpha Vantage refuse (quota ou endpoint premium), on s'arrête
immédiatement au lieu de répéter la même erreur sur chaque ticker.
"""
import json
import logging
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]
URL = "https://www.alphavantage.co/query"
RAW_DIR = Path("data/raw")
TIMEOUT = 30
CACHE_HOURS = 12             # on ne redemande pas la même série plusieurs fois par jour
PAUSE_SECONDS = 13           # 5 requêtes par minute maximum


class QuotaOrPlanError(RuntimeError):
    """Quota dépassé ou endpoint réservé aux comptes payants : inutile de continuer."""


def is_fresh(path: Path) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < CACHE_HOURS * 3600


def fetch_daily(ticker: str, api_key: str) -> dict:
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": ticker,
        "outputsize": "compact",
        "datatype": "json",
        "apikey": api_key,
    }
    response = requests.get(URL, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()

    if "Time Series (Daily)" in data:
        return data

    # Alpha Vantage répond 200 avec un message à la place des données
    for field in ("Information", "Note"):
        if field in data:
            message = str(data[field]).replace(api_key, "***")[:160]
            raise QuotaOrPlanError(f"{field} : {message}")
    if "Error Message" in data:
        raise ValueError("ticker ou paramètre invalide")
    raise ValueError("réponse inattendue")


def main() -> None:
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise SystemExit("ALPHA_VANTAGE_API_KEY manquante dans .env")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    force = os.getenv("FORCE_REFRESH", "0") == "1"
    failures = []
    calls = 0

    for ticker in TICKERS:
        path = RAW_DIR / f"alpha_vantage_daily_{ticker}.json"
        if is_fresh(path) and not force:
            logger.info("%s : série de moins de %d h, on passe (quota préservé)", ticker, CACHE_HOURS)
            continue
        if calls:
            time.sleep(PAUSE_SECONDS)
        calls += 1
        try:
            data = fetch_daily(ticker, api_key)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.info("%s : %d jours enregistrés", ticker, len(data["Time Series (Daily)"]))
        except QuotaOrPlanError as exc:
            logger.error("%s : %s", ticker, exc)
            logger.error("Arrêt immédiat : inutile d'insister (quota ou endpoint premium)")
            sys.exit(1)
        except Exception as exc:
            logger.error("Échec pour %s : %s", ticker, type(exc).__name__)
            failures.append(ticker)

    logger.info("Requêtes envoyées : %d (quota gratuit : 25 par jour)", calls)
    if failures:
        logger.error("Tickers en échec : %s", failures)
        sys.exit(1)


if __name__ == "__main__":
    main()