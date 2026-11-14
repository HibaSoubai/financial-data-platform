"""DAG principal : Yahoo Finance -> Bronze -> Silver -> Data Lake."""
import time
from datetime import datetime, timedelta
from pathlib import Path

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, task

PROJECT_DIR = "/opt/airflow/project"
TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"]
MIN_FILE_SIZE = 50_000      # octets : en dessous, le fichier est suspect
MAX_FILE_AGE = 2 * 3600     # secondes : au-delà, les données sont périmées

default_args = {
    "owner": "hiba",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="financial_pipeline",
    description="Yahoo Finance -> Bronze -> Silver -> Data Lake",
    start_date=datetime(2026, 11, 1),
    schedule="0 22 * * 1-5",   # lundi à vendredi, 22h UTC (après la clôture américaine)
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["finance", "etl"],
) as dag:

    extract = BashOperator(
        task_id="extract_yahoo_finance",
        bash_command=f"cd {PROJECT_DIR} && FORCE_REFRESH=1 python ingestion/yahoo_finance.py",
    )

    @task
    def validate_raw_files() -> int:
        """Vérifie que les 5 fichiers Bronze existent, ne sont pas vides et sont récents."""
        raw_dir = Path(PROJECT_DIR) / "data" / "raw"
        problems = []
        for ticker in TICKERS:
            path = raw_dir / f"{ticker}_prices.csv"
            if not path.exists():
                problems.append(f"{ticker} : fichier absent")
                continue
            if path.stat().st_size < MIN_FILE_SIZE:
                problems.append(f"{ticker} : fichier trop petit ({path.stat().st_size} octets)")
            if time.time() - path.stat().st_mtime > MAX_FILE_AGE:
                problems.append(f"{ticker} : données périmées")
        if problems:
            raise ValueError("Validation Bronze échouée : " + " ; ".join(problems))
        return len(TICKERS)

    validate = validate_raw_files()

    clean = BashOperator(
        task_id="clean_to_silver",
        bash_command=f"cd {PROJECT_DIR} && python transformations/cleaning.py",
    )

    upload = BashOperator(
        task_id="upload_to_lake",
        bash_command=f"cd {PROJECT_DIR} && python datalake/upload_to_adls.py",
    )

