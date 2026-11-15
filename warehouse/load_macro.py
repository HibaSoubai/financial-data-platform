"""Charge les indicateurs FRED (Silver) dans Snowflake : staging, dimension, MERGE dans la table de faits."""
import logging
import sys
from pathlib import Path

import pandas as pd
from snowflake.connector.pandas_tools import write_pandas

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))
from load_to_snowflake import get_connection  # noqa: E402
from transformations.macro_cleaning import SERIES_INFO  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

SILVER_FILE = Path("data/processed/macro_indicators_silver.parquet")
DDL_FILE = Path("snowflake/macro_tables.sql")
DB = "FIN_PLATFORM"
STAGING_FQN = f"{DB}.STAGING.MACRO_INDICATORS_SILVER"
DIM_FQN = f"{DB}.ANALYTICS.DIM_MACRO_SERIES"
FACT_FQN = f"{DB}.ANALYTICS.FACT_MACRO_INDICATORS"
DATE_FQN = f"{DB}.ANALYTICS.DIM_DATE"

MERGE_DIM = f"""
MERGE INTO {DIM_FQN} t
USING (SELECT %s AS series_id, %s AS description, %s AS frequency, %s AS unit) s
ON t.series_id = s.series_id
WHEN MATCHED THEN UPDATE SET description = s.description, frequency = s.frequency, unit = s.unit
WHEN NOT MATCHED THEN INSERT (series_id, description, frequency, unit)
    VALUES (s.series_id, s.description, s.frequency, s.unit)
"""

JOINED = f"""
    SELECT d.date_id, s.SERIES_ID AS series_id, s.OBS_VALUE AS obs_value
    FROM {STAGING_FQN} s
    JOIN {DATE_FQN} d ON d.full_date = TO_DATE(s.OBS_DATE)
    JOIN {DIM_FQN} m ON m.series_id = s.SERIES_ID
"""

MERGE_FACT = f"""
MERGE INTO {FACT_FQN} f
USING ({JOINED}) src
ON f.date_id = src.date_id AND f.series_id = src.series_id
WHEN MATCHED THEN UPDATE SET obs_value = src.obs_value
WHEN NOT MATCHED THEN INSERT (date_id, series_id, obs_value)
    VALUES (src.date_id, src.series_id, src.obs_value)
"""


def scalar(cur, sql: str) -> int:
    cur.execute(sql)
    return cur.fetchone()[0]


def main() -> None:
    if not SILVER_FILE.exists():
        raise SystemExit(f"Fichier Silver introuvable : {SILVER_FILE} (lance macro_cleaning.py)")
    df = pd.read_parquet(SILVER_FILE)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df.rename(columns={"series_id": "SERIES_ID", "date": "OBS_DATE", "value": "OBS_VALUE"})
    df = df[["SERIES_ID", "OBS_DATE", "OBS_VALUE"]]
    logger.info("Silver macro lu : %d lignes", len(df))

    conn = get_connection()
    try:
        conn.execute_string(DDL_FILE.read_text(encoding="utf-8"))

        with conn.cursor() as cur:
            for series_id, (description, frequency, unit, _, _) in SERIES_INFO.items():
                cur.execute(MERGE_DIM, (series_id, description, frequency, unit))
            cur.execute(f"TRUNCATE TABLE {STAGING_FQN}")

        success, _, nrows, _ = write_pandas(
            conn, df, "MACRO_INDICATORS_SILVER", database=DB, schema="STAGING"
        )
        if not success:
            raise RuntimeError("write_pandas a échoué")
        logger.info("Staging chargé : %d lignes", nrows)

        with conn.cursor() as cur:
            matched = scalar(cur, f"SELECT COUNT(*) FROM ({JOINED})")
            if matched != nrows:
                logger.error(
                    "%d lignes sans correspondance (date hors DIM_DATE ou série inconnue)",
                    nrows - matched,
                )
                sys.exit(1)

            cur.execute(MERGE_FACT)
            logger.info("FACT_MACRO_INDICATORS : %d lignes", scalar(cur, f"SELECT COUNT(*) FROM {FACT_FQN}"))
    finally:
        conn.close()


if __name__ == "__main__":
    main()