import yfinance as yf
import pandas as pd

# Entreprises à analyser
tickers = ["AAPL", "MSFT", "NVDA"]

# Récupération des données
data = yf.download(
    tickers,
    period="1mo",
    interval="1d",
    auto_adjust=True
)

print(data.head())