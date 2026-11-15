"""Charge la couche Silver (Parquet) dans Snowflake : STAGING puis MERGE dans FACT_STOCK_PRICES."""
import logging
import os
import sys
from pathlib import Path

import pandas as pd
import snowflake.connector
from dotenv import load_dotenv
from snowflake.connector.pandas_tools import write_pandas

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


class _QuietThirdParty(logging.Filter):
    """Masque les logs INFO des bibliothèques tierces (le connecteur Snowflake est très bavard)."""

    def filter(self, record):
        return record.levelno >= logging.WARNING or record.name in ("__main__", __name__)


for _handler in logging.getLogger().handlers:
    _handler.addFilter(_QuietThirdParty())

load_dotenv()

SILVER_FILE = Path("data/processed/stock_prices_silver.parquet")
DB = os.getenv("SNOWFLAKE_DATABASE", "FIN_PLATFORM")
STAGING_TABLE = "STOCK_PRICES_SILVER"
STAGING_FQN = f"{DB}.STAGING.{STAGING_TABLE}"
FACT_FQN = f"{DB}.ANALYTICS.FACT_STOCK_PRICES"
COMPANY_FQN = f"{DB}.ANALYTICS.DIM_COMPANY"
DATE_FQN = f"{DB}.ANALYTICS.DIM_DATE"

CREATE_STAGING = f"""
CREATE TABLE IF NOT EXISTS {STAGING_FQN} (
    TRADE_DATE      VARCHAR(10),
    TICKER          VARCHAR(10),
    OPEN_PRICE      FLOAT,
    HIGH_PRICE      FLOAT,
    LOW_PRICE       FLOAT,
    CLOSE_PRICE     FLOAT,
    ADJUSTED_CLOSE  FLOAT,
    VOLUME          NUMBER(20,0)
)
"""

MERGE_FACT = f"""
MERGE INTO {FACT_FQN} f
USING (
    SELECT d.date_id, c.company_id,
           s.OPEN_PRICE, s.HIGH_PRICE, s.LOW_PRICE,
           s.CLOSE_PRICE, s.ADJUSTED_CLOSE, s.VOLUME
    FROM {STAGING_FQN} s
    JOIN {COMPANY_FQN} c ON c.ticker = s.TICKER
    JOIN {DATE_FQN} d ON d.full_date = TO_DATE(s.TRADE_DATE)
) src
ON f.date_id = src.date_id AND f.company_id = src.company_id
WHEN MATCHED THEN UPDATE SET
    open_price = src.OPEN_PRICE,
    high_price = src.HIGH_PRICE,
    low_price = src.LOW_PRICE,
    close_price = src.CLOSE_PRICE,
    adjusted_close = src.ADJUSTED_CLOSE,
    volume = src.VOLUME
WHEN NOT MATCHED THEN INSERT
    (date_id, company_id, open_price, high_price, low_price,
     close_price, adjusted_close, volume)
VALUES
    (src.date_id, src.company_id, src.OPEN_PRICE, src.HIGH_PRICE, src.LOW_PRICE,
     src.CLOSE_PRICE, src.ADJUSTED_CLOSE, src.VOLUME)
"""

COLUMN_MAP = {
    "date": "TRADE_DATE",
    "ticker": "TICKER",
    "open": "OPEN_PRICE",
    "high": "HIGH_PRICE",
    "low": "LOW_PRICE",
    "close": "CLOSE_PRICE",
    "adj_close": "ADJUSTED_CLOSE",
    "volume": "VOLUME",
}


def get_connection():
    required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise SystemExit(f"Variables manquantes dans .env : {missing}")
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=os.getenv("SNOWFLAKE_ROLE", "FIN_ENGINEER"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "FIN_WH"),
        database=DB,
    )


def load_silver() -> pd.DataFrame:
    if not SILVER_FILE.exists():
        raise SystemExit(f"Fichier Silver introuvable : {SILVER_FILE}")
    df = pd.read_parquet(SILVER_FILE)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df.rename(columns=COLUMN_MAP)[list(COLUMN_MAP.values())]
    logger.info("Silver lu : %d lignes", len(df))
    return df


def scalar(cur, sql: str) -> int:
    cur.execute(sql)
    return cur.fetchone()[0]


def main() -> None:
    df = load_silver()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_STAGING)
            cur.execute(f"TRUNCATE TABLE {STAGING_FQN}")

        success, _, nrows, _ = write_pandas(
            conn, df, STAGING_TABLE, database=DB, schema="STAGING"
        )
        if not success:
            raise RuntimeError("write_pandas a échoué")
        logger.info("Staging chargé : %d lignes", nrows)

        with conn.cursor() as cur:
            matched = scalar(
                cur,
                f"""SELECT COUNT(*) FROM {STAGING_FQN} s
                    JOIN {COMPANY_FQN} c ON c.ticker = s.TICKER
                    JOIN {DATE_FQN} d ON d.full_date = TO_DATE(s.TRADE_DATE)""",
            )
            if matched != nrows:
                logger.error(
                    "%d lignes sans correspondance (ticker ou date absents des dimensions)",
                    nrows - matched,
                )
                sys.exit(1)

            cur.execute(MERGE_FACT)
            total = scalar(cur, f"SELECT COUNT(*) FROM {FACT_FQN}")
            logger.info("FACT_STOCK_PRICES : %d lignes", total)
    finally:
        conn.close()


if __name__ == "__main__":
    main()