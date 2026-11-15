"""Tests anti-fuite d'information pour la préparation des variables de prévision."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "warehouse"))

from price_forecasting import FEATURES, HORIZON, build_features, temporal_split  # noqa: E402


def make_prices(n=200, tickers=("TEST",), start="2023-01-02", seed=0):
    rng = np.random.default_rng(seed)
    frames = []
    for ticker in tickers:
        dates = pd.bdate_range(start, periods=n)
        returns = rng.normal(0.0005, 0.02, n)
        price = 100 * np.cumprod(1 + returns)
        df = pd.DataFrame({
            "ticker": ticker,
            "full_date": dates,
            "adjusted_close": price,
            "volume": rng.integers(1_000_000, 2_000_000, n).astype(float),
        })
        df["daily_return"] = df["adjusted_close"].pct_change()
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def test_les_variables_n_utilisent_pas_le_futur():
    """Calculer les variables sur un historique tronqué donne les mêmes valeurs que sur l'historique complet."""
    df = make_prices()
    full = build_features(df)
    k = 120
    partial = build_features(df.iloc[:k])
    pd.testing.assert_frame_equal(
        full.loc[: k - 1, FEATURES].reset_index(drop=True),
        partial[FEATURES].reset_index(drop=True),
    )


def test_la_cible_de_volatilite_est_celle_des_5_jours_suivants():
    df = make_prices()
    out = build_features(df)
    t = 50
    expected = df["daily_return"].iloc[t + 1: t + 1 + HORIZON].std() * (252 ** 0.5)
    assert out.loc[t, "target_vol_5d"] == pytest.approx(expected)


def test_les_dernieres_lignes_n_ont_pas_de_cible():
    out = build_features(make_prices())
    assert out["target_vol_5d"].iloc[-HORIZON:].isna().all()
    assert pd.isna(out["target_up"].iloc[-1])


def test_ecart_entre_entrainement_et_test():
    data = build_features(make_prices(n=400, tickers=("A", "B"), start="2024-06-03"))
    train, test = temporal_split(data)
    train_max = train["full_date"].max()
    test_min = test["full_date"].min()
    assert train_max < test_min
    all_dates = sorted(data["full_date"].unique())
    between = [d for d in all_dates if train_max < d < test_min]
    assert len(between) == HORIZON