USE ROLE FIN_ENGINEER;
USE WAREHOUSE FIN_WH;

-- 1) Indicateurs quotidiens par entreprise
CREATE OR REPLACE TABLE FIN_PLATFORM.ANALYTICS.FACT_DAILY_METRICS AS
WITH base AS (
    SELECT
        f.date_id,
        f.company_id,
        d.full_date,
        f.adjusted_close,
        f.volume,
        f.adjusted_close
            / LAG(f.adjusted_close) OVER (PARTITION BY f.company_id ORDER BY f.date_id) - 1
            AS daily_return
    FROM FIN_PLATFORM.ANALYTICS.FACT_STOCK_PRICES f
    JOIN FIN_PLATFORM.ANALYTICS.DIM_DATE d ON d.date_id = f.date_id
)
SELECT
    date_id,
    company_id,
    full_date,
    adjusted_close,
    volume,
    daily_return,
    CASE WHEN COUNT(adjusted_close) OVER (
            PARTITION BY company_id ORDER BY date_id
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) = 20
         THEN AVG(adjusted_close) OVER (
            PARTITION BY company_id ORDER BY date_id
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
    END AS sma_20,
    CASE WHEN COUNT(adjusted_close) OVER (
            PARTITION BY company_id ORDER BY date_id
            ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) = 50
         THEN AVG(adjusted_close) OVER (
            PARTITION BY company_id ORDER BY date_id
            ROWS BETWEEN 49 PRECEDING AND CURRENT ROW)
    END AS sma_50,
    CASE WHEN COUNT(daily_return) OVER (
            PARTITION BY company_id ORDER BY date_id
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) = 20
         THEN STDDEV_SAMP(daily_return) OVER (
            PARTITION BY company_id ORDER BY date_id
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) * SQRT(252)
    END AS volatility_20d,
    adjusted_close
        / FIRST_VALUE(adjusted_close) OVER (PARTITION BY company_id ORDER BY date_id)
        - 1 AS cumulative_return,
    adjusted_close
        / MAX(adjusted_close) OVER (
            PARTITION BY company_id ORDER BY date_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        - 1 AS drawdown
FROM base;

-- 2) Synthèse par entreprise
CREATE OR REPLACE TABLE FIN_PLATFORM.ANALYTICS.AGG_COMPANY_PERFORMANCE AS
SELECT
    c.company_id,
    c.ticker,
    c.company_name,
    MIN(m.full_date)                                        AS first_date,
    MAX(m.full_date)                                        AS last_date,
    COUNT(*)                                                AS trading_days,
    MIN_BY(m.adjusted_close, m.full_date)                   AS first_adj_close,
    MAX_BY(m.adjusted_close, m.full_date)                   AS last_adj_close,
    MAX_BY(m.adjusted_close, m.full_date)
        / MIN_BY(m.adjusted_close, m.full_date) - 1         AS total_return,
    POWER(
        MAX_BY(m.adjusted_close, m.full_date) / MIN_BY(m.adjusted_close, m.full_date),
        365.25 / NULLIF(DATEDIFF('day', MIN(m.full_date), MAX(m.full_date)), 0)
    ) - 1                                                   AS cagr,
    STDDEV_SAMP(m.daily_return) * SQRT(252)                 AS annualized_volatility,
    MIN(m.drawdown)                                         AS max_drawdown,
    AVG(m.volume)                                           AS avg_volume
FROM FIN_PLATFORM.ANALYTICS.FACT_DAILY_METRICS m
JOIN FIN_PLATFORM.ANALYTICS.DIM_COMPANY c ON c.company_id = m.company_id
GROUP BY c.company_id, c.ticker, c.company_name;
-- 3) Cours + indicateurs macro tels que connus à chaque date (sans fuite d'information)
CREATE OR REPLACE TABLE FIN_PLATFORM.ANALYTICS.GOLD_MARKET_MACRO AS
WITH macro AS (
    SELECT
        f.series_id,
        f.obs_value,
        CASE m.frequency
            WHEN 'mensuelle' THEN DATEADD('month', 2, d.full_date)
            ELSE DATEADD('day', 1, d.full_date)
        END AS available_from
    FROM FIN_PLATFORM.ANALYTICS.FACT_MACRO_INDICATORS f
    JOIN FIN_PLATFORM.ANALYTICS.DIM_DATE d ON d.date_id = f.date_id
    JOIN FIN_PLATFORM.ANALYTICS.DIM_MACRO_SERIES m ON m.series_id = f.series_id
),
calendar AS (
    SELECT DISTINCT date_id, full_date
    FROM FIN_PLATFORM.ANALYTICS.FACT_DAILY_METRICS
),
macro_asof AS (
    SELECT c.date_id, m.series_id, m.obs_value
    FROM calendar c
    JOIN macro m ON m.available_from <= c.full_date
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY c.date_id, m.series_id
        ORDER BY m.available_from DESC
    ) = 1
),
macro_wide AS (
    SELECT
        date_id,
        MAX(IFF(series_id = 'DGS10',    obs_value, NULL)) AS us10y_yield,
        MAX(IFF(series_id = 'VIXCLS',   obs_value, NULL)) AS vix,
        MAX(IFF(series_id = 'FEDFUNDS', obs_value, NULL)) AS fed_funds_rate,
        MAX(IFF(series_id = 'UNRATE',   obs_value, NULL)) AS unemployment_rate,
        MAX(IFF(series_id = 'CPIAUCSL', obs_value, NULL)) AS cpi_index
    FROM macro_asof
    GROUP BY date_id
)


SELECT
    c.ticker,
    m.*,
    w.us10y_yield,
    w.vix,
    w.fed_funds_rate,
    w.unemployment_rate,
    w.cpi_index
FROM FIN_PLATFORM.ANALYTICS.FACT_DAILY_METRICS m
JOIN FIN_PLATFORM.ANALYTICS.DIM_COMPANY c ON c.company_id = m.company_id
LEFT JOIN macro_wide w ON w.date_id = m.date_id;