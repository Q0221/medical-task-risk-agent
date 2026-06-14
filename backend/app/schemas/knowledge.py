"""知识库管理模块 Pydantic 模型。

涵盖 SOP 文档（列表/详情/创建/更新/版本）与知识空缺任务（列表/详情/处理/审核/归档）。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# SOP 文档
# ---------------------------------------------------------------------------

class SopCreateRequest(BaseModel):
    """创建 SOP 文档请求体。"""

    code: str = Field(..., max_length=32, description="SOP 编号，如 SOP-ADV-001")
    title: str = Field(..., max_length=255)
    category: Optional[str] = Field(default=None, max_length=64)
    department: Optional[str] = Field(default=None, max_length=64)
    version: str = Field(default="v1.0", max_length=16)
    tags: List[str] = Field(default_factory=list)
    content: Optional[str] = Field(default=None, description="文档全文内容")
    status: Literal["active", "draft"] = Field(default="active")


class SopUpdateRequest(BaseModel):
    """更新 SOP 文档（部分字段）。"""

    title: Optional[str] = Field(default=None, max_length=255)
    category: Optional[str] = Field(default=None, max_length=64)
    department: Optional[str] = Field(default=None, max_length=64)
    tags: Optional[List[str]] = None
    content: Optional[str] = None
    status: Optional[Literal["active", "draft", "archived"]] = None


class SopNewVersionRequest(BaseModel):
    """基于现有 SOP 创建新版本。"""

    version: str = Field(..., max_length=16, description="新版本号，如 v2.0")
    content: Optional[str] = None
    change_summary: Optional[str] = Field(default=None, max_length=500, description="变更说明")


class SopListItem(BaseModel):
    """SOP 列表行。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    title: str
    category: Optional[str]
    department: Optional[str]
    version: str
    tags: Optional[list]
    status: str
    hit_count: int
    updated_at: datetime


class SopDetail(SopListItem):
    """SOP 详情（追加全文内容和版本历史摘要）。"""

    content: Optional[str]
    parent_id: Optional[int]
    created_by: Optional[int]
    created_at: datetime


class SopListResponse(BaseModel):
    items: List[SopListItem]
    total: int
    page: int
    page_size: int


class KnowledgeStats(BaseModel):
    """知识库总览统计。"""

    sop_total: int
    sop_active: int
    sop_draft: int
    gap_open: int
    gap_in_progress: int
    gap_resolved: int
    recent_30d_hits: int


# ---------------------------------------------------------------------------
# 知识空缺任务
# ---------------------------------------------------------------------------

class GapListItem(BaseModel):
    """知识空缺列表行。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    original_question: str
    confidence: Optional[float]
    status: str
    assignee_id: int
    assignee_name: Optional[str] = None
    source_task_id: Optional[int]
    trace_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class GapDetail(GapListItem):
    """知识空缺详情。"""

    retrieval_query: Optional[str]
    rag_hits_snapshot: Optional[list]
    resolution_note: Optional[str]


class GapListResponse(BaseModel):
    items: List[GapListItem]
    total: int
    page: int
    page_size: int


class GapProcessRequest(BaseModel):
    """PATCH /knowledge/gaps/{id}/process 请求体（知识补充人提交处理结果）。"""

    resolution_note: str = Field(..., min_length=1, max_length=2000, description="补充说明或关联 SOP 链接")
    action: Literal["save_draft", "submit_review"] = Field(
        default="submit_review",
        description="save_draft=保存草稿(in_progress), submit_review=提交审核(resolved)",
    )


class GapReviewRequest(BaseModel):
    """PATCH /knowledge/gaps/{id}/review 请求体（主管审核）。"""

    action: Literal["approve", "reject"] = Field(..., description="approve=归档关闭, reject=退回重做")
    comment: Optional[str] = Field(default=None, max_length=1000)


class GapActionResult(BaseModel):
    """Gap 操作结果响应。"""

    gap_id: int
    status: str
    message: str
