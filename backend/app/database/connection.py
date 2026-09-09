"""MySQL connection helpers for repository-only data access."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterator

import pymysql
from pymysql.cursors import DictCursor

from app.core.config import get_settings


class DatabaseAccessError(RuntimeError):
    """Raised when the configured business database cannot be reached."""


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=to_json_value)


def json_loads(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def to_json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def normalize_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: to_json_value(value) for key, value in row.items()}


def normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_row(row) or {} for row in rows]


@contextmanager
def mysql_connection() -> Iterator[pymysql.connections.Connection]:
    settings = get_settings()
    try:
        connection = pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            charset=settings.mysql_charset,
            cursorclass=DictCursor,
            autocommit=False,
        )
    except pymysql.MySQLError as exc:
        raise DatabaseAccessError(
            f"Unable to connect to MySQL database '{settings.mysql_database}' "
            f"at {settings.mysql_host}:{settings.mysql_port}: {exc}"
        ) from exc

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


class MySQLRepository:
    """Small base repository with parameterized query helpers."""

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with mysql_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return normalize_row(cursor.fetchone())

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with mysql_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return normalize_rows(cursor.fetchall())

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with mysql_connection() as connection:
            with connection.cursor() as cursor:
                affected = cursor.execute(sql, params)
                return affected

    def transaction(self):
        """多语句写操作共用的单一事务。

        fetch_one/fetch_all/execute 每次调用都独立开连接并各自提交，跨语句的
        写入（如下单要连插 orders/order_items/物流表）中途失败会留下脏数据。
        需要原子性的写路径改为：
            with self.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql1, params1)
                    cur.execute(sql2, params2)
        退出 with 时统一 commit，任一语句抛异常则整体 rollback。
        """
        return mysql_connection()
