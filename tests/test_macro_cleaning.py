import pandas as pd
import pytest

from transformations.macro_cleaning import clean_series


def raw(rows):
    return pd.DataFrame(rows, columns=["date", "value", "series_id"])


def test_point_devient_valeur_manquante_et_est_supprime():
    df = raw([["2024-01-01", ".", "DGS10"], ["2024-01-02", "4.1", "DGS10"]])
    out = clean_series(df, "DGS10")
    assert len(out) == 1
    assert out.loc[0, "value"] == pytest.approx(4.1)


def test_doublon_de_date_garde_la_derniere_valeur():
    df = raw([["2024-01-02", "4.0", "DGS10"], ["2024-01-02", "4.1", "DGS10"]])
    out = clean_series(df, "DGS10")
    assert len(out) == 1
    assert out.loc[0, "value"] == pytest.approx(4.1)


def test_valeur_hors_plage_supprimee():
    df = raw([["2024-01-02", "500", "DGS10"], ["2024-01-03", "4.2", "DGS10"]])
    out = clean_series(df, "DGS10")
    assert len(out) == 1
    assert out.loc[0, "value"] == pytest.approx(4.2)


def test_colonnes_de_sortie():
    df = raw([["2024-01-02", "4.0", "DGS10"]])
    out = clean_series(df, "DGS10")
    assert list(out.columns) == ["series_id", "date", "value"]
    assert out.loc[0, "series_id"] == "DGS10"