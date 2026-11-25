import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / '.env'
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip())

DB_PARAMS = {
    'host': os.getenv('POTOLOK_DB_HOST', 'localhost'),
    'port': int(os.getenv('POTOLOK_DB_PORT', '5432')),
    'user': os.getenv('POTOLOK_DB_USER', 'postgres'),
    'password': os.getenv('POTOLOK_DB_PASSWORD', ''),
}
DB_NAME = os.getenv('POTOLOK_DB_NAME', 'potolok_db')
