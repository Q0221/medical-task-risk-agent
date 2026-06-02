"""模型集中导出。

任何新增 ORM 都要在此处 import，
以便 Base.metadata 包含所有表，供 Alembic autogenerate 扫描。
"""

from app.models.agent_trace import AgentTrace
from app.models.base import Base, BaseModel, SoftDeleteMixin, TimestampMixin
from app.models.hospital import Hospital
from app.models.knowledge_gap import KnowledgeGapTask
from app.models.notification import Notification
from app.models.product import Product
from app.models.risk_record import RiskRecord
from app.models.task import Task
from app.models.task_event import TaskEvent
from app.models.user import Role, User, UserRole

__all__ = [
    "Base",
    "BaseModel",
    "TimestampMixin",
    "SoftDeleteMixin",
    "Role",
    "User",
    "UserRole",
    "Hospital",
    "Product",
    "Task",
    "TaskEvent",
    "RiskRecord",
    "KnowledgeGapTask",
    "Notification",
    "AgentTrace",
]
