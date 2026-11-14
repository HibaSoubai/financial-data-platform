"""DAG de test : vérifie qu'Airflow voit notre projet et nos bibliothèques."""
from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

with DAG(
    dag_id="hello_finance",
    start_date=datetime(2026, 11, 1),
    schedule=None,          # lancement manuel uniquement
    catchup=False,          # ne rejoue pas les dates passées
    tags=["test"],
) as dag:
    check_project = BashOperator(
        task_id="check_project",
        bash_command="ls /opt/airflow/project",
    )
    check_libs = BashOperator(
        task_id="check_libs",
        bash_command="python -c \"import pandas, yfinance; print('pandas', pandas.__version__)\"",
    )

