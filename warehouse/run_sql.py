"""Exécute les SQL de la couche Gold et les contrôles qualité dans Snowflake.

Usage :
    python warehouse/run_sql.py gold      -> reconstruit les tables Gold
    python warehouse/run_sql.py quality   -> exécute les tests, échoue si un test bloquant échoue
"""
import logging
import sys
from pathlib import Path

from load_to_snowflake import get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

SQL_DIR = Path("snowflake")

# Ces contrôles avertissent mais ne bloquent pas le pipeline
WARNING_ONLY = {"rendements_extremes_sup_20pct"}


def run_file(conn, path: Path):
    if not path.exists():
        raise SystemExit(f"Fichier SQL introuvable : {path}")
    sql = path.read_text(encoding="utf-8")
    logger.info("Exécution de %s", path)
    return conn.execute_string(sql)


def build_gold(conn) -> None:
    run_file(conn, SQL_DIR / "gold_metrics.sql")
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM FIN_PLATFORM.ANALYTICS.FACT_DAILY_METRICS")
        logger.info("FACT_DAILY_METRICS : %d lignes", cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM FIN_PLATFORM.ANALYTICS.AGG_COMPANY_PERFORMANCE")
        logger.info("AGG_COMPANY_PERFORMANCE : %d lignes", cur.fetchone()[0])


def check_quality(conn) -> None:
    cursors = run_file(conn, SQL_DIR / "quality_checks.sql")
    rows = cursors[-1].fetchall()  # le dernier curseur contient le tableau de résultats
    if not rows:
        raise SystemExit("Aucun résultat de contrôle qualité")

    blocking = []
    for check_name, violations, status in rows:
        if status == "OK":
            logger.info("OK     | %s", check_name)
        elif check_name in WARNING_ONLY:
            logger.warning("AVERT. | %s (%s cas)", check_name, violations)
        else:
            logger.error("ECHEC  | %s (%s cas)", check_name, violations)
            blocking.append(check_name)

    if blocking:
        logger.error("Contrôles bloquants en échec : %s", blocking)
        sys.exit(1)
    logger.info("Tous les contrôles bloquants sont passés")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("gold", "quality"):
        raise SystemExit("Usage : python warehouse/run_sql.py [gold|quality]")

    conn = get_connection()
    try:
        if sys.argv[1] == "gold":
            build_gold(conn)
        else:
            check_quality(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()