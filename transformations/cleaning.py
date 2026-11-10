"""Nettoyage et validation des cours boursiers : Bronze -> Silver."""
import logging
from datetime import date, datetime
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")
SILVER_DIR = Path("data/processed")

COLUMN_MAP = {
    "Date": "date",
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
    "ticker": "ticker",
}
FINAL_COLUMNS = ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]
PRICE_COLUMNS = ["open", "high", "low", "close", "adj_close"]
EXTREME_RETURN = 0.20  # variation journalière à signaler (20 %)


def standardize(df: pd.DataFrame) -> pd.DataFrame:
    """Renomme les colonnes et force les types."""
    missing = set(COLUMN_MAP) - set(df.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes : {sorted(missing)}")

    df = df.rename(columns=COLUMN_MAP)[FINAL_COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in PRICE_COLUMNS + ["volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["ticker"] = df["ticker"].astype("string").str.strip().str.upper()
    return df


def clean(df: pd.DataFrame, ingestion_date: date) -> pd.DataFrame:
    """Supprime les lignes invalides, les doublons et la barre incomplète."""
    ticker = df["ticker"].iloc[0] if len(df) else "?"
    start = len(df)

    # 1. Valeurs manquantes
    df = df.dropna(subset=["date", "ticker", "volume"] + PRICE_COLUMNS)
    logger.info("%s | manquantes supprimées : %d", ticker, start - len(df))

    # 2. Doublons
    before = len(df)
    df = df.drop_duplicates(subset=["ticker", "date"], keep="last")
    logger.info("%s | doublons supprimés : %d", ticker, before - len(df))

    # 3. Valeurs impossibles
    before = len(df)
    invalid = (
        (df[PRICE_COLUMNS] <= 0).any(axis=1)
        | (df["volume"] < 0)
        | (df["high"] < df["low"])
    )
    df = df[~invalid]
    logger.info("%s | lignes invalides supprimées : %d", ticker, before - len(df))

    # 4. Barre du jour de téléchargement (potentiellement incomplète)
    before = len(df)
    df = df[df["date"].dt.date < ingestion_date]
    logger.info("%s | barre incomplète exclue : %d", ticker, before - len(df))

    df = df.copy()
    df["volume"] = df["volume"].astype("int64")
    return df


def report_anomalies(df: pd.DataFrame) -> None:
    """Signale (sans supprimer) les rendements journaliers extrêmes."""
    returns = df.sort_values("date")["adj_close"].pct_change()
    extreme = df.loc[returns.abs() > EXTREME_RETURN, "date"]
    for d in extreme:
        logger.warning("%s | rendement extrême le %s", df["ticker"].iloc[0], d.date())


def process_ticker(path: Path) -> pd.DataFrame:
    """Applique toute la chaîne de nettoyage à un fichier Bronze."""
    ingestion_date = datetime.fromtimestamp(path.stat().st_mtime).date()
    df = standardize(pd.read_csv(path))
    df = clean(df, ingestion_date)
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    report_anomalies(df)
    return df


def main() -> None:
    files = sorted(RAW_DIR.glob("*_prices.csv"))
    if not files:
        raise SystemExit("Aucun fichier Bronze trouvé dans data/raw")

    frames = []
    for path in files:
        try:
            frames.append(process_ticker(path))
        except Exception:
            logger.exception("Échec pour %s", path.name)

    if not frames:
        raise SystemExit("Aucun fichier traité avec succès")

    silver = pd.concat(frames, ignore_index=True)

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    parquet_path = SILVER_DIR / "stock_prices_silver.parquet"
    csv_path = SILVER_DIR / "stock_prices_silver.csv"
    silver.to_parquet(parquet_path, index=False)
    silver.to_csv(csv_path, index=False)

    logger.info("Silver écrit : %d lignes", len(silver))
    logger.info("Taille Parquet : %.0f Ko", parquet_path.stat().st_size / 1024)
    logger.info("Taille CSV     : %.0f Ko", csv_path.stat().st_size / 1024)


if __name__ == "__main__":
    main()