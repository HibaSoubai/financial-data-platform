USE ROLE FIN_ENGINEER;
USE WAREHOUSE FIN_WH;

SELECT check_name, violations, IFF(violations = 0, 'OK', 'ECHEC') AS status
FROM (
    SELECT 'doublons_date_entreprise' AS check_name, COUNT(*) AS violations
    FROM (
        SELECT date_id, company_id
        FROM FIN_PLATFORM.ANALYTICS.FACT_STOCK_PRICES
        GROUP BY date_id, company_id
        HAVING COUNT(*) > 1
    )
    UNION ALL
    SELECT 'prix_nuls_ou_negatifs', COUNT(*)
    FROM FIN_PLATFORM.ANALYTICS.FACT_STOCK_PRICES
    WHERE open_price IS NULL OR high_price IS NULL OR low_price IS NULL
       OR close_price IS NULL OR adjusted_close IS NULL
       OR open_price <= 0 OR high_price <= 0 OR low_price <= 0
       OR close_price <= 0 OR adjusted_close <= 0
    UNION ALL
    SELECT 'high_inferieur_a_low', COUNT(*)
    FROM FIN_PLATFORM.ANALYTICS.FACT_STOCK_PRICES
    WHERE high_price < low_price
    UNION ALL
    SELECT 'volume_negatif', COUNT(*)
    FROM FIN_PLATFORM.ANALYTICS.FACT_STOCK_PRICES
    WHERE volume < 0
    UNION ALL
    SELECT 'faits_sans_entreprise', COUNT(*)
    FROM FIN_PLATFORM.ANALYTICS.FACT_STOCK_PRICES f
    LEFT JOIN FIN_PLATFORM.ANALYTICS.DIM_COMPANY c ON c.company_id = f.company_id
    WHERE c.company_id IS NULL
    UNION ALL
    SELECT 'faits_sans_date', COUNT(*)
    FROM FIN_PLATFORM.ANALYTICS.FACT_STOCK_PRICES f
    LEFT JOIN FIN_PLATFORM.ANALYTICS.DIM_DATE d ON d.date_id = f.date_id
    WHERE d.date_id IS NULL
    UNION ALL
    SELECT 'rendements_extremes_sup_20pct', COUNT(*)
    FROM FIN_PLATFORM.ANALYTICS.FACT_DAILY_METRICS
    WHERE ABS(daily_return) > 0.20
    UNION ALL
    SELECT 'donnees_trop_anciennes_sup_4_jours',
           IFF(DATEDIFF('day', MAX(full_date), CURRENT_DATE()) > 4, 1, 0)
    FROM FIN_PLATFORM.ANALYTICS.FACT_DAILY_METRICS
)
ORDER BY check_name;