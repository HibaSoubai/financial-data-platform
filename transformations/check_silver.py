"""Vérification de la couche Silver."""
import pandas as pd

df = pd.read_parquet("data/processed/stock_prices_silver.parquet")

print("Forme :", df.shape)
print("\nTypes :\n", df.dtypes)
print("\nLignes par ticker :\n", df.groupby("ticker").size())
print("\nPériode :", df["date"].min().date(), "->", df["date"].max().date())
print("\nValeurs manquantes :", int(df.isna().sum().sum()))
print("Doublons (ticker, date) :", int(df.duplicated(["ticker", "date"]).sum()))
print("\nAperçu :\n", df.head(3))