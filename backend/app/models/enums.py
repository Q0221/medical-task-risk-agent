"""统一枚举定义。

所有枚举均以字符串形式持久化到 VARCHAR(32) 字段，避免 MySQL ENUM 难以迁移的问题。
"""

from enum import StrEnum


class TaskType(StrEnum):
    """任务类型（覆盖你描述里的核心业务场景）。"""

    CUSTOMER_FOLLOWUP = "customer_followup"      # 客户跟进
    PRODUCT_FEEDBACK = "product_feedback"        # 产品反馈
    COMPLAINT = "complaint"                      # 投诉处理
    ADVERSE_EVENT = "adverse_event"              # 不良事件跟进
    DEVICE_ANOMALY = "device_anomaly"            # 设备异常
    COMPLIANCE_REVIEW = "compliance_review"      # 合规审核
    KNOWLEDGE_MAINTAIN = "knowledge_maintain"    # 知识库维护
    OTHER = "other"


class TaskStatus(StrEnum):
    """任务生命周期状态。"""

    PENDING = "pending"            # 已创建，等待开始
    IN_PROGRESS = "in_progress"    # 进行中
    BLOCKED = "blocked"            # 阻塞
    AWAITING_REVIEW = "awaiting_review"  # 等待人工审核（高风险）
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    OVERDUE = "overdue"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class RiskLevel(StrEnum):
    """风险分级（Risk Agent 输出）。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewStatus(StrEnum):
    """Human-in-the-loop 审核结果。"""

    NONE = "none"            # 无需审核
    PENDING = "pending"      # 待审核
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"  # 升级处理


class BusinessObjectType(StrEnum):
    """任务关联的业务对象类型。"""

    HOSPITAL = "hospital"
    PRODUCT = "product"
    ORDER = "order"
    CONTRACT = "contract"
    DEVICE = "device"
    PATIENT_CASE = "patient_case"
    NONE = "none"


class TaskEventType(StrEnum):
    """任务流转事件类型（task_events 表）。"""

    CREATE = "create"
    ASSIGN = "assign"
    UPDATE = "update"
    COMMENT = "comment"
    RISK_REVIEW_REQUEST = "risk_review_request"
    RISK_REVIEW_DECIDE = "risk_review_decide"
    REMINDER_SENT = "reminder_sent"
    COMPLETE = "complete"
    CANCEL = "cancel"
    REOPEN = "reopen"
    ATTACHMENT = "attachment"


class NotificationChannel(StrEnum):
    WXWORK = "wxwork"   # 企业微信
    EMAIL = "email"
    IM = "im"           # 站内消息
    SMS = "sms"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    DEAD = "dead"       # 死信


class NotificationKind(StrEnum):
    """通知业务场景。"""

    TASK_CREATED = "task_created"
    TASK_REMINDER = "task_reminder"
    TASK_OVERDUE = "task_overdue"
    RISK_REVIEW_REQUIRED = "risk_review_required"
    KNOWLEDGE_GAP_ASSIGNED = "knowledge_gap_assigned"
    DAILY_SUMMARY = "daily_summary"
    WEEKLY_SUMMARY = "weekly_summary"


class AgentNode(StrEnum):
    """LangGraph 节点名（agent_traces 用）。"""

    SUPERVISOR = "supervisor"
    TASK_AGENT = "task_agent"
    RISK_AGENT = "risk_agent"
    RAG_AGENT = "rag_agent"
    NOTIFY_AGENT = "notify_agent"
    SUMMARY_AGENT = "summary_agent"
    HUMAN_REVIEW = "human_review"
    TOOL_CALL = "tool_call"


class AgentTraceStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    RETRY = "retry"
    INTERRUPTED = "interrupted"


class KnowledgeGapStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class RoleCode(StrEnum):
    """内置角色码（与 roles 表 code 字段一致）。"""

    CUSTOMER_SERVICE = "customer_service"    # 客服
    MEDICAL_SUPPORT = "medical_support"      # 医学支持
    PRODUCT_OPS = "product_ops"              # 产品运营
    QA = "qa"                                # 质控
    COMPLIANCE = "compliance"                # 合规
    MANAGER = "manager"                      # 主管
    ADMIN = "admin"                          # 系统管理员
