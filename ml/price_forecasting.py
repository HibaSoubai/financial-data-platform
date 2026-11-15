"""Expérimentation de modèles de prévision (volatilité et direction) avec Scikit-learn.

Expérience d'apprentissage : ce n'est ni un outil de trading, ni un conseil financier.
Séparation temporelle stricte, écart entre entraînement et test, comparaison à des références.
"""
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from volatility_analysis import load_data  # même dossier : ml/

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("ml/outputs")
SPLIT_DATE = "2025-01-01"   # le test commence à cette date
HORIZON = 5                 # jours de bourse de la cible de volatilité
ANN = 252 ** 0.5            # annualisation
SEED = 42

FEATURES = [
    "ret_lag0", "ret_lag1", "ret_lag2", "ret_lag4", "abs_ret_lag0",
    "ret_mean_5", "ret_mean_20",
    "vol_5", "vol_20", "vol_60",
    "volume_ratio", "price_vs_sma20", "sma20_vs_sma50", "drawdown",
]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Variables explicatives (passé uniquement) et cibles (futur), calculées par entreprise."""
    frames = []
    for _, g in df.sort_values(["ticker", "full_date"]).groupby("ticker"):
        g = g.reset_index(drop=True).copy()
        r = g["daily_return"]
        price = g["adjusted_close"]

        g["ret_lag0"] = r
        g["ret_lag1"] = r.shift(1)
        g["ret_lag2"] = r.shift(2)
        g["ret_lag4"] = r.shift(4)
        g["abs_ret_lag0"] = r.abs()
        g["ret_mean_5"] = r.rolling(5).mean()
        g["ret_mean_20"] = r.rolling(20).mean()
        g["vol_5"] = r.rolling(5).std() * ANN
        g["vol_20"] = r.rolling(20).std() * ANN
        g["vol_60"] = r.rolling(60).std() * ANN
        g["volume_ratio"] = g["volume"] / g["volume"].rolling(20).mean()
        sma20 = price.rolling(20).mean()
        sma50 = price.rolling(50).mean()
        g["price_vs_sma20"] = price / sma20 - 1
        g["sma20_vs_sma50"] = sma20 / sma50 - 1
        g["drawdown"] = price / price.cummax() - 1

        # Cibles : elles regardent le futur, elles ne servent JAMAIS de variables
        g["target_vol_5d"] = r.rolling(HORIZON).std().shift(-HORIZON) * ANN
        nxt = r.shift(-1)
        g["target_up"] = (nxt > 0).astype(float).where(nxt.notna())
        frames.append(g)
    return pd.concat(frames, ignore_index=True)


def temporal_split(data: pd.DataFrame):
    """Entraînement avant SPLIT_DATE (moins HORIZON jours d'écart), test à partir de SPLIT_DATE."""
    dates = pd.Series(data["full_date"].unique()).sort_values().tolist()
    split_idx = next(i for i, d in enumerate(dates) if d >= pd.Timestamp(SPLIT_DATE))
    train_dates = set(dates[: split_idx - HORIZON])
    test_dates = set(dates[split_idx:])
    train = data[data["full_date"].isin(train_dates)]
    test = data[data["full_date"].isin(test_dates)]
    logger.info(
        "Entraînement : %s -> %s | Test : %s -> %s",
        min(train_dates).date(), max(train_dates).date(),
        min(test_dates).date(), max(test_dates).date(),
    )
    return train, test


def regression_metrics(y_true, y_pred) -> dict:
    return {
        "MAE": mean_absolute_error(y_true, y_pred),
        "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "R2": r2_score(y_true, y_pred),
    }


def run_volatility(train: pd.DataFrame, test: pd.DataFrame):
    cols = FEATURES + ["target_vol_5d"]
    train = train.dropna(subset=cols)
    test = test.dropna(subset=cols).copy()
    X_train, y_train = train[FEATURES], train["target_vol_5d"]
    X_test, y_test = test[FEATURES], test["target_vol_5d"]
    logger.info("Volatilité : %d lignes d'entraînement, %d de test", len(train), len(test))

    preds = {
        "ref_vol_20j (persistance)": test["vol_20"].to_numpy(),
        "ref_vol_5j": test["vol_5"].to_numpy(),
    }
    models = {
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
        "random_forest": RandomForestRegressor(
            n_estimators=300, max_depth=6, min_samples_leaf=20, random_state=SEED, n_jobs=-1
        ),
        "hist_gradient_boosting": HistGradientBoostingRegressor(
            max_depth=3, learning_rate=0.05, max_iter=200, random_state=SEED
        ),
    }
    fitted = {}
    for name, model in models.items():
        model.fit(X_train, y_train)
        preds[name] = model.predict(X_test)
        fitted[name] = model

    results = pd.DataFrame(
        {name: regression_metrics(y_test, p) for name, p in preds.items()}
    ).T
    base_mae = results.loc["ref_vol_20j (persistence)", "MAE"]
    results["gain_MAE_vs_ref_20j"] = 1 - results["MAE"] / base_mae
    return results.sort_values("MAE"), test, preds, fitted


def run_direction(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    cols = FEATURES + ["target_up"]
    train = train.dropna(subset=cols)
    test = test.dropna(subset=cols)
    X_train, y_train = train[FEATURES], train["target_up"].astype(int)
    X_test, y_test = test[FEATURES], test["target_up"].astype(int)
    logger.info(
        "Direction : part de hausses = %.1f %% (entraînement) et %.1f %% (test)",
        100 * y_train.mean(), 100 * y_test.mean(),
    )

    models = {
        "ref_toujours_la_classe_majoritaire": DummyClassifier(strategy="most_frequent"),
        "logistic_regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
        "random_forest": RandomForestClassifier(
            n_estimators=300, max_depth=5, min_samples_leaf=50, random_state=SEED, n_jobs=-1
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            max_depth=3, learning_rate=0.05, max_iter=150, random_state=SEED
        ),
    }
    rows = {}
    for name, model in models.items():
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
        proba = model.predict_proba(X_test)[:, 1]
        rows[name] = {
            "accuracy": accuracy_score(y_test, pred),
            "balanced_accuracy": balanced_accuracy_score(y_test, pred),
            "roc_auc": roc_auc_score(y_test, proba),
        }
    return pd.DataFrame(rows).T.sort_values("roc_auc", ascending=False)


def plot_volatility_forecast(test, preds, best, ticker="NVDA") -> None:
    plot_df = test.assign(prediction=preds[best], reference=test["vol_20"])
    g = plot_df[plot_df["ticker"] == ticker].sort_values("full_date")
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(g["full_date"], g["target_vol_5d"], label="Volatilité réalisée (5 j suivants)", linewidth=1.5)
    ax.plot(g["full_date"], g["prediction"], label=f"Prévision : {best}", linewidth=1)
    ax.plot(g["full_date"], g["reference"], label="Référence : volatilité 20 j", linewidth=1, alpha=0.7)
    ax.set_title(f"{ticker} : volatilité prévue contre réalisée (période de test)")
    ax.set_ylabel("Volatilité annualisée")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "volatility_forecast.png", dpi=120)
    plt.close(fig)


def plot_feature_importance(fitted) -> None:
    model = fitted["random_forest"]
    imp = pd.Series(model.feature_importances_, index=FEATURES).sort_values()
    fig, ax = plt.subplots(figsize=(8, 5))
    imp.plot.barh(ax=ax)
    ax.set_title("Importance des variables (random forest, volatilité)")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "feature_importance.png", dpi=120)
    plt.close(fig)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 200)
    pd.set_option("display.float_format", lambda x: f"{x:.4f}")

    data = build_features(load_data())
    train, test = temporal_split(data)

    vol_results, vol_test, vol_preds, vol_models = run_volatility(train, test)
    dir_results = run_direction(train, test)

    print("\n=== Prévision de la volatilité (test) ===\n", vol_results)
    print("\n=== Prévision de la direction du lendemain (test) ===\n", dir_results)
    print("\nRappel : expérience pédagogique, pas un conseil financier.")

    vol_results.to_csv(OUTPUT_DIR / "forecast_volatility_results.csv")
    dir_results.to_csv(OUTPUT_DIR / "forecast_direction_results.csv")

    best = vol_results.index[0]
    if best.startswith("ref_"):
        best = vol_results.drop(index=[i for i in vol_results.index if i.startswith("ref_")]).index[0]
    plot_volatility_forecast(vol_test, vol_preds, best)
    plot_feature_importance(vol_models)
    logger.info("Résultats et graphiques écrits dans %s", OUTPUT_DIR)


if __name__ == "__main__":
    main()