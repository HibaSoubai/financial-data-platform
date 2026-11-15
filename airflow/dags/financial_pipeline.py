"""DAG principal : cours (yfinance) + macro (FRED) -> Bronze -> Silver -> Lake -> Snowflake -> Gold -> Qualité."""
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


def run(script: str, env: str = "") -> str:
    return f"cd {PROJECT_DIR} && {env} python {script}".replace("&&  python", "&& python")


with DAG(
    dag_id="financial_pipeline",
    description="Cours + macro -> Bronze -> Silver -> Lake -> Snowflake -> Gold -> Qualité",
    start_date=datetime(2026, 11, 1),
    schedule="0 22 * * 1-5",   # lundi à vendredi, 22h UTC (après la clôture américaine)
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["finance", "etl", "elt"],
) as dag:

    # --- Branche 1 : cours boursiers ---
    extract = BashOperator(
        task_id="extract_yahoo_finance",
        bash_command=run("ingestion/yahoo_finance.py", "FORCE_REFRESH=1"),
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

    clean = BashOperator(task_id="clean_to_silver", bash_command=run("transformations/cleaning.py"))
    upload = BashOperator(task_id="upload_to_lake", bash_command=run("datalake/upload_to_adls.py"))
    load_warehouse = BashOperator(task_id="load_to_snowflake", bash_command=run("warehouse/load_to_snowflake.py"))

    # Recoupement avec Alpha Vantage : informatif, sans nouvelle tentative (le quota gratuit est limité)
    crosscheck = BashOperator(
        task_id="crosscheck_alpha_vantage",
        bash_command=f"cd {PROJECT_DIR} && python ingestion/alpha_vantage.py && python ingestion/compare_sources.py",
        retries=0,
    )

    # --- Branche 2 : indicateurs macroéconomiques ---
    extract_fred = BashOperator(task_id="extract_fred", bash_command=run("ingestion/fred_api.py"))
    clean_macro = BashOperator(task_id="clean_macro", bash_command=run("transformations/macro_cleaning.py"))
    load_macro = BashOperator(task_id="load_macro", bash_command=run("warehouse/load_macro.py"))

    # --- Convergence : Gold puis qualité ---
    build_gold = BashOperator(task_id="build_gold_metrics", bash_command=run("warehouse/run_sql.py gold"))
    quality = BashOperator(task_id="data_quality_checks", bash_command=run("warehouse/run_sql.py quality"))

    extract >> validate >> clean >> upload >> load_warehouse
    extract >> crosscheck
    extract_fred >> clean_macro >> load_macro
    [load_warehouse, load_macro] >> build_gold >> quality