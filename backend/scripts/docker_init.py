"""Docker 容器启动前置初始化（幂等）。

作为后端容器 CMD 的第一步执行：
1. 等待 MySQL 可连接（compose 中 depends_on healthy 之外的兜底，最长 60s）；
2. 检查向量索引（qdrant 本地模式）：为空则调用 rebuild_rag_index.run(force=True)
   全量重建（复用 knowledge_base/knowledge/ 与当前 EMBEDDING_PROVIDER 配置）；
3. 打印初始化摘要。

幂等性：MySQL 建库建表由 mysql 镜像首启时的 /docker-entrypoint-initdb.d/ 完成
（数据卷非空则自动跳过）；向量索引非空则跳过重建。重复 up 不会重复导数据。
"""

import logging
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # /app
sys.path.insert(0, BASE_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("docker_init")


def wait_for_mysql(timeout_s: float = 60.0, interval_s: float = 2.0) -> None:
    """阻塞等待 MySQL 可建立连接并执行 SELECT 1。"""
    import pymysql

    from app.core.config import get_settings

    settings = get_settings()
    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            conn = pymysql.connect(
                host=settings.mysql_host,
                port=settings.mysql_port,
                user=settings.mysql_user,
                password=settings.mysql_password,
                database=settings.mysql_database,
                connect_timeout=3,
            )
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
            conn.close()
            logger.info(
                "MySQL 连接成功 (host=%s, db=%s)", settings.mysql_host, settings.mysql_database
            )
            return
        except Exception as exc:  # noqa: BLE001 - 重试循环需捕获一切连接错误
            last_error = exc
            logger.info("等待 MySQL 就绪 ... (%s)", exc)
            time.sleep(interval_s)
    raise SystemExit(f"MySQL 等待超时（{timeout_s:.0f}s）：{last_error}")


def ensure_rag_index() -> None:
    """向量索引为空时全量重建（非空跳过，保证幂等）。"""
    from app.rag.vectorstore import chroma_store

    count = chroma_store.count()
    if count > 0:
        logger.info("向量索引已存在（%d chunks），跳过重建", count)
        return

    logger.info("向量索引为空，开始全量重建（knowledge_base/knowledge/ → 父子块 → qdrant）...")
    from rebuild_rag_index import run as rebuild_run

    rebuild_run(force=True)
    # 注意：rebuild 完成后其内部已关闭 qdrant client（同进程内 chroma_store 不可再用），
    # 此处不再 count；块数量汇总见 rebuild 自身输出的"完成！"行。
    logger.info("向量索引重建流程完成")


def main() -> None:
    started = time.perf_counter()
    wait_for_mysql()
    ensure_rag_index()
    logger.info("初始化完成，耗时 %.1fs，启动 uvicorn ...", time.perf_counter() - started)


if __name__ == "__main__":
    main()
