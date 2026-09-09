"""
Workflow Repository - Stage 5 持久化唯一入口

职责：
- Workflow / Checkpoint / Interrupt / Resume / Handoff / Recovery / Trace 持久化
- 提供 Save / Load / Update / Delete / Query 抽象
- 以 Repository Pattern 隔离存储实现，未来可从 JSON 平滑迁移到 SQLite/PostgreSQL

当前实现：
- JSON 文件存储
- 每类记录一个目录：backend/workflow_repository/{record_type}/
- 文件名：{record_id}.json
"""

from __future__ import annotations

import json
import os
import time
import logging
import copy
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from app.workflow.models import WorkflowPersistenceRecord

logger = logging.getLogger(__name__)

_REPO_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "workflow_repository",
)


def _ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _json_safe(value: Any) -> Any:
    """递归转换为 JSON 可序列化对象"""
    if is_dataclass(value):
        if hasattr(value, "to_dict"):
            return _json_safe(value.to_dict())
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "value"):
        return value.value
    return str(value)


class WorkflowRepository:
    """Workflow 持久化 Repository"""

    def __init__(self, root_dir: str = _REPO_DIR):
        self.root_dir = root_dir
        _ensure_dir(self.root_dir)
        self._active_root_dir = self.root_dir
        self._record_cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._workflow_index_cache: dict[str, list[tuple[str, str]]] = {}
        self._build_workflow_index()

    def save(
        self,
        record_type: str,
        record_id: str,
        workflow_id: str,
        payload: Any,
        metadata: dict[str, Any] | None = None,
        preserve_created_at: bool = True,
    ) -> WorkflowPersistenceRecord:
        """保存记录"""
        self._ensure_active_root()
        now = datetime.now()
        existing = self.load(record_type, record_id) if preserve_created_at else None
        created_at = (
            datetime.fromisoformat(existing["created_at"])
            if existing and existing.get("created_at")
            else now
        )
        record = WorkflowPersistenceRecord(
            record_id=record_id,
            record_type=record_type,
            workflow_id=workflow_id,
            payload=_json_safe(payload),
            created_at=created_at,
            updated_at=now,
            metadata=metadata or {},
        )
        record_dict = record.to_dict()
        self._write_dict(record.record_type, record.record_id, record_dict)
        self._cache_record(record_dict)
        self._index_record(record.record_type, record.record_id, record.workflow_id)
        logger.info(
            f"[WorkflowRepository] save type={record_type} id={record_id} workflow={workflow_id}"
        )
        return record

    def load(self, record_type: str, record_id: str) -> dict[str, Any] | None:
        """加载记录"""
        self._ensure_active_root()
        path = self._path(record_type, record_id)
        cached = self._record_cache.get((record_type, record_id))
        if cached:
            return copy.deepcopy(cached)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            record = json.load(f)
        self._cache_record(record)
        return copy.deepcopy(record)

    def update(
        self,
        record_type: str,
        record_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """更新记录 payload/metadata 顶层字段"""
        self._ensure_active_root()
        record = self.load(record_type, record_id)
        if record is None:
            return None
        for key, value in updates.items():
            if key == "payload" and isinstance(value, dict):
                payload = dict(record.get("payload", {}))
                payload.update(_json_safe(value))
                record["payload"] = payload
            elif key == "metadata" and isinstance(value, dict):
                meta = dict(record.get("metadata", {}))
                meta.update(_json_safe(value))
                record["metadata"] = meta
            else:
                record[key] = _json_safe(value)
        record["updated_at"] = datetime.now().isoformat()
        self._write_dict(record_type, record_id, record)
        self._cache_record(record)
        logger.info(f"[WorkflowRepository] update type={record_type} id={record_id}")
        return record

    def delete(self, record_type: str, record_id: str) -> bool:
        """删除记录"""
        self._ensure_active_root()
        path = self._path(record_type, record_id)
        if not os.path.exists(path):
            return False
        record = self.load(record_type, record_id)
        os.remove(path)
        self._record_cache.pop((record_type, record_id), None)
        if record:
            self._deindex_record(record_type, record_id, record.get("workflow_id", ""))
        logger.info(f"[WorkflowRepository] delete type={record_type} id={record_id}")
        return True

    def query(
        self,
        record_type: str | None = None,
        workflow_id: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """查询记录，按更新时间倒序"""
        self._ensure_active_root()
        types = [record_type] if record_type else self._list_record_types()
        results: list[dict[str, Any]] = []
        indexed_refs = self._indexed_refs(workflow_id, types) if workflow_id else None
        if indexed_refs is not None:
            for typ, record_id in indexed_refs:
                record = self._record_cache.get((typ, record_id))
                if record:
                    record = copy.deepcopy(record)
                else:
                    record = self.load(typ, record_id)
                if not record:
                    continue
                if workflow_id and record.get("workflow_id") != workflow_id:
                    continue
                if filters and not self._matches(record, filters):
                    continue
                results.append(record)
            results.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
            return results[:limit] if limit else results
        for typ in types:
            typ_dir = self._type_dir(typ)
            if not os.path.isdir(typ_dir):
                continue
            for fname in os.listdir(typ_dir):
                if not fname.endswith(".json"):
                    continue
                with open(os.path.join(typ_dir, fname), "r", encoding="utf-8") as f:
                    record = json.load(f)
                if workflow_id and record.get("workflow_id") != workflow_id:
                    continue
                if filters and not self._matches(record, filters):
                    continue
                results.append(record)

        results.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
        return results[:limit] if limit else results

    def latest(
        self,
        record_type: str,
        workflow_id: str,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """查询某 workflow 最近一条记录"""
        records = self.query(record_type=record_type, workflow_id=workflow_id, filters=filters, limit=1)
        return records[0] if records else None

    def _matches(self, record: dict[str, Any], filters: dict[str, Any]) -> bool:
        payload = record.get("payload", {})
        metadata = record.get("metadata", {})
        for key, expected in filters.items():
            actual = record.get(key)
            if actual is None:
                actual = payload.get(key)
            if actual is None:
                actual = metadata.get(key)
            if actual != expected:
                return False
        return True

    def _ensure_active_root(self) -> None:
        if self._active_root_dir == self.root_dir:
            return
        _ensure_dir(self.root_dir)
        self._active_root_dir = self.root_dir
        self._record_cache.clear()
        self._build_workflow_index()

    def _list_record_types(self) -> list[str]:
        if not os.path.isdir(self.root_dir):
            return []
        return [
            name for name in os.listdir(self.root_dir)
            if os.path.isdir(os.path.join(self.root_dir, name)) and not name.startswith("_")
        ]

    def _type_dir(self, record_type: str) -> str:
        return _ensure_dir(os.path.join(self.root_dir, record_type))

    def _path(self, record_type: str, record_id: str) -> str:
        return os.path.join(self._type_dir(record_type), f"{record_id}.json")

    def _write(self, record: WorkflowPersistenceRecord) -> None:
        self._write_dict(record.record_type, record.record_id, record.to_dict())

    def _cache_record(self, record: dict[str, Any]) -> None:
        record_type = record.get("record_type")
        record_id = record.get("record_id")
        if record_type and record_id:
            self._record_cache[(record_type, record_id)] = copy.deepcopy(record)

    def _write_dict(self, record_type: str, record_id: str, record: dict[str, Any]) -> None:
        tmp = self._path(record_type, f"{record_id}.{int(time.time() * 1000)}.{uuid.uuid4().hex[:8]}.tmp")
        final = self._path(record_type, record_id)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_json_safe(record), f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, final)

    def _indexed_refs(
        self,
        workflow_id: str | None,
        record_types: list[str],
    ) -> list[tuple[str, str]] | None:
        if not workflow_id:
            return None
        refs = self._load_workflow_index(workflow_id)
        if refs is None:
            return None
        allowed = set(record_types)
        return [(typ, record_id) for typ, record_id in refs if typ in allowed]

    def _index_record(self, record_type: str, record_id: str, workflow_id: str) -> None:
        if not workflow_id:
            return
        refs = self._workflow_index_cache.setdefault(workflow_id, [])
        ref = (record_type, record_id)
        if ref in refs:
            return
        refs.append(ref)
        self._write_workflow_index(workflow_id, refs)

    def _deindex_record(self, record_type: str, record_id: str, workflow_id: str) -> None:
        if not workflow_id:
            return
        refs = self._load_workflow_index(workflow_id)
        if refs is None:
            return
        refs = [ref for ref in refs if ref != (record_type, record_id)]
        self._workflow_index_cache[workflow_id] = refs
        self._write_workflow_index(workflow_id, refs)

    def _load_workflow_index(self, workflow_id: str) -> list[tuple[str, str]] | None:
        if workflow_id in self._workflow_index_cache:
            return self._workflow_index_cache[workflow_id]
        return None

    def _build_workflow_index(self) -> None:
        self._workflow_index_cache.clear()
        for record_type in self._list_record_types():
            typ_dir = self._type_dir(record_type)
            if not os.path.isdir(typ_dir):
                continue
            for fname in os.listdir(typ_dir):
                if not fname.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(typ_dir, fname), "r", encoding="utf-8") as f:
                        record = json.load(f)
                except (OSError, json.JSONDecodeError):
                    continue
                workflow_id = record.get("workflow_id")
                record_id = record.get("record_id")
                if workflow_id and record_id:
                    self._cache_record(record)
                    refs = self._workflow_index_cache.setdefault(workflow_id, [])
                    ref = (record_type, record_id)
                    if ref not in refs:
                        refs.append(ref)

    def _write_workflow_index(
        self,
        workflow_id: str,
        refs: list[tuple[str, str]],
    ) -> None:
        # The durable source of truth is still the record JSON files. The workflow
        # index is rebuilt on Repository startup and kept in memory during writes.
        return


workflow_repository = WorkflowRepository()
