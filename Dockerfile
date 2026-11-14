FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir pandas numpy pyarrow yfinance pytest azure-storage-file-datalake python-dotenv "snowflake-connector-python[pandas]"

CMD ["python", "--version"]
