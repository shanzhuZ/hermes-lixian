# -*- coding: utf-8 -*-
"""MySQL 连接（XW_MYSQL_*；缺省时尝试从 HERMES_HOME/.env 读取）。"""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

logger = logging.getLogger(__name__)

_ENV_LOADED = False


class DbError(RuntimeError):
    pass


def _load_dotenv_once() -> None:
    """Hermes 通常已注入环境变量；本地/缺省时补读 .env（不覆盖已有非空键）。"""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    candidates = []
    home = (os.environ.get("HERMES_HOME") or "").strip()
    if home:
        candidates.append(Path(home) / ".env")
    here = Path(__file__).resolve()
    # plugins/xw-ingest -> repo root
    candidates.append(here.parents[2] / ".env")
    candidates.append(here.parents[2] / "var" / "hermes" / ".env")
    for p in candidates:
        try:
            if not p.is_file():
                continue
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, _, v = s.partition("=")
                k = k.strip()
                if not k.startswith("XW_MYSQL_") and k != "XW_PERSIST_ENABLED":
                    continue
                if k in os.environ and str(os.environ.get(k) or "").strip():
                    continue
                v = v.strip().strip('"').strip("'")
                os.environ[k] = v
            return
        except Exception:
            continue


def _cfg() -> Dict[str, Any]:
    _load_dotenv_once()
    return {
        "host": (os.environ.get("XW_MYSQL_HOST") or "127.0.0.1").strip(),
        "port": int((os.environ.get("XW_MYSQL_PORT") or "3306").strip() or "3306"),
        "user": (os.environ.get("XW_MYSQL_USER") or "root").strip(),
        "password": os.environ.get("XW_MYSQL_PASSWORD") or "",
        "database": (os.environ.get("XW_MYSQL_DB") or "hermes-xw1").strip(),
        "charset": "utf8mb4",
    }


def enabled() -> bool:
    _load_dotenv_once()
    flag = (os.environ.get("XW_PERSIST_ENABLED") or "1").strip()
    if flag in ("0", "false", "False", "no"):
        return False
    return bool(_cfg()["database"])


def _connect():
    if not enabled():
        raise DbError("XW_PERSIST_ENABLED=0 或未配置库，跳过入库")
    try:
        import pymysql
    except ImportError as exc:
        raise DbError("未安装 pymysql，请: pip install pymysql") from exc
    cfg = _cfg()
    return pymysql.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        charset=cfg["charset"],
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


@contextmanager
def transaction() -> Generator[Any, None, None]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute(sql: str, params: Optional[Tuple | Dict] = None) -> int:
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return int(cur.rowcount)


def fetch_one(sql: str, params: Optional[Tuple | Dict] = None) -> Optional[Dict[str, Any]]:
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            row = cur.fetchone()
            return dict(row) if row else None


def fetch_all(sql: str, params: Optional[Tuple | Dict] = None) -> List[Dict[str, Any]]:
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return [dict(r) for r in cur.fetchall()]


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
