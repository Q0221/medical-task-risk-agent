#!/bin/sh
set -e

echo "等待 MySQL 就绪 (${MYSQL_HOST}:${MYSQL_PORT}) ..."
python - <<'PY'
import os
import sys
import time

import pymysql

host = os.environ.get("MYSQL_HOST", "mysql")
port = int(os.environ.get("MYSQL_PORT", "3306"))
user = os.environ.get("MYSQL_USER", "root")
password = os.environ.get("MYSQL_PASSWORD", "")
database = os.environ.get("MYSQL_DB", "medical_agent")
max_attempts = int(os.environ.get("MYSQL_WAIT_ATTEMPTS", "60"))
interval_seconds = int(os.environ.get("MYSQL_WAIT_INTERVAL", "2"))

for attempt in range(1, max_attempts + 1):
    try:
        connection = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connect_timeout=5,
        )
        connection.close()
        print(f"MySQL 已就绪（第 {attempt} 次尝试）")
        sys.exit(0)
    except Exception as exc:
        print(f"MySQL 未就绪（{attempt}/{max_attempts}）：{exc}")
        time.sleep(interval_seconds)

print("等待 MySQL 超时，退出")
sys.exit(1)
PY

echo "执行数据库迁移 ..."
alembic upgrade head

if [ "${RUN_SEED_BULK:-false}" = "true" ]; then
    echo "灌入演示数据 (seed_bulk) ..."
    python -m scripts.seed_bulk
fi

echo "启动 FastAPI 服务 ..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
