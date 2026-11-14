USE ROLE FIN_ENGINEER;
USE WAREHOUSE FIN_WH;
USE SCHEMA FIN_PLATFORM.ANALYTICS;

-- Dimension entreprise
CREATE TABLE IF NOT EXISTS DIM_COMPANY (
    company_id    NUMBER AUTOINCREMENT PRIMARY KEY,
    ticker        VARCHAR(10)  NOT NULL,
    company_name  VARCHAR(100) NOT NULL,
    sector        VARCHAR(100),
    industry      VARCHAR(100)
);

-- Dimension date
CREATE TABLE IF NOT EXISTS DIM_DATE (
    date_id       NUMBER(8,0) PRIMARY KEY,   -- format AAAAMMJJ
    full_date     DATE         NOT NULL,
    day           NUMBER(2,0)  NOT NULL,
    month         NUMBER(2,0)  NOT NULL,
    month_name    VARCHAR(10)  NOT NULL,
    quarter       NUMBER(1,0)  NOT NULL,
    year          NUMBER(4,0)  NOT NULL,
    day_of_week   NUMBER(1,0)  NOT NULL,     -- 1 = lundi ... 7 = dimanche
    is_weekend    BOOLEAN      NOT NULL
);

-- Table de faits : une ligne par entreprise et par jour de bourse
CREATE TABLE IF NOT EXISTS FACT_STOCK_PRICES (
    date_id         NUMBER(8,0)   NOT NULL REFERENCES DIM_DATE (date_id),
    company_id      NUMBER        NOT NULL REFERENCES DIM_COMPANY (company_id),
    open_price      NUMBER(18,6),
    high_price      NUMBER(18,6),
    low_price       NUMBER(18,6),
    close_price     NUMBER(18,6),
    adjusted_close  NUMBER(18,6),
    volume          NUMBER(20,0),
    PRIMARY KEY (date_id, company_id)
);

-- Charge les 5 entreprises (MERGE = relançable sans doublon)
MERGE INTO DIM_COMPANY t
USING (
    SELECT * FROM VALUES
        ('AAPL',  'Apple Inc.',            'Information Technology', 'Technology Hardware'),
        ('MSFT',  'Microsoft Corporation', 'Information Technology', 'Software'),
        ('NVDA',  'NVIDIA Corporation',    'Information Technology', 'Semiconductors'),
        ('AMZN',  'Amazon.com, Inc.',      'Consumer Discretionary', 'Broadline Retail'),
        ('GOOGL', 'Alphabet Inc.',         'Communication Services', 'Interactive Media')
    AS v (ticker, company_name, sector, industry)
) s
ON t.ticker = s.ticker
WHEN NOT MATCHED THEN
    INSERT (ticker, company_name, sector, industry)
    VALUES (s.ticker, s.company_name, s.sector, s.industry);

-- Génère le calendrier du 2020-01-01 au 2027-12-31 (INSERT OVERWRITE = idempotent)
INSERT OVERWRITE INTO DIM_DATE
SELECT
    TO_NUMBER(TO_CHAR(d, 'YYYYMMDD')),
    d,
    DAY(d),
    MONTH(d),
    MONTHNAME(d),
    QUARTER(d),
    YEAR(d),
    DAYOFWEEKISO(d),
    IFF(DAYOFWEEKISO(d) >= 6, TRUE, FALSE)
FROM (
    SELECT DATEADD(day, ROW_NUMBER() OVER (ORDER BY SEQ4()) - 1, '2020-01-01'::DATE) AS d
    FROM TABLE(GENERATOR(ROWCOUNT => 3000))
)
WHERE d <= '2027-12-31'::DATE;