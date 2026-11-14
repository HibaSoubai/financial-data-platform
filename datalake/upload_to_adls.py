"""Envoi des couches Bronze et Silver vers un Data Lake (local ou Azure ADLS Gen2)."""
import logging
import os
import shutil
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

load_dotenv()

RAW_DIR = Path("data/raw")
SILVER_FILE = Path("data/processed/stock_prices_silver.parquet")
LOCAL_LAKE = Path("lake")


def build_plan() -> list[tuple[str, str, Path]]:
    """Liste (container, chemin distant, fichier local) des fichiers à envoyer."""
    plan = []
    ingestion = date.today().isoformat()
    for path in sorted(RAW_DIR.glob("*_prices.csv")):
        remote = f"yahoo_finance/ingestion_date={ingestion}/{path.name}"
        plan.append(("bronze", remote, path))
    if SILVER_FILE.exists():
        plan.append(("silver", f"stock_prices/{SILVER_FILE.name}", SILVER_FILE))
    return plan


def upload_local(plan) -> None:
    for container, remote, local in plan:
        target = LOCAL_LAKE / container / remote
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local, target)
        logger.info("Copié : %s -> %s", local, target)


def get_azure_client():
    from azure.storage.filedatalake import DataLakeServiceClient

    account = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
    key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
    if not account or not key:
        raise SystemExit("AZURE_STORAGE_ACCOUNT_NAME / AZURE_STORAGE_ACCOUNT_KEY manquants dans .env")
    return DataLakeServiceClient(
        account_url=f"https://{account}.dfs.core.windows.net",
        credential=key,
    )


def upload_azure(plan) -> None:
    service = get_azure_client()
    for container, remote, local in plan:
        fs = service.get_file_system_client(container)
        file_client = fs.get_file_client(remote)
        with open(local, "rb") as f:
            file_client.upload_data(f, overwrite=True)
        logger.info("Envoyé : %s -> %s/%s", local, container, remote)


def list_lake() -> None:
    """Affiche le contenu du lac pour vérifier l'envoi."""
    mode = os.getenv("LAKE_MODE", "local").lower()
    if mode == "azure":
        service = get_azure_client()
        for container in ("bronze", "silver", "gold"):
            fs = service.get_file_system_client(container)
            for item in fs.get_paths():
                if not item.is_directory:
                    logger.info("%s/%s (%d octets)", container, item.name, item.content_length)
    else:
        for path in sorted(LOCAL_LAKE.rglob("*")):
            if path.is_file():
                logger.info("%s (%d octets)", path, path.stat().st_size)


def main() -> None:
    mode = os.getenv("LAKE_MODE", "local").lower()
    plan = build_plan()
    if not plan:
        raise SystemExit("Rien à envoyer : lance d'abord l'ingestion et le nettoyage")
    logger.info("Mode : %s | %d fichiers à envoyer", mode, len(plan))
    if mode == "azure":
        upload_azure(plan)
    elif mode == "local":
        upload_local(plan)
    else:
        raise SystemExit(f"LAKE_MODE inconnu : {mode} (attendu : local ou azure)")
    list_lake()


if __name__ == "__main__":
    main()