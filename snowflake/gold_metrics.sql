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