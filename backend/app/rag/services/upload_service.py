"""
UploadService - 知识库上传服务

职责：
- 接收上传文件
- 校验文件格式 / 大小
- 保存到 uploads/{file_id}/
- 调用 KnowledgePipeline 执行预处理
- 返回结构化结果

架构位置：
- rag/services/ 层
- 被 api/rag.py 调用

扩展规划：
- Phase 5.3: 支持多知识库（knowledge_base_id 参数）
- Phase 5.4: 支持异步处理（大文件后台任务）
"""

import os
import logging
from fastapi import UploadFile
from app.rag.schemas.document import UploadedFile, PipelineResult
from app.rag.pipelines import KnowledgePipeline
from app.rag.constants.config import UPLOAD_DIR, ALLOWED_EXTENSIONS, MAX_FILE_SIZE

logger = logging.getLogger(__name__)


class UploadService:
    """知识库上传服务"""

    def __init__(self):
        self.pipeline = KnowledgePipeline()

    async def process_upload(self, file: UploadFile) -> PipelineResult:
        """
        处理文件上传 + 预处理

        流程:
        1. 校验文件
        2. 保存文件
        3. 执行 Pipeline
        4. 返回结果

        Args:
            file: FastAPI UploadFile 对象

        Returns:
            PipelineResult: 预处理结果

        Raises:
            ValueError: 文件校验失败
        """
        # Step 1: 校验
        self._validate(file)

        # Step 2: 保存
        uploaded_file = await self._save(file)
        logger.info(
            f"[UPLOAD] 文件已保存: {uploaded_file.file_path} "
            f"(size={uploaded_file.file_size} bytes)"
        )

        # Step 3: Pipeline
        try:
            result = self.pipeline.run(uploaded_file)
        except Exception as e:
            logger.error(f"[UPLOAD] Pipeline 处理失败: {e}")
            raise ValueError(f"文档处理失败: {str(e)}")

        return result

    def _validate(self, file: UploadFile) -> None:
        """
        文件校验

        Raises:
            ValueError: 校验不通过
        """
        if not file.filename:
            raise ValueError("文件名不能为空")

        # 扩展名校验
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"不支持的文件格式: .{ext}，"
                f"支持: {', '.join(ALLOWED_EXTENSIONS)}"
            )

        # 大小校验 (通过 content_type 或 header 无法精确判断，保存后二次检查)
        if file.size and file.size > MAX_FILE_SIZE:
            raise ValueError(
                f"文件过大: {file.size / 1024 / 1024:.1f}MB，"
                f"最大: {MAX_FILE_SIZE / 1024 / 1024:.0f}MB"
            )

    async def _save(self, file: UploadFile) -> UploadedFile:
        """
        保存文件到 uploads/{file_id}/

        Returns:
            UploadedFile: 文件元信息
        """
        # 生成元信息
        ext = file.filename.rsplit(".", 1)[-1].lower()
        uploaded = UploadedFile(
            file_name=file.filename,
            file_type=ext,
            file_size=0,
            file_path="",
        )

        # 创建目录
        file_dir = os.path.join(UPLOAD_DIR, uploaded.file_id)
        os.makedirs(file_dir, exist_ok=True)

        # 保存文件
        file_path = os.path.join(file_dir, file.filename)
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        # 更新元信息
        uploaded.file_path = file_path
        uploaded.file_size = len(content)

        # 二次校验文件大小
        if uploaded.file_size == 0:
            raise ValueError("上传文件为空")
        if uploaded.file_size > MAX_FILE_SIZE:
            os.remove(file_path)
            raise ValueError(
                f"文件过大: {uploaded.file_size / 1024 / 1024:.1f}MB，"
                f"最大: {MAX_FILE_SIZE / 1024 / 1024:.0f}MB"
            )

        logger.info(f"[UPLOAD] 文件已保存: {file_path}")
        return uploaded


# 全局单例
upload_service = UploadService()
