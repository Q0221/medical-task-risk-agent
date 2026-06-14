<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  ArrowLeft, ArrowRight, Calendar, Check, Close, Filter,
  Grid, List, Plus, Search, View,
} from "@element-plus/icons-vue";
import PageHeader from "../components/PageHeader.vue";
import RiskBadge from "../components/RiskBadge.vue";
import {
  addTaskAttachment, addTaskComment, assignTask, batchAssignTasks,
  batchCancelTasks, batchCompleteTasks, cancelTask, cancelTaskReminder,
  completeTask, getTaskById, getTaskTimeline, getTasks, setTaskReminder,
  updateTaskCollaborators,
} from "../api/tasks.js";
import { chatWithAgent } from "../api/agent.js";
import { currentUserId } from "../store/app.js";
import {
  eventTypeLabel, formatDateTime, formatDue, PRIORITY_OPTIONS,
  reviewStatusLabel, RISK_OPTIONS, STATUS_OPTIONS, statusClass,
  statusLabel, TASK_TYPE_OPTIONS, typeLabel, priorityLabel,
} from "../utils/mappers.js";

const route = useRoute();

// ── 列表状态 ──────────────────────────────────────────────────────────────
const tasks = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const loading = ref(false);

// ── 普通筛选 ──────────────────────────────────────────────────────────────
const search = ref("");
const statusFilter = ref("");
const riskFilter = ref("");

// ── 高级筛选（面板折叠） ───────────────────────────────────────────────────
const filterExpanded = ref(false);
const typeFilter = ref("");
const priorityFilter = ref("");
const dueRange = ref(null); // [Date, Date] | null

// ── 视图模式 ──────────────────────────────────────────────────────────────
const view = ref("list"); // list | board | calendar

// ── 多选/批量 ─────────────────────────────────────────────────────────────
const selectedIds = ref(new Set());
const batchLoading = ref(false);
const batchAssignName = ref("");

const selectedCount = computed(() => selectedIds.value.size);
const allSelected = computed(() =>
  filteredTasks.value.length > 0 &&
  filteredTasks.value.every((t) => selectedIds.value.has(t.id))
);
const indeterminate = computed(() =>
  selectedCount.value > 0 && !allSelected.value
);

function toggleSelect(taskId) {
  const next = new Set(selectedIds.value);
  if (next.has(taskId)) next.delete(taskId);
  else next.add(taskId);
  selectedIds.value = next;
}

function toggleAll() {
  if (allSelected.value) {
    selectedIds.value = new Set();
  } else {
    selectedIds.value = new Set(filteredTasks.value.map((t) => t.id));
  }
}

function clearSelection() {
  selectedIds.value = new Set();
}

// ── 日历视图 ──────────────────────────────────────────────────────────────
const calendarDate = ref(new Date()); // 当前显示的月份
const calendarTasks = ref([]);
const calendarLoading = ref(false);

const calendarYear = computed(() => calendarDate.value.getFullYear());
const calendarMonth = computed(() => calendarDate.value.getMonth() + 1);

const calendarDays = computed(() => {
  const year = calendarDate.value.getFullYear();
  const month = calendarDate.value.getMonth();
  const firstDay = new Date(year, month, 1).getDay(); // 0=Sun
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const daysInPrevMonth = new Date(year, month, 0).getDate();

  const cells = [];
  // 上月补位
  for (let d = firstDay - 1; d >= 0; d--) {
    cells.push({ date: new Date(year, month - 1, daysInPrevMonth - d), inMonth: false });
  }
  // 本月
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({ date: new Date(year, month, d), inMonth: true });
  }
  // 补满 6 行
  const remaining = 42 - cells.length;
  for (let d = 1; d <= remaining; d++) {
    cells.push({ date: new Date(year, month + 1, d), inMonth: false });
  }
  return cells;
});

function getCalendarDayTasks(date) {
  return calendarTasks.value.filter((t) => {
    if (!t.due_at) return false;
    const d = new Date(t.due_at);
    return d.getFullYear() === date.getFullYear() &&
      d.getMonth() === date.getMonth() &&
      d.getDate() === date.getDate();
  });
}

function isToday(date) {
  const now = new Date();
  return date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();
}

async function prevMonth() {
  const d = calendarDate.value;
  calendarDate.value = new Date(d.getFullYear(), d.getMonth() - 1, 1);
  await loadCalendarTasks();
}

async function nextMonth() {
  const d = calendarDate.value;
  calendarDate.value = new Date(d.getFullYear(), d.getMonth() + 1, 1);
  await loadCalendarTasks();
}

async function loadCalendarTasks() {
  calendarLoading.value = true;
  try {
    const year = calendarDate.value.getFullYear();
    const month = calendarDate.value.getMonth();
    const after = new Date(year, month, 1);
    const before = new Date(year, month + 1, 0, 23, 59, 59);
    const data = await getTasks({
      page: 1,
      page_size: 200,
      due_after: after.toISOString(),
      due_before: before.toISOString(),
    });
    calendarTasks.value = data.items || [];
  } catch {
    // silent
  } finally {
    calendarLoading.value = false;
  }
}

// ── 任务列表 ──────────────────────────────────────────────────────────────
async function loadTasks() {
  loading.value = true;
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
      status: statusFilter.value || undefined,
      risk_level: riskFilter.value || undefined,
      task_type: typeFilter.value || undefined,
      priority: priorityFilter.value || undefined,
      due_after: dueRange.value?.[0] ? dueRange.value[0].toISOString() : undefined,
      due_before: dueRange.value?.[1] ? dueRange.value[1].toISOString() : undefined,
    };
    const data = await getTasks(params);
    tasks.value = data.items;
    total.value = data.total;
  } catch (e) {
    ElMessage.error(e.message || "加载任务失败");
  } finally {
    loading.value = false;
  }
}

const filteredTasks = computed(() => {
  if (!search.value) return tasks.value;
  const q = search.value.toLowerCase();
  return tasks.value.filter((t) =>
    `${t.title}${t.id}`.toLowerCase().includes(q)
  );
});

// ── 任务详情 ──────────────────────────────────────────────────────────────
const detailOpen = ref(false);
const detailTab = ref("info"); // info | timeline | comments | collaborators
const selected = ref(null);
const detailLoading = ref(false);
const actionLoading = ref(false);

const reminderForm = ref({ remind_at: null, due_at: null });
const assignForm = ref({ assignee: "", comment: "" });
const completeComment = ref("");
const cancelReason = ref("");

// ── 时间线 ────────────────────────────────────────────────────────────────
const timelineItems = ref([]);
const timelineLoading = ref(false);

async function loadTimeline(taskId) {
  timelineLoading.value = true;
  try {
    const data = await getTaskTimeline(taskId);
    timelineItems.value = (data.items || []).reverse(); // 最新在前
  } catch {
    timelineItems.value = [];
  } finally {
    timelineLoading.value = false;
  }
}

function timelineColor(eventType) {
  const map = {
    create: "#52c41a",
    complete: "#1677ff",
    cancel: "#ff4d4f",
    assign: "#fa8c16",
    comment: "#722ed1",
    attachment: "#13c2c2",
    risk_review_request: "#f5222d",
    risk_review_decide: "#eb2f96",
  };
  return map[eventType] || "#8c8c8c";
}

function timelinePayloadText(item) {
  const p = item.payload || {};
  if (item.event_type === "comment") return p.content || "";
  if (item.event_type === "attachment") return `附件：${p.name || ""}${p.url ? ` (${p.url})` : ""}`;
  if (item.event_type === "assign") return `分配给用户 #${p.new_assignee_id}${p.new_assignee_name ? `（${p.new_assignee_name}）` : ""}`;
  if (item.event_type === "complete") return p.comment ? `备注：${p.comment}` : "";
  if (item.event_type === "cancel") return p.reason ? `原因：${p.reason}` : "";
  if (item.event_type === "risk_review_decide") return `结果：${p.action} · ${p.comment || ""}`;
  if (item.event_type === "update" && p.field === "collaborators") {
    return `协作者已更新 → [${(p.new_value || []).join(", ")}]`;
  }
  return "";
}

// ── 评论 ──────────────────────────────────────────────────────────────────
const commentText = ref("");
const commentLoading = ref(false);

const commentItems = computed(() =>
  timelineItems.value.filter((e) => e.event_type === "comment")
);

async function handleAddComment() {
  const text = commentText.value.trim();
  if (!text) return;
  commentLoading.value = true;
  try {
    await addTaskComment(selected.value.id, { content: text });
    commentText.value = "";
    await loadTimeline(selected.value.id);
    ElMessage.success("评论已添加");
  } catch (e) {
    ElMessage.error(e.message || "评论失败");
  } finally {
    commentLoading.value = false;
  }
}

// ── 附件 ──────────────────────────────────────────────────────────────────
const attachmentForm = ref({ name: "", url: "" });
const attachmentLoading = ref(false);

const attachmentItems = computed(() =>
  timelineItems.value.filter((e) => e.event_type === "attachment")
);

async function handleAddAttachment() {
  const name = attachmentForm.value.name.trim();
  if (!name) { ElMessage.warning("请输入附件名称"); return; }
  attachmentLoading.value = true;
  try {
    await addTaskAttachment(selected.value.id, {
      name,
      url: attachmentForm.value.url.trim() || undefined,
    });
    attachmentForm.value = { name: "", url: "" };
    await loadTimeline(selected.value.id);
    ElMessage.success("附件已记录");
  } catch (e) {
    ElMessage.error(e.message || "操作失败");
  } finally {
    attachmentLoading.value = false;
  }
}

// ── 协作者 ────────────────────────────────────────────────────────────────
const collaboratorInput = ref("");
const collaboratorLoading = ref(false);
const collaboratorIds = computed(() => (selected.value?.collaborators || []).map(Number));

async function handleUpdateCollaborators(newIds) {
  collaboratorLoading.value = true;
  try {
    const detail = await updateTaskCollaborators(selected.value.id, { user_ids: newIds });
    selected.value = detail;
    ElMessage.success("协作者已更新");
  } catch (e) {
    ElMessage.error(e.message || "更新失败");
  } finally {
    collaboratorLoading.value = false;
  }
}

async function handleAddCollaborator() {
  const val = collaboratorInput.value.trim();
  if (!val) return;
  const id = Number(val);
  if (!Number.isInteger(id) || id <= 0) { ElMessage.warning("请输入有效的用户 ID"); return; }
  const newIds = [...new Set([...collaboratorIds.value, id])];
  await handleUpdateCollaborators(newIds);
  collaboratorInput.value = "";
}

async function handleRemoveCollaborator(userId) {
  const newIds = collaboratorIds.value.filter((id) => id !== userId);
  await handleUpdateCollaborators(newIds);
}

// ── 任务操作 ──────────────────────────────────────────────────────────────
const boardColumns = [
  { name: "待处理", statuses: ["pending", "overdue", "blocked"] },
  { name: "进行中", statuses: ["in_progress"] },
  { name: "待审核", statuses: ["awaiting_review"] },
  { name: "已完成", statuses: ["completed", "cancelled"] },
];

function getBoardItems(statuses) {
  return tasks.value.filter((t) => statuses.includes(t.status));
}

function iso(value) {
  return value instanceof Date ? value.toISOString() : value;
}

async function openDetail(task) {
  detailOpen.value = true;
  detailTab.value = "info";
  detailLoading.value = true;
  selected.value = task;
  try {
    const detail = await getTaskById(task.id);
    selected.value = detail;
    syncActionForms(detail);
    await loadTimeline(detail.id);
  } catch {
    // 保留列表行数据
  } finally {
    detailLoading.value = false;
  }
}

async function openTaskById(taskId) {
  if (!taskId) return;
  detailOpen.value = true;
  detailTab.value = "info";
  detailLoading.value = true;
  selected.value = { id: taskId, title: `任务 #${taskId}` };
  try {
    const detail = await getTaskById(taskId);
    selected.value = detail;
    syncActionForms(detail);
    await loadTimeline(detail.id);
  } catch (e) {
    ElMessage.error(e.message || `任务 #${taskId} 加载失败`);
  } finally {
    detailLoading.value = false;
  }
}

async function openTaskFromRoute() {
  const taskId = Number(route.query.task_id);
  if (!Number.isInteger(taskId) || taskId <= 0) return;
  await openTaskById(taskId);
}

function syncActionForms(task) {
  reminderForm.value = {
    remind_at: task.remind_at ? new Date(task.remind_at) : null,
    due_at: task.due_at ? new Date(task.due_at) : null,
  };
  assignForm.value = { assignee: "", comment: "" };
  completeComment.value = "";
  cancelReason.value = "";
}

async function refreshSelected() {
  if (!selected.value?.id) return;
  const detail = await getTaskById(selected.value.id);
  selected.value = detail;
  syncActionForms(detail);
}

async function runTaskAction(handler, message) {
  if (!selected.value?.id) return;
  actionLoading.value = true;
  try {
    await handler(selected.value.id);
    ElMessage.success(message);
    await refreshSelected();
    await loadTimeline(selected.value.id);
    await loadTasks();
  } catch (e) {
    ElMessage.error(e.message || "操作失败");
  } finally {
    actionLoading.value = false;
  }
}

async function handleSetReminder() {
  if (!reminderForm.value.remind_at) { ElMessage.warning("请先选择提醒时间"); return; }
  await runTaskAction(
    (id) => setTaskReminder(id, {
      remind_at: iso(reminderForm.value.remind_at),
      due_at: reminderForm.value.due_at ? iso(reminderForm.value.due_at) : undefined,
    }),
    "提醒已设置",
  );
}

async function handleCancelReminder() {
  await runTaskAction((id) => cancelTaskReminder(id), "提醒已取消");
}

async function handleAssign() {
  const value = assignForm.value.assignee.trim();
  if (!value) { ElMessage.warning("请输入负责人 ID 或姓名"); return; }
  const body = { operator_id: currentUserId.value, comment: assignForm.value.comment || undefined };
  if (/^\d+$/.test(value)) body.assignee_id = Number(value);
  else body.assignee_name = value;
  await runTaskAction((id) => assignTask(id, body), "负责人已更新");
}

async function handleComplete() {
  await runTaskAction(
    (id) => completeTask(id, { operator_id: currentUserId.value, comment: completeComment.value || undefined }),
    "任务已完成",
  );
}

async function handleCancelTask() {
  try {
    await ElMessageBox.confirm("确认取消该任务吗？", "取消任务", {
      confirmButtonText: "确认取消",
      cancelButtonText: "返回",
      type: "warning",
    });
    await runTaskAction(
      (id) => cancelTask(id, { operator_id: currentUserId.value, reason: cancelReason.value || undefined }),
      "任务已取消",
    );
  } catch { /* 用户取消弹窗 */ }
}

// ── 批量操作 ──────────────────────────────────────────────────────────────
async function handleBatchComplete() {
  if (!selectedCount.value) return;
  try {
    await ElMessageBox.confirm(`确认批量完成选中的 ${selectedCount.value} 条任务？`, "批量完成", { type: "warning" });
  } catch { return; }
  batchLoading.value = true;
  try {
    const result = await batchCompleteTasks({ task_ids: [...selectedIds.value] });
    ElMessage.success(result.message);
    clearSelection();
    await loadTasks();
  } catch (e) {
    ElMessage.error(e.message || "批量完成失败");
  } finally {
    batchLoading.value = false;
  }
}

async function handleBatchCancel() {
  if (!selectedCount.value) return;
  try {
    await ElMessageBox.confirm(`确认批量取消选中的 ${selectedCount.value} 条任务？`, "批量取消", { type: "warning" });
  } catch { return; }
  batchLoading.value = true;
  try {
    const result = await batchCancelTasks({ task_ids: [...selectedIds.value] });
    ElMessage.success(result.message);
    clearSelection();
    await loadTasks();
  } catch (e) {
    ElMessage.error(e.message || "批量取消失败");
  } finally {
    batchLoading.value = false;
  }
}

async function handleBatchAssign() {
  const val = batchAssignName.value.trim();
  if (!val) { ElMessage.warning("请输入负责人 ID 或姓名"); return; }
  if (!selectedCount.value) return;
  batchLoading.value = true;
  try {
    const body = { task_ids: [...selectedIds.value] };
    if (/^\d+$/.test(val)) body.assignee_id = Number(val);
    else body.assignee_name = val;
    const result = await batchAssignTasks(body);
    ElMessage.success(result.message);
    batchAssignName.value = "";
    clearSelection();
    await loadTasks();
  } catch (e) {
    ElMessage.error(e.message || "批量分配失败");
  } finally {
    batchLoading.value = false;
  }
}

// ── 新建任务 ──────────────────────────────────────────────────────────────
const createOpen = ref(false);
const createLoading = ref(false);
const form = ref({ text: "请张客服明天下午3点提醒回访示例三甲医院A的售后情况", reply: "" });

async function handleCreateByAgent() {
  const text = form.value.text.trim();
  if (!text) { ElMessage.warning("请输入自然语言任务描述"); return; }
  createLoading.value = true;
  try {
    const data = await chatWithAgent({ user_input: text, user_id: currentUserId.value, session_id: `task_create_${Date.now()}` });
    form.value.reply = data.messages?.join("\n") || data.reply || data.question || "Agent 已处理，请查看任务列表。";
    if (data.task) {
      ElMessage.success(`任务已创建：#${data.task.id}`);
      createOpen.value = false;
      await loadTasks();
      await openDetail(data.task);
    } else if (data.intent === "need_clarify") {
      ElMessage.warning("Agent 需要补充信息，请在智能协同页继续多轮对话");
    } else {
      ElMessage.info(form.value.reply);
    }
  } catch (e) {
    ElMessage.error(e.message || "创建任务失败");
  } finally {
    createLoading.value = false;
  }
}

// ── 翻页 & Watch ──────────────────────────────────────────────────────────
function handlePageChange(p) {
  page.value = p;
}

watch([statusFilter, riskFilter, typeFilter, priorityFilter, dueRange], () => {
  page.value = 1;
  loadTasks();
});

watch(page, loadTasks);

watch(view, (val) => {
  if (val === "calendar") loadCalendarTasks();
});

watch(() => route.query.task_id, openTaskFromRoute);

onMounted(async () => {
  await loadTasks();
  await openTaskFromRoute();
});
</script>

<template>
  <PageHeader title="任务中心" desc="统一管理客户跟进、产品反馈、投诉处理、合规审核与知识维护任务。" eyebrow="TASK CENTER">
    <button class="secondary-btn" @click="view = 'calendar'"><el-icon><Calendar /></el-icon>日历视图</button>
    <button class="primary-btn" @click="createOpen = true"><el-icon><Plus /></el-icon>新建任务</button>
  </PageHeader>

  <section class="card" v-loading="loading">
    <!-- 顶行：统计 + 视图切换 -->
    <div class="task-topline">
      <div class="task-summary">
        <span class="active">全部任务 <b>{{ total }}</b></span>
      </div>
      <div class="view-switch">
        <button :class="{ active: view === 'list' }" @click="view = 'list'" title="列表视图"><el-icon><List /></el-icon></button>
        <button :class="{ active: view === 'board' }" @click="view = 'board'" title="看板视图"><el-icon><Grid /></el-icon></button>
        <button :class="{ active: view === 'calendar' }" @click="view = 'calendar'" title="日历视图"><el-icon><Calendar /></el-icon></button>
      </div>
    </div>

    <!-- 筛选工具栏 -->
    <div class="toolbar">
      <el-input v-model="search" :prefix-icon="Search" placeholder="搜索任务标题或编号" clearable style="width:200px" />
      <el-select v-model="statusFilter" placeholder="全部状态" clearable style="width:120px">
        <el-option v-for="opt in STATUS_OPTIONS" :key="opt.value" :value="opt.value" :label="opt.label" />
      </el-select>
      <el-select v-model="riskFilter" placeholder="风险等级" clearable style="width:110px">
        <el-option v-for="opt in RISK_OPTIONS" :key="opt.value" :value="opt.value" :label="opt.label" />
      </el-select>
      <button class="small-btn" @click="filterExpanded = !filterExpanded">
        <el-icon><Filter /></el-icon>高级筛选{{ filterExpanded ? ' ▲' : ' ▼' }}
      </button>
      <span class="toolbar-spacer"></span>
      <span class="result-count">共 {{ total }} 条结果</span>
    </div>

    <!-- 高级筛选面板 -->
    <div v-if="filterExpanded" class="advanced-filter">
      <el-select v-model="typeFilter" placeholder="任务类型" clearable style="width:140px">
        <el-option v-for="opt in TASK_TYPE_OPTIONS" :key="opt.value" :value="opt.value" :label="opt.label" />
      </el-select>
      <el-select v-model="priorityFilter" placeholder="优先级" clearable style="width:110px">
        <el-option v-for="opt in PRIORITY_OPTIONS" :key="opt.value" :value="opt.value" :label="opt.label" />
      </el-select>
      <el-date-picker
        v-model="dueRange"
        type="daterange"
        range-separator="—"
        start-placeholder="截止开始"
        end-placeholder="截止结束"
        style="width:260px"
      />
      <button class="small-btn" @click="typeFilter=''; priorityFilter=''; dueRange=null">
        <el-icon><Close /></el-icon>清空高级筛选
      </button>
    </div>

    <!-- 批量操作栏 -->
    <div v-if="selectedCount > 0" class="batch-bar" v-loading="batchLoading">
      <span class="batch-label">已选 <b>{{ selectedCount }}</b> 条</span>
      <button class="small-btn" @click="handleBatchComplete"><el-icon><Check /></el-icon>批量完成</button>
      <button class="small-btn danger-btn" @click="handleBatchCancel"><el-icon><Close /></el-icon>批量取消</button>
      <div class="batch-assign-group">
        <el-input v-model="batchAssignName" placeholder="负责人 ID 或姓名" style="width:160px" clearable />
        <button class="small-btn" @click="handleBatchAssign">批量分配</button>
      </div>
      <button class="ghost-btn" @click="clearSelection">取消选择</button>
    </div>

    <!-- 列表视图 -->
    <table v-if="view === 'list'" class="list-table task-table">
      <thead>
        <tr>
          <th>
            <el-checkbox
              :indeterminate="indeterminate"
              :model-value="allSelected"
              @change="toggleAll"
            />
          </th>
          <th>任务信息</th><th>类型</th><th>优先级</th><th>风险等级</th>
          <th>负责人</th><th>截止时间</th><th>状态</th><th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="task in filteredTasks" :key="task.id" :class="{ 'row-selected': selectedIds.has(task.id) }">
          <td>
            <el-checkbox
              :model-value="selectedIds.has(task.id)"
              @change="toggleSelect(task.id)"
            />
          </td>
          <td>
            <strong class="table-title">{{ task.title }}</strong>
            <span class="table-sub">#{{ task.id }}</span>
          </td>
          <td><span class="source-chip">{{ typeLabel(task.type) }}</span></td>
          <td><span class="priority-chip" :class="task.priority">{{ priorityLabel(task.priority) }}</span></td>
          <td><RiskBadge :level="task.risk_level" compact /></td>
          <td>用户 #{{ task.assignee_id }}</td>
          <td>{{ formatDue(task.due_at) }}</td>
          <td><span class="status-dot" :class="statusClass(task.status)">{{ statusLabel(task.status) }}</span></td>
          <td><button class="ghost-btn" @click="openDetail(task)"><el-icon><View /></el-icon>详情</button></td>
        </tr>
        <tr v-if="!filteredTasks.length && !loading">
          <td colspan="9" class="empty-row">暂无任务数据</td>
        </tr>
      </tbody>
    </table>

    <!-- 看板视图 -->
    <div v-else-if="view === 'board'" class="board">
      <section v-for="column in boardColumns" :key="column.name">
        <header>
          <strong>{{ column.name }}</strong>
          <span>{{ getBoardItems(column.statuses).length }}</span>
        </header>
        <button v-for="task in getBoardItems(column.statuses)" :key="task.id" class="board-item" @click="openDetail(task)">
          <div><span class="soft-chip">{{ typeLabel(task.type) }}</span><RiskBadge :level="task.risk_level" compact /></div>
          <h4>{{ task.title }}</h4>
          <p>#{{ task.id }}</p>
          <footer>
            <span>用户 #{{ task.assignee_id }}</span>
            <b>{{ formatDue(task.due_at) }}</b>
          </footer>
        </button>
        <div v-if="!getBoardItems(column.statuses).length" class="board-empty">暂无任务</div>
      </section>
    </div>

    <!-- 日历视图 -->
    <div v-else-if="view === 'calendar'" class="calendar-wrap" v-loading="calendarLoading">
      <div class="calendar-header">
        <button class="ghost-btn" @click="prevMonth"><el-icon><ArrowLeft /></el-icon></button>
        <span class="calendar-title">{{ calendarYear }} 年 {{ calendarMonth }} 月</span>
        <button class="ghost-btn" @click="nextMonth"><el-icon><ArrowRight /></el-icon></button>
      </div>
      <div class="calendar-grid">
        <div v-for="day in ['日','一','二','三','四','五','六']" :key="day" class="cal-weekday">{{ day }}</div>
        <div
          v-for="(cell, idx) in calendarDays"
          :key="idx"
          class="cal-cell"
          :class="{ 'other-month': !cell.inMonth, 'today': isToday(cell.date) }"
        >
          <span class="cal-day-num">{{ cell.date.getDate() }}</span>
          <div class="cal-tasks">
            <div
              v-for="task in getCalendarDayTasks(cell.date).slice(0, 3)"
              :key="task.id"
              class="cal-task-item"
              :class="statusClass(task.status)"
              @click="openDetail(task)"
              :title="task.title"
            >
              {{ task.title }}
            </div>
            <div v-if="getCalendarDayTasks(cell.date).length > 3" class="cal-more">
              +{{ getCalendarDayTasks(cell.date).length - 3 }} 条
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 分页（非日历视图） -->
    <div v-if="view !== 'calendar'" class="pagination-row">
      <span>共 {{ total }} 条任务</span>
      <el-pagination
        small background
        layout="prev, pager, next"
        :total="total"
        :page-size="pageSize"
        :current-page="page"
        @current-change="handlePageChange"
      />
    </div>
  </section>

  <!-- ── 任务详情抽屉 ─────────────────────────────────────────────── -->
  <el-drawer v-model="detailOpen" size="520px" :destroy-on-close="false">
    <template v-if="selected" #header>
      <div class="drawer-title">
        <h3>{{ selected.title }}</h3>
        <p>#{{ selected.id }} · {{ selected.source ?? '-' }}</p>
      </div>
    </template>

    <div v-if="detailLoading" class="drawer-loading"><el-skeleton :rows="8" animated /></div>

    <template v-else-if="selected">
      <!-- 状态行 -->
      <div class="detail-status-row">
        <RiskBadge :level="selected.risk_level" />
        <span class="status-dot" :class="statusClass(selected.status)">{{ statusLabel(selected.status) }}</span>
        <span class="review-tag">{{ reviewStatusLabel(selected.review_status) }}</span>
      </div>

      <!-- 标签页 -->
      <el-tabs v-model="detailTab" class="detail-tabs">
        <!-- ① 基本信息 + 操作 -->
        <el-tab-pane label="基本信息" name="info">
          <div class="info-grid">
            <div class="info-item"><span>任务类型</span><strong>{{ typeLabel(selected.type) }}</strong></div>
            <div class="info-item"><span>优先级</span><strong>{{ priorityLabel(selected.priority) }}</strong></div>
            <div class="info-item"><span>负责人</span><strong>用户 #{{ selected.assignee_id }}</strong></div>
            <div class="info-item"><span>截止时间</span><strong>{{ formatDue(selected.due_at) }}</strong></div>
            <div class="info-item"><span>提醒时间</span><strong>{{ formatDateTime(selected.remind_at) }}</strong></div>
            <div class="info-item"><span>关联医院</span><strong>{{ selected.hospital_id ? `#${selected.hospital_id}` : '-' }}</strong></div>
            <div class="info-item"><span>关联产品</span><strong>{{ selected.product_id ? `#${selected.product_id}` : '-' }}</strong></div>
            <div class="info-item"><span>创建时间</span><strong>{{ formatDateTime(selected.created_at) }}</strong></div>
          </div>

          <div v-if="selected.risk_suggested_action || selected.risk_reason || selected.description" class="note-section">
            <div v-if="selected.risk_suggested_action">
              <h5>SOP 处理建议</h5>
              <div class="note-box">{{ selected.risk_suggested_action }}</div>
            </div>
            <div v-if="selected.risk_reason">
              <h5>风险原因</h5>
              <div class="note-box">{{ selected.risk_reason }}</div>
            </div>
            <div v-if="selected.description">
              <h5>任务描述</h5>
              <div class="note-box">{{ selected.description }}</div>
            </div>
          </div>

          <!-- 操作面板 -->
          <div class="action-panel" v-loading="actionLoading">
            <div class="action-block">
              <span class="action-label">提醒与截止</span>
              <div class="dialog-grid">
                <el-date-picker v-model="reminderForm.remind_at" type="datetime" placeholder="提醒时间" style="width:100%" />
                <el-date-picker v-model="reminderForm.due_at" type="datetime" placeholder="截止时间" style="width:100%" />
              </div>
              <div class="action-row">
                <button class="secondary-btn" @click="handleCancelReminder">取消提醒</button>
                <button class="primary-btn" @click="handleSetReminder">设置提醒</button>
              </div>
            </div>
            <div class="action-block">
              <span class="action-label">重新分配</span>
              <el-input v-model="assignForm.assignee" placeholder="负责人 ID 或姓名，例如 2 / 张客服" />
              <el-input v-model="assignForm.comment" type="textarea" :rows="2" placeholder="分配备注（可选）" />
              <div class="action-row"><button class="primary-btn" @click="handleAssign">更新负责人</button></div>
            </div>
            <div class="action-block">
              <span class="action-label">完成或取消</span>
              <el-input v-model="completeComment" type="textarea" :rows="2" placeholder="完成备注（可选）" />
              <el-input v-model="cancelReason" type="textarea" :rows="2" placeholder="取消原因（可选）" />
              <div class="action-row">
                <button class="secondary-btn danger-btn" @click="handleCancelTask">取消任务</button>
                <button class="primary-btn" @click="handleComplete">标记完成</button>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <!-- ② 时间线 -->
        <el-tab-pane label="时间线" name="timeline">
          <div v-if="timelineLoading" class="tab-loading"><el-skeleton :rows="4" animated /></div>
          <div v-else-if="!timelineItems.length" class="tab-empty">暂无事件记录</div>
          <el-timeline v-else class="event-timeline">
            <el-timeline-item
              v-for="item in timelineItems"
              :key="item.id"
              :color="timelineColor(item.event_type)"
              :timestamp="formatDateTime(item.created_at)"
              placement="top"
            >
              <div class="tl-item">
                <span class="tl-type-tag">{{ eventTypeLabel(item.event_type) }}</span>
                <span class="tl-operator">用户 #{{ item.operator_id ?? '系统' }} ({{ item.operator_kind }})</span>
              </div>
              <p v-if="timelinePayloadText(item)" class="tl-detail">{{ timelinePayloadText(item) }}</p>
            </el-timeline-item>
          </el-timeline>
        </el-tab-pane>

        <!-- ③ 评论 + 附件 -->
        <el-tab-pane label="评论" name="comments">
          <!-- 评论列表 -->
          <div v-if="!commentItems.length" class="tab-empty">暂无评论</div>
          <div v-else class="comment-list">
            <div v-for="c in commentItems" :key="c.id" class="comment-item">
              <div class="comment-meta">
                <span class="comment-author">用户 #{{ c.operator_id }}</span>
                <span class="comment-time">{{ formatDateTime(c.created_at) }}</span>
              </div>
              <p class="comment-content">{{ (c.payload || {}).content }}</p>
            </div>
          </div>
          <!-- 添加评论 -->
          <div class="comment-form">
            <el-input
              v-model="commentText"
              type="textarea"
              :rows="3"
              placeholder="输入评论内容…"
            />
            <div class="action-row">
              <button class="primary-btn" :disabled="commentLoading || !commentText.trim()" @click="handleAddComment">
                {{ commentLoading ? "提交中…" : "发表评论" }}
              </button>
            </div>
          </div>

          <!-- 附件区域 -->
          <div class="attachment-section">
            <h5>附件记录</h5>
            <div v-if="!attachmentItems.length" class="tab-empty">暂无附件</div>
            <div v-else class="attachment-list">
              <div v-for="att in attachmentItems" :key="att.id" class="att-item">
                <span class="att-name">{{ (att.payload || {}).name }}</span>
                <a v-if="(att.payload || {}).url" :href="att.payload.url" target="_blank" class="att-link">查看</a>
                <span class="att-time">{{ formatDateTime(att.created_at) }}</span>
              </div>
            </div>
            <div class="att-form">
              <el-input v-model="attachmentForm.name" placeholder="附件名称" style="width:160px" />
              <el-input v-model="attachmentForm.url" placeholder="URL（可选）" style="width:200px" />
              <button class="small-btn" :disabled="attachmentLoading" @click="handleAddAttachment">记录附件</button>
            </div>
          </div>
        </el-tab-pane>

        <!-- ④ 协作者 -->
        <el-tab-pane label="协作者" name="collaborators">
          <div v-if="!collaboratorIds.length" class="tab-empty">暂无协作者</div>
          <div v-else class="collab-list">
            <div v-for="uid in collaboratorIds" :key="uid" class="collab-item" v-loading="collaboratorLoading">
              <span>用户 #{{ uid }}</span>
              <button class="icon-btn" @click="handleRemoveCollaborator(uid)" title="移除"><el-icon><Close /></el-icon></button>
            </div>
          </div>
          <div class="collab-add">
            <el-input v-model="collaboratorInput" placeholder="输入用户 ID 添加协作者" style="width:220px" @keyup.enter="handleAddCollaborator" />
            <button class="primary-btn" @click="handleAddCollaborator">添加</button>
          </div>
        </el-tab-pane>
      </el-tabs>
    </template>
  </el-drawer>

  <!-- ── 新建任务弹窗 ────────────────────────────────────────────── -->
  <el-dialog v-model="createOpen" title="新建任务" width="540px">
    <el-form label-position="top">
      <el-form-item label="自然语言任务描述">
        <el-input v-model="form.text" type="textarea" :rows="5" placeholder="例如：请张客服明天下午3点提醒回访示例三甲医院A的售后情况" />
      </el-form-item>
      <div v-if="form.reply" class="note-box">{{ form.reply }}</div>
    </el-form>
    <template #footer>
      <button class="secondary-btn" @click="createOpen = false">取消</button>
      <button class="primary-btn" :disabled="createLoading" @click="handleCreateByAgent">
        {{ createLoading ? "Agent 处理中…" : "创建任务" }}
      </button>
    </template>
  </el-dialog>
</template>

<style scoped>
/* ── 顶行 ──────────────────────────────────────────────────────── */
.task-topline { display: flex; justify-content: space-between; padding: 0 15px; border-bottom: 1px solid #edf0f4; }
.task-summary { display: flex; gap: 22px; }
.task-summary span { padding: 15px 1px 13px; color: #8490a0; font-size: 12px; }
.task-summary span.active { color: #2868da; border-bottom: 2px solid #2868da; font-weight: 600; }
.task-summary b { margin-left: 3px; font-size: 10px; }
.view-switch { display: flex; align-items: center; }
.view-switch button { display: grid; width: 31px; height: 28px; place-items: center; border: 1px solid #e2e7ed; color: #8b96a6; background: white; }
.view-switch button:first-child { border-radius: 6px 0 0 6px; }
.view-switch button:last-child { margin-left: -1px; border-radius: 0 6px 6px 0; }
.view-switch button.active { z-index: 1; border-color: #a8c4f8; color: #276adc; background: #f0f5ff; }
/* ── 工具栏 ─────────────────────────────────────────────────────── */
.result-count { color: #9ba5b3; font-size: 11px; }
/* ── 高级筛选面板 ────────────────────────────────────────────────── */
.advanced-filter { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; padding: 10px 15px 12px; background: #f8fafc; border-bottom: 1px solid #edf0f4; }
/* ── 批量操作栏 ─────────────────────────────────────────────────── */
.batch-bar { display: flex; align-items: center; gap: 10px; padding: 9px 15px; background: #f0f5ff; border-bottom: 1px solid #d6e4ff; flex-wrap: wrap; }
.batch-label { font-size: 12px; color: #2868da; font-weight: 600; }
.batch-label b { margin-left: 3px; }
.batch-assign-group { display: flex; gap: 6px; align-items: center; }
/* ── 列表表格 ───────────────────────────────────────────────────── */
.task-table th:first-child, .task-table td:first-child { width: 36px; padding-right: 0; }
.row-selected td { background: #f0f5ff !important; }
.priority-chip { display: inline-block; padding: 1px 7px; border-radius: 10px; font-size: 11px; background: #f3f5f7; color: #6b778c; }
.priority-chip.urgent { background: #fff1f0; color: #f5222d; }
.priority-chip.high { background: #fff7e6; color: #fa8c16; }
/* ── 看板 ────────────────────────────────────────────────────────── */
.board { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; padding: 14px; background: #f8fafc; }
.board section { min-height: 400px; }
.board header { display: flex; align-items: center; gap: 6px; margin-bottom: 9px; padding: 0 3px; }
.board header strong { color: #58667a; font-size: 12px; }
.board header span { display: grid; width: 18px; height: 18px; place-items: center; border-radius: 50%; color: #8490a1; font-size: 10px; background: #e9edf3; }
.board-item { width: 100%; margin-bottom: 9px; padding: 11px; border: 1px solid #e6ebf1; border-radius: 8px; text-align: left; background: white; box-shadow: 0 4px 10px rgba(44,65,95,.035); }
.board-item > div { display: flex; justify-content: space-between; }
.board-item h4 { margin-top: 9px; color: #4a586c; font-size: 11px; line-height: 1.6; }
.board-item p { margin-top: 5px; color: #98a2af; font-size: 10px; }
.board-item footer { display: flex; justify-content: space-between; margin-top: 13px; color: #93a0af; font-size: 10px; }
.board-item footer b { color: #d78337; font-weight: 500; }
.board-empty { padding: 25px 0; color: #afb7c2; font-size: 11px; text-align: center; }
/* ── 日历视图 ───────────────────────────────────────────────────── */
.calendar-wrap { padding: 14px; }
.calendar-header { display: flex; align-items: center; justify-content: center; gap: 16px; margin-bottom: 14px; }
.calendar-title { font-size: 15px; font-weight: 600; color: #2c3e50; min-width: 120px; text-align: center; }
.calendar-grid { display: grid; grid-template-columns: repeat(7, 1fr); border: 1px solid #e8ecf1; border-radius: 8px; overflow: hidden; }
.cal-weekday { padding: 8px; text-align: center; font-size: 11px; font-weight: 600; color: #8490a0; background: #f8fafc; border-bottom: 1px solid #e8ecf1; }
.cal-cell { min-height: 90px; padding: 6px; border-right: 1px solid #e8ecf1; border-bottom: 1px solid #e8ecf1; background: white; }
.cal-cell:nth-child(7n) { border-right: 0; }
.cal-cell.other-month { background: #fcfcfd; }
.cal-cell.other-month .cal-day-num { color: #c5cdd8; }
.cal-cell.today { background: #f0f5ff; }
.cal-cell.today .cal-day-num { background: #2868da; color: white; border-radius: 50%; width: 22px; height: 22px; display: inline-flex; align-items: center; justify-content: center; }
.cal-day-num { display: block; font-size: 12px; color: #4a586c; margin-bottom: 4px; }
.cal-tasks { display: flex; flex-direction: column; gap: 2px; }
.cal-task-item { padding: 1px 5px; border-radius: 3px; font-size: 10px; cursor: pointer; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; background: #e8f0fe; color: #2868da; }
.cal-task-item.done { background: #f0fff4; color: #389e0d; }
.cal-task-item.overdue { background: #fff1f0; color: #f5222d; }
.cal-task-item.waiting { background: #fffbe6; color: #d48806; }
.cal-more { font-size: 10px; color: #8490a0; }
/* ── 详情抽屉 ───────────────────────────────────────────────────── */
.drawer-loading { padding: 20px; }
.detail-status-row { display: flex; align-items: center; gap: 10px; padding: 0 0 14px; }
.review-tag { padding: 2px 8px; border-radius: 10px; font-size: 11px; background: #f3f5f7; color: #6b778c; }
.detail-tabs { margin-top: 4px; }
.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 18px; padding: 4px 0 14px; }
.info-item { display: flex; flex-direction: column; gap: 2px; }
.info-item span { font-size: 11px; color: #8490a0; }
.info-item strong { font-size: 12px; color: #2c3e50; }
.note-section { display: flex; flex-direction: column; gap: 10px; padding-bottom: 14px; }
.note-section h5 { margin: 0 0 4px; font-size: 12px; color: #5a6475; }
.action-panel { border-top: 1px solid #eef1f4; padding-top: 4px; }
.action-block { display: grid; gap: 8px; padding: 10px 0; border-top: 1px solid #f0f2f5; }
.action-block:first-of-type { border-top: 0; }
.action-label { color: #7a8798; font-size: 11px; font-weight: 600; }
.action-row { display: flex; justify-content: flex-end; gap: 8px; }
.action-row .primary-btn, .action-row .secondary-btn { padding: 8px 11px; }
.dialog-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
/* ── 时间线 ─────────────────────────────────────────────────────── */
.tab-loading, .tab-empty { padding: 20px 0; color: #aab3bf; font-size: 12px; text-align: center; }
.event-timeline { padding: 10px 0; }
.tl-item { display: flex; align-items: center; gap: 8px; }
.tl-type-tag { padding: 1px 7px; border-radius: 10px; font-size: 11px; background: #eef1f4; color: #5a6475; font-weight: 600; }
.tl-operator { font-size: 11px; color: #8490a0; }
.tl-detail { margin: 4px 0 0; font-size: 11px; color: #4a586c; line-height: 1.5; }
/* ── 评论 ────────────────────────────────────────────────────────── */
.comment-list { display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px; }
.comment-item { padding: 10px 12px; background: #f8fafc; border-radius: 8px; border: 1px solid #edf0f4; }
.comment-meta { display: flex; justify-content: space-between; margin-bottom: 5px; }
.comment-author { font-size: 11px; font-weight: 600; color: #2868da; }
.comment-time { font-size: 10px; color: #aab3bf; }
.comment-content { font-size: 12px; color: #4a586c; line-height: 1.6; margin: 0; }
.comment-form { border-top: 1px solid #edf0f4; padding-top: 12px; display: flex; flex-direction: column; gap: 8px; }
/* ── 附件 ────────────────────────────────────────────────────────── */
.attachment-section { border-top: 1px solid #edf0f4; margin-top: 16px; padding-top: 14px; }
.attachment-section h5 { font-size: 12px; color: #5a6475; margin: 0 0 10px; }
.attachment-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.att-item { display: flex; align-items: center; gap: 10px; padding: 6px 10px; background: #f8fafc; border-radius: 6px; border: 1px solid #edf0f4; }
.att-name { flex: 1; font-size: 12px; color: #4a586c; font-weight: 500; }
.att-link { font-size: 11px; color: #2868da; text-decoration: none; }
.att-link:hover { text-decoration: underline; }
.att-time { font-size: 10px; color: #aab3bf; }
.att-form { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
/* ── 协作者 ─────────────────────────────────────────────────────── */
.collab-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.collab-item { display: flex; align-items: center; justify-content: space-between; padding: 7px 10px; background: #f8fafc; border-radius: 6px; border: 1px solid #edf0f4; font-size: 12px; color: #4a586c; }
.collab-add { display: flex; gap: 8px; align-items: center; }
.icon-btn { padding: 4px 6px; border: none; border-radius: 4px; color: #f5222d; background: transparent; cursor: pointer; display: flex; align-items: center; }
.icon-btn:hover { background: #fff1f0; }
/* ── 通用 ────────────────────────────────────────────────────────── */
.empty-row { padding: 32px; color: #aab3bf; text-align: center; font-size: 12px; }
</style>
