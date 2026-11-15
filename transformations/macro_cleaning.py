"""Nettoyage des indicateurs macroéconomiques FRED : Bronze -> Silver."""
import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")
SILVER_DIR = Path("data/processed")
OUTPUT = SILVER_DIR / "macro_indicators_silver.parquet"

# series_id -> (description, fréquence, unité, minimum plausible, maximum plausible)
SERIES_INFO = {
    "FEDFUNDS": ("Taux directeur effectif (Fed funds)", "mensuelle", "pourcentage", 0, 25),
    "CPIAUCSL": ("Indice des prix à la consommation", "mensuelle", "indice (base 1982-1984 = 100)", 0, 1000),
    "DGS10": ("Rendement des bons du Trésor à 10 ans", "quotidienne", "pourcentage", -2, 25),
    "UNRATE": ("Taux de chômage américain", "mensuelle", "pourcentage", 0, 30),
    "VIXCLS": ("Indice de volatilité VIX", "quotidienne", "points d'indice", 0, 200),
}


def clean_series(df: pd.DataFrame, series_id: str) -> pd.DataFrame:
    """Nettoie une série : types, valeurs manquantes (.), valeurs impossibles, doublons."""
    start = len(df)
    df = df.rename(columns=str.lower)[["date", "value"]].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")   # "." devient NaN

    missing = int(df["value"].isna().sum() + df["date"].isna().sum())
    df = df.dropna(subset=["date", "value"])

    _, _, _, low, high = SERIES_INFO[series_id]
    out_of_range = int(((df["value"] < low) | (df["value"] > high)).sum())
    df = df[(df["value"] >= low) & (df["value"] <= high)]

    before = len(df)
    df = df.drop_duplicates(subset=["date"], keep="last")
    duplicates = before - len(df)

    logger.info(
        "%s | lues : %d | manquantes (.) : %d | hors plage : %d | doublons : %d | gardées : %d",
        series_id, start, missing, out_of_range, duplicates, len(df),
    )
    df["series_id"] = series_id
    return df[["series_id", "date", "value"]].sort_values("date").reset_index(drop=True)


def main() -> None:
    frames = []
    for series_id in SERIES_INFO:
        path = RAW_DIR / f"fred_{series_id}.csv"
        if not path.exists():
            raise SystemExit(f"Fichier Bronze manquant : {path} (lance d'abord ingestion/fred_api.py)")
        frames.append(clean_series(pd.read_csv(path), series_id))

    silver = pd.concat(frames, ignore_index=True)
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    silver.to_parquet(OUTPUT, index=False)
    logger.info("Silver macro écrit : %d lignes -> %s", len(silver), OUTPUT)
    logger.info("Période : %s -> %s", silver["date"].min().date(), silver["date"].max().date())


if __name__ == "__main__":
    main()