"""Ingestion des cours boursiers depuis Yahoo Finance (couche Bronze)."""
import logging
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]
RAW_DIR = Path("data/raw")
MAX_RETRIES = 3
WAIT_SECONDS = 15


def fetch_prices(ticker: str, start: str = "2020-01-01") -> pd.DataFrame:
    """Télécharge l'historique OHLCV d'un ticker, avec plusieurs tentatives."""
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("Téléchargement de %s (tentative %d/%d)", ticker, attempt, MAX_RETRIES)
        df = yf.download(ticker, start=start, auto_adjust=False, progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.reset_index()
            df["ticker"] = ticker
            return df
        logger.warning("Aucune donnée pour %s, nouvelle tentative dans %ds", ticker, WAIT_SECONDS)
        time.sleep(WAIT_SECONDS)
    raise ValueError(f"Aucune donnée reçue pour {ticker} après {MAX_RETRIES} tentatives")


def save_raw(df: pd.DataFrame, ticker: str) -> Path:
    """Sauvegarde les données brutes sans les modifier."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{ticker}_prices.csv"
    df.to_csv(path, index=False)
    logger.info("Fichier écrit : %s (%d lignes)", path, len(df))
    return path


def main() -> None:
    for ticker in TICKERS:
        path = RAW_DIR / f"{ticker}_prices.csv"
        if path.exists():
            logger.info("%s déjà présent, on passe", path)
            continue
        try:
            save_raw(fetch_prices(ticker), ticker)
        except Exception:
            logger.exception("Échec pour %s", ticker)


if __name__ == "__main__":
    main()