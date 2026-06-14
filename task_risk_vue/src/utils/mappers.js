export const TASK_STATUS_LABEL = {
  pending: "待处理",
  in_progress: "进行中",
  blocked: "阻塞",
  awaiting_review: "待审核",
  completed: "已完成",
  cancelled: "已取消",
  overdue: "已逾期",
};

export const TASK_STATUS_CLASS = {
  pending: "processing",
  in_progress: "processing",
  blocked: "overdue",
  awaiting_review: "waiting",
  completed: "done",
  cancelled: "done",
  overdue: "overdue",
};

export const TASK_TYPE_LABEL = {
  customer_followup: "客户跟进",
  product_feedback: "产品反馈",
  complaint: "投诉处理",
  adverse_event: "不良事件",
  device_anomaly: "设备异常",
  compliance_review: "合规审核",
  knowledge_maintain: "知识维护",
  other: "其他",
};

export const TASK_PRIORITY_LABEL = {
  low: "普通",
  medium: "普通",
  high: "高",
  urgent: "紧急",
};

export const RISK_LEVEL_LABEL = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
  critical: "紧急风险",
};

export const REVIEW_STATUS_LABEL = {
  none: "无需审核",
  pending: "待审核",
  approved: "已通过",
  rejected: "已驳回",
  escalated: "已升级",
};

export const NOTIFICATION_KIND_LABEL = {
  task_created: "任务分配",
  task_reminder: "任务提醒",
  task_overdue: "任务逾期",
  risk_review_required: "风险审核",
  knowledge_gap_assigned: "知识补充",
  daily_summary: "日报",
  weekly_summary: "周报",
};

export const NOTIFICATION_STATUS_LABEL = {
  pending: "待发送",
  sent: "已发送",
  failed: "发送失败",
  dead: "死信",
};

export const TASK_EVENT_TYPE_LABEL = {
  create: "任务创建",
  assign: "负责人变更",
  update: "信息更新",
  comment: "评论",
  risk_review_request: "风险审核申请",
  risk_review_decide: "风险审核决策",
  reminder_sent: "提醒发送",
  complete: "任务完成",
  cancel: "任务取消",
  reopen: "任务重开",
  attachment: "附件上传",
};

export const TASK_TYPE_OPTIONS = Object.entries(TASK_TYPE_LABEL).map(([value, label]) => ({ value, label }));

export const PRIORITY_OPTIONS = [
  { value: "urgent", label: "紧急" },
  { value: "high", label: "高" },
  { value: "medium", label: "普通" },
  { value: "low", label: "低" },
];

export const TRACE_NODE_LABEL = {
  supervisor: "意图识别与路由",
  merge: "多轮信息合并",
  clarify: "追问补全",
  task_agent: "任务创建",
  risk_agent: "风险评估",
  rag_agent: "知识库检索",
  notify_agent: "通知调度",
  summary_agent: "报告生成",
  human_review: "人工审核",
  tool_call: "工具调用",
};

/** 后端枚举值 → 前端状态过滤选项（供 el-select 使用） */
export const STATUS_OPTIONS = Object.entries(TASK_STATUS_LABEL).map(([value, label]) => ({ value, label }));

/** 前端中文状态 → 后端枚举值（反向映射，用于过滤时 el-select 选项一致） */
export const RISK_OPTIONS = [
  { value: "critical", label: "紧急风险" },
  { value: "high", label: "高风险" },
  { value: "medium", label: "中风险" },
  { value: "low", label: "低风险" },
];

export function statusLabel(status) {
  return TASK_STATUS_LABEL[status] ?? status;
}

export function statusClass(status) {
  return TASK_STATUS_CLASS[status] ?? "processing";
}

export function typeLabel(type) {
  return TASK_TYPE_LABEL[type] ?? type;
}

export function priorityLabel(priority) {
  return TASK_PRIORITY_LABEL[priority] ?? priority;
}

export function riskLabel(level) {
  return RISK_LEVEL_LABEL[level] ?? level;
}

export function reviewStatusLabel(status) {
  return REVIEW_STATUS_LABEL[status] ?? status;
}

export function notificationKindLabel(kind) {
  return NOTIFICATION_KIND_LABEL[kind] ?? kind;
}

export function notificationStatusLabel(status) {
  return NOTIFICATION_STATUS_LABEL[status] ?? status;
}

export function traceNodeLabel(node) {
  return TRACE_NODE_LABEL[node] ?? node;
}

export function formatDateTime(datetime) {
  if (!datetime) return "-";
  const d = new Date(datetime);
  if (Number.isNaN(d.getTime())) return datetime;
  return `${d.getFullYear()}-${(d.getMonth() + 1).toString().padStart(2, "0")}-${d.getDate().toString().padStart(2, "0")} ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}

export function eventTypeLabel(type) {
  return TASK_EVENT_TYPE_LABEL[type] ?? type;
}

export function formatDue(datetime) {
  if (!datetime) return "待设置";
  const d = new Date(datetime);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const tomorrow = new Date(today.getTime() + 86400000);
  const yesterday = new Date(today.getTime() - 86400000);
  const taskDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  if (taskDay.getTime() === today.getTime()) {
    return `今天 ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
  }
  if (taskDay.getTime() === tomorrow.getTime()) {
    return `明天 ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
  }
  if (taskDay.getTime() === yesterday.getTime()) {
    return `昨天 ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
  }
  return `${(d.getMonth() + 1).toString().padStart(2, "0")}-${d.getDate().toString().padStart(2, "0")} ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}
