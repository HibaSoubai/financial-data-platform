"""Réconciliation : cours Alpha Vantage (100 derniers jours) contre yfinance (Bronze)."""
import json
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw")
TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]
ALERT_THRESHOLD = 0.005   # 0,5 % d'écart sur le cours de clôture


def load_alpha(ticker: str) -> pd.DataFrame:
    data = json.loads((RAW_DIR / f"alpha_vantage_daily_{ticker}.json").read_text(encoding="utf-8"))
    rows = [
        {"date": d, "av_close": float(v["4. close"]), "av_volume": int(v["5. volume"])}
        for d, v in data["Time Series (Daily)"].items()
    ]
    return pd.DataFrame(rows)


def load_yahoo(ticker: str) -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / f"{ticker}_prices.csv", usecols=["Date", "Close", "Volume"])
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    return df.rename(columns={"Date": "date", "Close": "yf_close", "Volume": "yf_volume"})


def main() -> None:
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.float_format", lambda x: f"{x:.4f}")
    rows, details = [], []
    for ticker in TICKERS:
        try:
            merged = load_alpha(ticker).merge(load_yahoo(ticker), on="date", how="inner")
        except FileNotFoundError as exc:
            print(f"{ticker} : fichier manquant ({exc.filename})")
            continue
        merged["close_diff"] = merged["av_close"] / merged["yf_close"] - 1
        merged["volume_diff"] = merged["av_volume"] / merged["yf_volume"] - 1
        merged["ticker"] = ticker
        details.append(merged)
        rows.append({
            "ticker": ticker,
            "jours_communs": len(merged),
            "ecart_close_median": merged["close_diff"].abs().median(),
            "ecart_close_max": merged["close_diff"].abs().max(),
            "jours_en_alerte": int((merged["close_diff"].abs() > ALERT_THRESHOLD).sum()),
            "ecart_volume_median": merged["volume_diff"].abs().median(),
        })

    if not rows:
        raise SystemExit("Aucune donnée à comparer : lance d'abord alpha_vantage.py")

    print("\n=== Réconciliation Alpha Vantage / yfinance ===\n")
    print(pd.DataFrame(rows).set_index("ticker"))

    all_details = pd.concat(details)
    alerts = all_details[all_details["close_diff"].abs() > ALERT_THRESHOLD]
    if len(alerts):
        print("\n=== Jours en alerte (écart de clôture supérieur à 0,5 %) ===\n")
        print(alerts[["ticker", "date", "av_close", "yf_close", "close_diff"]].head(20).to_string(index=False))
    else:
        print("\nAucun écart de clôture supérieur à 0,5 %.")


if __name__ == "__main__":
    main()