from datetime import date

import pandas as pd

from transformations.cleaning import clean, standardize


def make_raw(rows):
    cols = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume", "ticker"]
    return pd.DataFrame(rows, columns=cols)


def test_doublons_supprimes():
    raw = make_raw([
        ["2024-01-02", 10, 12, 9, 11, 11, 100, "AAPL"],
        ["2024-01-02", 10, 12, 9, 11, 11, 100, "AAPL"],
    ])
    out = clean(standardize(raw), ingestion_date=date(2024, 2, 1))
    assert len(out) == 1


def test_high_inferieur_a_low_supprime():
    raw = make_raw([
        ["2024-01-02", 10, 8, 9, 9, 9, 100, "AAPL"],   # high < low : invalide
        ["2024-01-03", 10, 12, 9, 11, 11, 100, "AAPL"],
    ])
    out = clean(standardize(raw), ingestion_date=date(2024, 2, 1))
    assert len(out) == 1


def test_barre_du_jour_exclue():
    raw = make_raw([
        ["2024-01-02", 10, 12, 9, 11, 11, 100, "AAPL"],
        ["2024-01-03", 10, 12, 9, 11, 11, 100, "AAPL"],
    ])
    out = clean(standardize(raw), ingestion_date=date(2024, 1, 3))
    assert out["date"].dt.date.max() == date(2024, 1, 2)