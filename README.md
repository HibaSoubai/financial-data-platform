# Financial Data Engineering Platform

Pipeline de données financières de bout en bout : ingestion (yfinance, Alpha Vantage, FRED),
Data Lake (architecture Medallion), orchestration Airflow, Snowflake, Power BI, ML.

## Statut
- [x] Phase 1 : ingestion des cours boursiers (yfinance, couche Bronze)
- [ ] Phase 2 : pipeline ETL
- [ ] Phases 3 à 9

## Installation (Windows / PowerShell)
    python -m venv venv
    .\venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    python ingestion/yahoo_finance.py