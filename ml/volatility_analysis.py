"""Analyse historique des rendements et de la volatilité, à partir de la couche Gold (Snowflake).

Analyse descriptive du passé : ce n'est ni une prévision, ni un conseil financier.
"""
import logging
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # pas d'écran dans Docker : on écrit des fichiers image
import matplotlib.pyplot as plt
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1] / "warehouse"))
from load_to_snowflake import get_connection  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s", 
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("ml/outputs")
TRADING_DAYS = 252

QUERY = """
SELECT c.ticker, m.full_date, m.adjusted_close, m.volume,
       m.daily_return, m.volatility_20d
FROM FIN_PLATFORM.ANALYTICS.FACT_DAILY_METRICS m
JOIN FIN_PLATFORM.ANALYTICS.DIM_COMPANY c ON c.company_id = m.company_id
ORDER BY c.ticker, m.full_date
"""


def load_data() -> pd.DataFrame:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(QUERY)
            df = cur.fetch_pandas_all()
    finally:
        conn.close()

    df.columns = [c.lower() for c in df.columns]
    df["full_date"] = pd.to_datetime(df["full_date"])
    for col in ["adjusted_close", "volume", "daily_return", "volatility_20d"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    logger.info("Données chargées : %d lignes, %d entreprises", len(df), df["ticker"].nunique())
    return df


def summary_stats(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for ticker, g in df.groupby("ticker"):
        r = g["daily_return"].dropna()
        worst = g.loc[g["daily_return"].idxmin()]
        best = g.loc[g["daily_return"].idxmax()]
        rows.append({
            "ticker": ticker,
            "mean_daily_return": r.mean(),
            "annualized_volatility": r.std() * TRADING_DAYS ** 0.5,
            "skewness": r.skew(),
            "excess_kurtosis": r.kurt(),
            "worst_day": worst["full_date"].date(),
            "worst_return": worst["daily_return"],
            "best_day": best["full_date"].date(),
            "best_return": best["daily_return"],
        })
    return pd.DataFrame(rows).set_index("ticker")


def yearly_volatility(df: pd.DataFrame) -> pd.DataFrame:
    tmp = df.assign(year=df["full_date"].dt.year)
    vol = tmp.groupby(["year", "ticker"])["daily_return"].std().unstack("ticker")
    return vol * TRADING_DAYS ** 0.5


def correlation(df: pd.DataFrame) -> pd.DataFrame:
    pivot = df.pivot(index="full_date", columns="ticker", values="daily_return")
    return pivot.corr()


def clustering(df: pd.DataFrame) -> pd.DataFrame:
    """Autocorrélation à 1 jour des rendements et de leur valeur absolue."""
    rows = []
    for ticker, g in df.groupby("ticker"):
        r = g["daily_return"].dropna()
        rows.append({
            "ticker": ticker,
            "autocorr_returns_lag1": r.autocorr(1),
            "autocorr_abs_returns_lag1": r.abs().autocorr(1),
        })
    return pd.DataFrame(rows).set_index("ticker")


def plot_normalized_prices(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(11, 5))
    for ticker, g in df.groupby("ticker"):
        g = g.sort_values("full_date")
        ax.plot(g["full_date"], g["adjusted_close"] / g["adjusted_close"].iloc[0] * 100, label=ticker)
    ax.set_title("Performance comparée (base 100 au premier jour, prix ajustés)")
    ax.set_ylabel("Base 100")
    ax.set_yscale("log")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "normalized_prices.png", dpi=120)
    plt.close(fig)


def plot_volatility(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(11, 5))
    for ticker, g in df.groupby("ticker"):
        g = g.sort_values("full_date")
        ax.plot(g["full_date"], g["volatility_20d"], label=ticker, linewidth=1)
    ax.set_title("Volatilité annualisée glissante sur 20 jours")
    ax.set_ylabel("Volatilité annualisée")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "rolling_volatility.png", dpi=120)
    plt.close(fig)


def plot_correlation(corr: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(corr.values, vmin=0, vmax=1, cmap="viridis")
    ax.set_xticks(range(len(corr)), corr.columns)
    ax.set_yticks(range(len(corr)), corr.index)
    for i in range(len(corr)):
        for j in range(len(corr)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", color="white")
    ax.set_title("Corrélation des rendements journaliers")
    fig.colorbar(im)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "correlation.png", dpi=120)
    plt.close(fig)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.float_format", lambda x: f"{x:.4f}")

    df = load_data()

    stats = summary_stats(df)
    yearly = yearly_volatility(df)
    corr = correlation(df)
    cluster = clustering(df)

    print("\n=== Statistiques par entreprise ===\n", stats)
    print("\n=== Volatilité annualisée par année ===\n", yearly)
    print("\n=== Corrélation des rendements ===\n", corr)
    print("\n=== Regroupement de volatilité (autocorrélation à 1 jour) ===\n", cluster)

    stats.to_csv(OUTPUT_DIR / "summary_stats.csv")
    yearly.to_csv(OUTPUT_DIR / "yearly_volatility.csv")
    corr.to_csv(OUTPUT_DIR / "correlation.csv")
    cluster.to_csv(OUTPUT_DIR / "volatility_clustering.csv")

    plot_normalized_prices(df)
    plot_volatility(df)
    plot_correlation(corr)
    logger.info("Résultats et graphiques écrits dans %s", OUTPUT_DIR)


if __name__ == "__main__":
    main()