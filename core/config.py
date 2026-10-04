import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

API_ROOT = Path(os.environ.get("API_FACTORY_ROOT", "/home/datalake/NewFolder/programs/rest/API"))
SERVICES_DIR = API_ROOT / "generated_services"
LOGS_DIR = API_ROOT / "logs"

STATUS_FILE = BASE_DIR / "services_status.json"
DB_CONFIGS_FILE = BASE_DIR / "db_configs.json"
KEYS_FILE = BASE_DIR / "api_keys.json"
ANALYTICS_DB = BASE_DIR / "analytics.db"
BI_DASHBOARDS_FILE = BASE_DIR / "bi_dashboards.json"
USERS_FILE = BASE_DIR / "users.json"


def resolve_pm2_interpreter() -> str:
    """مسیر پایتونی که واقعاً روی سیستم وجود دارد."""
    import shutil
    import sys

    candidates = []
    env = os.environ.get("API_FACTORY_PM2_INTERPRETER", "").strip()
    if env:
        candidates.append(env)

    # پایتون همین پروسه‌ای که پنل را اجرا کرده (معمولاً همان venv)
    if sys.executable:
        candidates.append(sys.executable)

    # which
    for cmd in ("python3", "python"):
        w = shutil.which(cmd)
        if w:
            candidates.append(w)

    # مسیرهای رایج پروژه / سرور
    candidates.extend(
        [
            "/media/mahdi/Data/data-lake/venv/bin/python",
            "/media/mahdi/Data/data-lake/venv/bin/python3",
            "/home/datalake/dagster_venv/bin/python3",
            "/home/datalake/dagster_venv/python3",
            "/home/datalake/dagster_venv/bin/python",
            str(Path.home() / "dagster_venv/bin/python3"),
            "/usr/bin/python3",
            "/usr/local/bin/python3",
        ]
    )

    seen = set()
    for c in candidates:
        if not c or c in seen:
            continue
        seen.add(c)
        if Path(c).exists():
            return c
    return env or sys.executable or "python3"


PM2_INTERPRETER = resolve_pm2_interpreter()

PORT_CHANGE_PASSWORD = os.environ.get("API_FACTORY_PORT_PASSWORD", "admin")
LOGIN_USER = os.environ.get("API_FACTORY_USER", "admin")
LOGIN_PASS = os.environ.get("API_FACTORY_PASS", "admin")
SERVER_IP = os.environ.get("API_FACTORY_SERVER_IP", "127.0.0.1")
SECRET_KEY = os.environ.get("API_FACTORY_SECRET", "api-factory-pro-secret-change-me")

try:
    SERVICES_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    SERVICES_DIR = BASE_DIR / "generated_services"
    LOGS_DIR = BASE_DIR / "logs"
    SERVICES_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)
