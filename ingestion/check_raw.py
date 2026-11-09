"""Contrôle rapide des fichiers bruts (couche Bronze)."""
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw")

for path in sorted(RAW_DIR.glob("*_prices.csv")):
    df = pd.read_csv(path, parse_dates=["Date"])
    print(f"\n=== {path.name} ===")
    print("Lignes, colonnes :", df.shape)
    print("Période          :", df["Date"].min().date(), "->", df["Date"].max().date())
    print("Valeurs manquantes :", int(df.isna().sum().sum()))
    print("Doublons de date   :", int(df["Date"].duplicated().sum()))
    print(df.head(3))