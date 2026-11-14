import pandas as pd

df = pd.read_csv("data/raw/AAPL_prices.csv", parse_dates=["Date"])

# 1. Jour du volume maximal
idx = df["Volume"].idxmax()
print("Volume max :", df.loc[idx, "Date"].date(), int(df.loc[idx, "Volume"]))

# 2. Close vs Adj Close à la date la plus ancienne
first = df.sort_values("Date").iloc[0]
print("Première date :", first["Date"].date())
print("Close     :", first["Close"])
print("Adj Close :", first["Adj Close"])