<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, computed } from "vue";
import {
  ChatDotRound, CircleCheck, Document, Promotion,
  Refresh, Warning, Edit, UserFilled, OfficeBuilding, Box,
  ArrowDown, ArrowUp, Cpu,
} from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import PageHeader from "../components/PageHeader.vue";
import RiskBadge from "../components/RiskBadge.vue";
import { chatWithAgent, confirmDraft, searchCandidates, getSessionHistory, getThinkingTrace } from "../api/agent.js";
import { currentUserId } from "../store/app.js";
import { typeLabel, priorityLabel, riskLabel, statusLabel, formatDue, formatDateTime } from "../utils/mappers.js";

// ── 聊天状态 ──
const input = ref("");
const chatBody = ref(null);
const isTyping = ref(false);
const sessionId = ref(null);

// ── 右侧面板数据 ──
const taskCreated = ref(false);
const draft = ref(null);
const riskAssessment = ref(null);
const ragResult = ref(null);
const lastTask = ref(null);
const summaryResult = ref(null);
const queryResult = ref(null);

// ── 错误恢复状态 ──
const hasError = ref(false);
const errorMessage = ref("");
const candidates = ref({ assignee: [], hospital: [], product: [] });
// 用户选定的候选 ID
const selectedAssigneeId = ref(null);
const selectedAssigneeName = ref("");
const selectedHospitalId = ref(null);
const selectedHospitalName = ref("");
const selectedProductId = ref(null);
const selectedProductName = ref("");

// ── 会话历史 drawer ──
const historyDrawerVisible = ref(false);
const historyMessages = ref([]);
const historyLoading = ref(false);

// ── 思考过程轮询 ──
const thinkingPollTimer = ref(null);

// ── 消息列表 ──
const messages = ref([
  {
    from: "agent",
    time: nowTime(),
    text: "早上好，我是 MedFlow 协同助手。你可以直接告诉我需要跟进的事项，我会帮你整理任务、识别风险并匹配 SOP。",
  },
]);

const suggestions = ["生成今日日报", "生成本周周报", "查询我今天到期的任务", "检索设备异常 SOP"];

// ── 是否显示确认按钮 ──
const canConfirm = computed(() => {
  if (!draft.value) return false;
  if (taskCreated.value) return false;
  // create_error 时也可以重试提交（需要先选候选项）
  return true;
});

// ── 候选项是否已处理（create_error 时检查是否选了负责人）──
const candidateResolved = computed(() => {
  if (!hasError.value) return true;
  const hasAssigneeCands = candidates.value.assignee?.length > 0;
  if (hasAssigneeCands && !selectedAssigneeId.value) return false;
  return true;
});

function nowTime() {
  return new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function createTraceId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID().replace(/-/g, "");
  }
  return `t${Date.now().toString(16)}${Math.random().toString(16).slice(2, 10)}`;
}

function stopThinkingPoll() {
  if (thinkingPollTimer.value) {
    clearInterval(thinkingPollTimer.value);
    thinkingPollTimer.value = null;
  }
}

async function refreshThinkingSteps(msg) {
  if (!msg?.traceId) return;
  try {
    const data = await getThinkingTrace(msg.traceId);
    msg.thinkingSteps = data.steps || [];
    await scrollBottom();
  } catch {
    // 请求处理中时可能尚无 trace 记录，忽略即可
  }
}

function startThinkingPoll(msg, traceId) {
  stopThinkingPoll();
  msg.traceId = traceId;
  msg.thinkingExpanded = true;
  refreshThinkingSteps(msg);
  thinkingPollTimer.value = setInterval(() => refreshThinkingSteps(msg), 500);
}

function createPendingAgentMessage(traceId) {
  return {
    from: "agent",
    time: nowTime(),
    text: "",
    pending: true,
    traceId,
    thinkingSteps: [],
    thinkingExpanded: true,
  };
}

function finalizeAgentMessage(msg, data) {
  msg.pending = false;
  msg.text = buildReplyText(data);
  msg.analysis = !!data.risk_assessment;
  msg.error = data.intent === "create_error";
  if (data.trace_id) msg.traceId = data.trace_id;
  if (data.thinking_steps?.length) {
    msg.thinkingSteps = data.thinking_steps;
  }
  msg.thinkingExpanded = true;
}


// ── 生成/恢复 sessionId ──
function ensureSessionId() {
  if (!sessionId.value) {
    sessionId.value = `s_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    localStorage.setItem("agent_session_id", sessionId.value);
  }
}

onMounted(() => {
  const stored = localStorage.getItem("agent_session_id");
  if (stored) {
    sessionId.value = stored;
  }
});

onBeforeUnmount(() => {
  stopThinkingPoll();
});

// ── 发送消息 ──
async function sendMessage(text = input.value) {
  const trimmed = text.trim();
  if (!trimmed) return;

  ensureSessionId();
  messages.value.push({ from: "user", time: nowTime(), text: trimmed });
  input.value = "";
  isTyping.value = true;
  taskCreated.value = false;
  hasError.value = false;

  await scrollBottom();

  const traceId = createTraceId();
  const pendingMsg = createPendingAgentMessage(traceId);
  messages.value.push(pendingMsg);
  startThinkingPoll(pendingMsg, traceId);
  await scrollBottom();

  try {
    const data = await chatWithAgent({
      user_input: trimmed,
      user_id: currentUserId.value,
      session_id: sessionId.value,
      trace_id: traceId,
    });

    if (data.session_id) {
      sessionId.value = data.session_id;
      localStorage.setItem("agent_session_id", data.session_id);
    }

    applyResponseData(data);
    stopThinkingPoll();
    await refreshThinkingSteps(pendingMsg);
    finalizeAgentMessage(pendingMsg, data);
  } catch (error) {
    stopThinkingPoll();
    pendingMsg.pending = false;
    pendingMsg.error = true;
    pendingMsg.text = `处理失败：${error.message}。请检查后端服务是否运行。`;
    ElMessage.error(error.message || "Agent 调用失败");
  } finally {
    isTyping.value = false;
    await scrollBottom();
  }
}

// ── 草稿确认（直接调 confirm-draft，不经过 LLM）──
async function handleConfirmDraft() {
  if (!draft.value) return;
  ensureSessionId();
  isTyping.value = true;
  taskCreated.value = false;
  hasError.value = false;

  const payload = {
    session_id: sessionId.value,
    title: draft.value.title,
    type: draft.value.type || "other",
    priority: draft.value.priority || "medium",
    description: draft.value.description || null,
    assignee_name: selectedAssigneeName.value || draft.value.assignee_name || null,
    assignee_id: selectedAssigneeId.value || null,
    hospital_name: selectedHospitalName.value || draft.value.hospital_name || null,
    hospital_id: selectedHospitalId.value || null,
    product_name: selectedProductName.value || draft.value.product_name || null,
    product_id: selectedProductId.value || null,
    due_at: draft.value.due_at || null,
    remind_at: draft.value.remind_at || null,
    risk_keywords: draft.value.risk_keywords || [],
  };

  messages.value.push({ from: "user", time: nowTime(), text: `确认提交草稿：${draft.value.title}` });
  await scrollBottom();

  try {
    const data = await confirmDraft(payload);
    applyResponseData(data);
    const replyText = buildReplyText(data);
    const isErr = data.intent === "create_error";
    messages.value.push({
      from: "agent",
      time: nowTime(),
      text: replyText,
      analysis: !!data.risk_assessment,
      error: isErr,
      traceId: data.trace_id || null,
      thinkingSteps: data.thinking_steps || [],
      thinkingExpanded: (data.thinking_steps || []).length > 0,
    });
    if (!isErr) {
      ElMessage.success("任务创建成功！");
    }
  } catch (e) {
    messages.value.push({ from: "agent", time: nowTime(), text: `提交失败：${e.message}`, error: true });
    ElMessage.error(e.message || "草稿提交失败");
  } finally {
    isTyping.value = false;
    await scrollBottom();
  }
}

// ── 候选项搜索 ──
async function searchAssigneeCandidates(keyword) {
  if (!keyword?.trim()) return;
  try {
    const data = await searchCandidates({ entity_type: "user", name: keyword });
    candidates.value.assignee = data.items || [];
  } catch { /* 忽略搜索错误 */ }
}

async function searchHospitalCandidates(keyword) {
  if (!keyword?.trim()) return;
  try {
    const data = await searchCandidates({ entity_type: "hospital", name: keyword });
    candidates.value.hospital = data.items || [];
  } catch { /* 忽略搜索错误 */ }
}

// ── 选定候选项 ──
function pickAssignee(item) {
  selectedAssigneeId.value = item.id;
  selectedAssigneeName.value = item.name;
}

function pickHospital(item) {
  selectedHospitalId.value = item.id;
  selectedHospitalName.value = item.name;
}

// ── 响应数据应用 ──
function applyResponseData(data) {
  if (data.draft) draft.value = data.draft;
  if (data.risk_assessment) riskAssessment.value = data.risk_assessment;
  if (data.rag_result) ragResult.value = data.rag_result;
  if (data.summary) summaryResult.value = data.summary;
  if (data.query_result) queryResult.value = data.query_result;
  if (data.task) {
    taskCreated.value = true;
    lastTask.value = data.task;
    hasError.value = false;
    // 清除候选选择状态
    selectedAssigneeId.value = null;
    selectedAssigneeName.value = "";
    selectedHospitalId.value = null;
    selectedHospitalName.value = "";
    candidates.value = { assignee: [], hospital: [], product: [] };
  }
  if (data.intent === "create_error") {
    hasError.value = true;
    errorMessage.value = data.error_message || "任务创建失败";
    if (data.candidates) {
      candidates.value = {
        assignee: data.candidates.assignee || [],
        hospital: data.candidates.hospital || [],
        product: data.candidates.product || [],
      };
    }
  }
}

// ── 回复文本构建 ──
function buildReplyText(data) {
  if (data.intent === "create_error") {
    return `${data.error_message || "任务创建失败"}\n请从右侧候选列表中选择正确的负责人后重新提交。`;
  }
  if (data.messages?.length > 0) return data.messages.join("\n");
  if (data.question) return data.question;
  if (data.reply) return data.reply;
  if (draft.value) {
    return `已识别为「${typeLabel(draft.value.type)}」任务，右侧草稿已更新。${
      riskAssessment.value ? `风险等级：${riskAssessment.value.level}。` : ""
    }`;
  }
  return "已收到，请继续补充信息。";
}

// ── 会话历史 ──
async function openHistory() {
  if (!sessionId.value) return;
  historyDrawerVisible.value = true;
  historyLoading.value = true;
  try {
    const data = await getSessionHistory(sessionId.value);
    historyMessages.value = data.messages || [];
  } catch (e) {
    ElMessage.error("历史加载失败：" + e.message);
  } finally {
    historyLoading.value = false;
  }
}

// ── 新会话 ──
function startNewSession() {
  stopThinkingPoll();
  messages.value = [{ from: "agent", time: nowTime(), text: "新会话已开始。请告诉我需要处理的事项。" }];
  sessionId.value = `s_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
  localStorage.setItem("agent_session_id", sessionId.value);
  draft.value = null;
  riskAssessment.value = null;
  ragResult.value = null;
  lastTask.value = null;
  summaryResult.value = null;
  queryResult.value = null;
  taskCreated.value = false;
  hasError.value = false;
  errorMessage.value = "";
  candidates.value = { assignee: [], hospital: [], product: [] };
  selectedAssigneeId.value = null;
  selectedAssigneeName.value = "";
  selectedHospitalId.value = null;
  selectedHospitalName.value = "";
}

function toggleThinking(msg) {
  if (msg.pending) return;
  msg.thinkingExpanded = !msg.thinkingExpanded;
}

async function loadThinking(msg) {
  if (!msg.traceId || msg.thinkingSteps?.length) return;
  try {
    const data = await getThinkingTrace(msg.traceId);
    msg.thinkingSteps = data.steps || [];
  } catch (err) {
    ElMessage.error("思考过程加载失败：" + err.message);
  }
}

async function openThinking(msg) {
  if (!msg.thinkingSteps?.length && msg.traceId) {
    await loadThinking(msg);
    if (msg.thinkingSteps?.length) {
      msg.thinkingExpanded = true;
    }
    return;
  }
  toggleThinking(msg);
}

function thinkingStatusLabel(status) {
  if (status === "ok") return "成功";
  if (status === "error") return "失败";
  if (status === "retry") return "重试";
  return status || "未知";
}

async function scrollBottom() {
  await nextTick();
  if (chatBody.value) chatBody.value.scrollTop = chatBody.value.scrollHeight;
}
</script>

<template>
  <PageHeader title="智能协同" desc="用自然语言描述业务事项，Agent 将协助你完成任务创建、风险判断与 SOP 检索。" eyebrow="AI ASSISTANT">
    <span class="agent-health"><i></i> Agent 在线</span>
  </PageHeader>

  <div class="assistant-grid">
    <!-- 左侧对话区 -->
    <section class="card conversation">
      <div class="chat-head">
        <div class="ai-avatar"><el-icon><ChatDotRound /></el-icon></div>
        <div><h3>MedFlow 协同助手</h3><p><i></i> 在线 · 已连接企业知识库</p></div>
        <div class="head-actions">
          <button class="small-btn" @click="openHistory" :disabled="!sessionId" title="查看本次会话历史">
            <el-icon><Document /></el-icon>历史
          </button>
          <button class="small-btn" @click="startNewSession"><el-icon><Refresh /></el-icon>新会话</button>
        </div>
      </div>

      <div ref="chatBody" class="chat-body">
        <div class="chat-date">今天</div>
        <div v-for="(msg, idx) in messages" :key="idx" class="message-row" :class="msg.from">
          <div v-if="msg.from === 'agent'" class="msg-avatar">M</div>
          <div class="msg-content">
            <div
              v-if="msg.text || msg.analysis || msg.error"
              class="message"
              :class="{ analysis: msg.analysis, error: msg.error }"
            >
              <span v-if="msg.analysis" class="analysis-label"><el-icon><Warning /></el-icon> 风险分析完成</span>
              <span v-if="msg.error && !msg.analysis" class="error-label"><el-icon><Warning /></el-icon> 处理错误</span>
              {{ msg.text }}
            </div>
            <div
              v-if="msg.from === 'agent' && (msg.pending || msg.thinkingSteps?.length || msg.traceId)"
              class="thinking-panel"
              :class="{ 'is-live': msg.pending }"
            >
              <button class="thinking-toggle" @click="openThinking(msg)">
                <el-icon><Cpu /></el-icon>
                <span>
                  <template v-if="msg.pending">思考中…</template>
                  <template v-else>{{ msg.thinkingExpanded ? "收起思考过程" : "查看思考过程" }}</template>
                  <template v-if="msg.thinkingSteps?.length">（{{ msg.thinkingSteps.length }} 步）</template>
                </span>
                <el-icon v-if="!msg.pending"><ArrowUp v-if="msg.thinkingExpanded" /><ArrowDown v-else /></el-icon>
                <i v-else class="thinking-pulse"></i>
              </button>
              <div v-if="msg.thinkingExpanded" class="thinking-steps">
                <div v-if="msg.pending && !msg.thinkingSteps?.length" class="thinking-waiting">正在分析您的问题…</div>
                <div
                  v-for="step in msg.thinkingSteps"
                  :key="`${msg.traceId || msg.time}-${step.order}`"
                  class="thinking-step"
                  :class="`status-${step.status}`"
                >
                  <div class="step-head">
                    <span class="step-order">{{ step.order }}</span>
                    <div class="step-meta">
                      <strong>{{ step.node_label || step.node }}</strong>
                      <small>{{ thinkingStatusLabel(step.status) }} · {{ step.duration_ms }}ms</small>
                    </div>
                  </div>
                  <div class="step-summary">{{ step.summary }}</div>
                  <details v-if="step.input_data || step.output_data" class="step-detail">
                    <summary>查看输入/输出</summary>
                    <div v-if="step.input_data" class="detail-block">
                      <span>输入</span>
                      <pre>{{ JSON.stringify(step.input_data, null, 2) }}</pre>
                    </div>
                    <div v-if="step.output_data" class="detail-block">
                      <span>输出</span>
                      <pre>{{ JSON.stringify(step.output_data, null, 2) }}</pre>
                    </div>
                  </details>
                  <div v-if="step.error_message" class="step-error">{{ step.error_message }}</div>
                </div>
              </div>
            </div>
            <small>{{ msg.time }}</small>
          </div>
        </div>
      </div>

      <div class="quick-prompts">
        <button v-for="item in suggestions" :key="item" @click="sendMessage(item)">{{ item }}</button>
      </div>
      <div class="chat-input">
        <textarea
          v-model="input" rows="2"
          placeholder="描述需要协同处理的事项，例如：明天下午提醒我跟进康宁医院季度回访..."
          @keydown.enter.exact.prevent="sendMessage()"
        />
        <button @click="sendMessage()" :disabled="isTyping"><el-icon><Promotion /></el-icon></button>
        <span>Enter 发送 · Shift + Enter 换行</span>
      </div>
    </section>

    <!-- 右侧面板 -->
    <aside class="draft-column">

      <!-- 报告结果 -->
      <section class="card report-card" v-if="summaryResult">
        <div class="draft-head">
          <div><span>统计报告</span><h3>{{ summaryResult.summary_type === "weekly" ? "任务周报" : "任务日报" }}</h3></div>
          <span class="parse-ok"><el-icon><CircleCheck /></el-icon>已生成</span>
        </div>
        <div class="report-content">
          <div class="report-period">
            <span>统计区间</span><strong>{{ summaryResult.stats?.date_range }}</strong>
          </div>
          <div class="metric-grid">
            <div><span>新增</span><strong>{{ summaryResult.stats?.total_created ?? 0 }}</strong></div>
            <div><span>完成</span><strong>{{ summaryResult.stats?.total_completed ?? 0 }}</strong></div>
            <div><span>逾期</span><strong class="red-text">{{ summaryResult.stats?.total_overdue ?? 0 }}</strong></div>
            <div><span>待审</span><strong>{{ summaryResult.stats?.total_pending_review ?? 0 }}</strong></div>
          </div>
          <div class="report-narrative">{{ summaryResult.narrative }}</div>
          <div v-if="summaryResult.notification_id" class="sop-placeholder">通知记录：#{{ summaryResult.notification_id }}</div>
        </div>
      </section>

      <!-- 任务查询结果 -->
      <section class="card query-card" v-if="queryResult">
        <div class="draft-head">
          <div>
            <span>查询结果</span>
            <h3>任务列表</h3>
          </div>
          <span class="parse-ok"><el-icon><CircleCheck /></el-icon>{{ queryResult.showing }} / {{ queryResult.total }}</span>
        </div>
        <div class="query-desc">{{ queryResult.query_description }}</div>
        <div class="query-list">
          <div
            v-for="item in queryResult.tasks" :key="item.id"
            class="query-item" :class="{ 'overdue': item.is_overdue }"
          >
            <div class="qi-header">
              <span class="qi-risk" :class="`risk-${item.risk_level}`">{{ riskLabel(item.risk_level) }}</span>
              <span class="qi-id">#{{ item.id }}</span>
              <span class="qi-overdue-tag" v-if="item.is_overdue">逾期</span>
            </div>
            <div class="qi-title">{{ item.title }}</div>
            <div class="qi-meta">
              <span>{{ statusLabel(item.status) }}</span>
              <span v-if="item.due_at"> · 截止 {{ formatDue(item.due_at) }}</span>
              <span> · {{ priorityLabel(item.priority) }}优先级</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 任务草稿 -->
      <section class="card draft-card" v-if="draft">
        <div class="draft-head">
          <div><span>实时解析结果</span><h3>任务草稿</h3></div>
          <span v-if="!hasError" class="parse-ok"><el-icon><CircleCheck /></el-icon>字段校验通过</span>
          <span v-else class="parse-error"><el-icon><Warning /></el-icon>需要补充</span>
        </div>
        <div class="draft-content">
          <div class="draft-title">
            <span class="soft-chip blue">{{ typeLabel(draft.type) }}</span>
            <h4>{{ draft.title }}</h4>
            <p v-if="draft.description">{{ draft.description }}</p>
          </div>
          <div class="field-grid">
            <div v-if="draft.hospital_name || selectedHospitalName">
              <span>关联医院</span>
              <strong>{{ selectedHospitalName || draft.hospital_name }}</strong>
            </div>
            <div v-if="draft.product_name || selectedProductName">
              <span>关联产品</span>
              <strong>{{ selectedProductName || draft.product_name }}</strong>
            </div>
            <div>
              <span>责任人</span>
              <strong :class="{ 'warn-text': hasError && candidates.assignee?.length > 0 && !selectedAssigneeId }">
                {{ selectedAssigneeName || draft.assignee_name || "—" }}
              </strong>
            </div>
            <div v-if="draft.due_at"><span>截止时间</span><strong>{{ formatDue(draft.due_at) }}</strong></div>
            <div v-if="draft.priority">
              <span>优先级</span>
              <strong :class="{ 'red-text': ['urgent','high'].includes(draft.priority) }">{{ priorityLabel(draft.priority) }}</strong>
            </div>
            <div v-if="draft.risk_keywords?.length"><span>风险关键词</span><strong>{{ draft.risk_keywords.join("、") }}</strong></div>
          </div>
        </div>

        <!-- 错误恢复：候选项选择 -->
        <div v-if="hasError" class="recover-panel">
          <div class="recover-title"><el-icon><Edit /></el-icon>{{ errorMessage }}，请从候选项中选择：</div>

          <!-- 负责人候选 -->
          <div v-if="candidates.assignee?.length > 0" class="candidate-group">
            <div class="cand-label"><el-icon><UserFilled /></el-icon> 负责人候选</div>
            <div class="cand-list">
              <button
                v-for="item in candidates.assignee" :key="item.id"
                class="cand-item" :class="{ selected: selectedAssigneeId === item.id }"
                @click="pickAssignee(item)"
              >
                {{ item.name }}
                <span v-if="item.extra?.department" class="cand-extra">{{ item.extra.department }}</span>
              </button>
            </div>
            <div v-if="selectedAssigneeId" class="cand-selected">
              <el-icon><CircleCheck /></el-icon> 已选：{{ selectedAssigneeName }}
            </div>
          </div>

          <!-- 医院候选 -->
          <div v-if="candidates.hospital?.length > 0" class="candidate-group">
            <div class="cand-label"><el-icon><OfficeBuilding /></el-icon> 医院候选</div>
            <div class="cand-list">
              <button
                v-for="item in candidates.hospital" :key="item.id"
                class="cand-item" :class="{ selected: selectedHospitalId === item.id }"
                @click="pickHospital(item)"
              >{{ item.name }}</button>
            </div>
          </div>

          <!-- 无候选时提示搜索 -->
          <div v-if="!candidates.assignee?.length && !candidates.hospital?.length" class="no-cand-tip">
            <p>未找到近似匹配，请直接在对话框中修正姓名后重新描述任务。</p>
          </div>
        </div>
      </section>

      <!-- 无草稿时引导 -->
      <section class="card draft-card" v-else>
        <div class="draft-head">
          <div><span>实时解析结果</span><h3>任务草稿</h3></div>
          <span class="parse-waiting">等待输入</span>
        </div>
        <div class="draft-placeholder"><p>在左侧对话框描述任务后，<br>Agent 将自动抽取并填充此面板。</p></div>
      </section>

      <!-- 风险评估 -->
      <section class="card insight-card" v-if="riskAssessment">
        <div class="section-mini-head">
          <span><el-icon><Warning /></el-icon> 风险判断</span>
          <RiskBadge :level="riskAssessment.level" />
        </div>
        <div class="risk-reason">{{ riskAssessment.reason }}</div>
        <div v-if="riskAssessment.suggested_action" class="review-tip">
          <i></i><span>{{ riskAssessment.suggested_action }}</span>
        </div>
      </section>

      <!-- 创建结果 -->
      <section class="card insight-card" v-if="lastTask">
        <div class="section-mini-head">
          <span><el-icon><CircleCheck /></el-icon> 创建结果</span>
          <b>#{{ lastTask.id }}</b>
        </div>
        <div class="created-task">
          <strong>{{ lastTask.title }}</strong>
          <span>{{ typeLabel(lastTask.type) }} · {{ formatDateTime(lastTask.created_at) }}</span>
          <span>负责人 ID {{ lastTask.assignee_id }} · 状态 {{ lastTask.status }}</span>
        </div>
      </section>

      <!-- SOP 推荐 -->
      <section class="card insight-card" v-if="ragResult">
        <div class="section-mini-head">
          <span><el-icon><Document /></el-icon> SOP 智能推荐</span>
          <b>{{ Math.round((ragResult.confidence || 0) * 100) }}%</b>
        </div>
        <div class="sop-answer">{{ ragResult.answer }}</div>
        <div v-if="ragResult.key_steps?.length" class="sop-steps">
          <span v-for="step in ragResult.key_steps" :key="step">{{ step }}</span>
        </div>
        <div v-if="ragResult.references?.length" class="sop-placeholder">引用：{{ ragResult.references.join(" / ") }}</div>
        <div v-if="ragResult.is_gap" class="review-tip">
          <i></i><span>知识空缺已创建：#{{ ragResult.gap_task_id || "-" }}，原因：{{ ragResult.gap_reason }}</span>
        </div>
      </section>
      <section class="card insight-card" v-else-if="draft && !hasError">
        <div class="section-mini-head">
          <span><el-icon><Document /></el-icon> SOP 智能推荐</span>
          <b>等待检索</b>
        </div>
        <div class="sop-placeholder">高风险任务创建后会自动展示 RAG Agent 的 SOP 建议。</div>
      </section>

      <!-- 确认提交按钮 -->
      <template v-if="draft">
        <button
          v-if="!taskCreated"
          class="submit-draft"
          :class="{ 'submit-error': hasError }"
          :disabled="isTyping || (hasError && !candidateResolved)"
          @click="handleConfirmDraft"
        >
          <el-icon><CircleCheck /></el-icon>
          {{ hasError ? "选好候选项后重新提交" : "确认并提交任务" }}
        </button>
        <button v-else class="submit-draft created">
          <el-icon><CircleCheck /></el-icon>已进入审核队列
        </button>
      </template>
    </aside>
  </div>

  <!-- 会话历史 Drawer -->
  <el-drawer v-model="historyDrawerVisible" title="本次会话历史" size="360px" direction="rtl">
    <div v-if="historyLoading" class="history-loading">加载中…</div>
    <div v-else-if="!historyMessages.length" class="history-empty">暂无历史记录</div>
    <div v-else class="history-list">
      <div
        v-for="(msg, idx) in historyMessages" :key="idx"
        class="history-item" :class="msg.role"
      >
        <div class="history-role">{{ msg.role === "user" ? "我" : "Agent" }} · {{ msg.time }}</div>
        <div class="history-text" :class="{ 'history-error': msg.is_error }">{{ msg.text }}</div>
        <div v-if="msg.task_id" class="history-meta">任务 #{{ msg.task_id }}</div>
      </div>
    </div>
  </el-drawer>
</template>

<style scoped>
.agent-health { display: inline-flex; align-items: center; gap: 7px; padding: 8px 11px; border: 1px solid #dcefe7; border-radius: 8px; color: #438a71; font-size: 11px; background: #f7fcfa; }
.agent-health i { width: 7px; height: 7px; border-radius: 50%; background: #27b37d; }

.assistant-grid { display: grid; height: calc(100vh - 136px); min-height: 620px; grid-template-columns: 1fr 370px; gap: 15px; }

/* 左侧对话 */
.conversation { display: flex; min-width: 0; flex-direction: column; overflow: hidden; }
.chat-head { display: flex; align-items: center; gap: 10px; padding: 14px 16px; border-bottom: 1px solid #e9edf2; }
.chat-head h3 { color: #334158; font-size: 13px; }
.chat-head p { margin-top: 4px; color: #9aa4b2; font-size: 10px; }
.chat-head p i { display: inline-block; width: 6px; height: 6px; margin-right: 4px; border-radius: 50%; background: #27b37d; }
.head-actions { display: flex; gap: 6px; margin-left: auto; }
.small-btn { display: inline-flex; align-items: center; gap: 4px; padding: 5px 8px; border: 1px solid #e0e5ec; border-radius: 6px; color: #6b7a8d; font-size: 11px; background: white; cursor: pointer; }
.small-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.ai-avatar { display: grid; width: 35px; height: 35px; place-items: center; border-radius: 11px; color: #2e73e8; background: #eaf2ff; }

.chat-body { flex: 1; overflow-y: auto; padding: 14px 18px; background: #fbfcfe; }
.chat-date { width: fit-content; margin: 0 auto 14px; padding: 4px 9px; border-radius: 10px; color: #9ca7b5; font-size: 10px; background: #f0f3f7; }
.message-row { display: flex; gap: 8px; margin: 11px 0; }
.message-row.user { justify-content: end; }
.msg-avatar { display: grid; width: 27px; height: 27px; flex: none; place-items: center; border-radius: 8px; color: white; font-size: 10px; font-weight: 700; background: #3477e7; }
.msg-content { max-width: 72%; }
.message { padding: 10px 12px; border: 1px solid #e8ecf1; border-radius: 5px 11px 11px 11px; color: #59677b; font-size: 12px; line-height: 1.8; background: white; white-space: pre-wrap; }
.user .message { border: 0; border-radius: 11px 5px 11px 11px; color: white; background: #3477e7; }
.message.analysis { border-color: #ffd9bd; background: #fffaf5; }
.message.error { border-color: #fcc; background: #fff5f5; color: #c44; }
.analysis-label, .error-label { display: block; margin-bottom: 5px; font-size: 10px; font-weight: 600; }
.analysis-label { color: #d77328; }
.error-label { color: #cc4444; }
.msg-content small { display: block; margin-top: 4px; color: #adb5c0; font-size: 9px; }
.user small { text-align: right; }

.thinking-panel { margin-top: 6px; }
.thinking-panel.is-live .thinking-toggle { border-color: #b9d4ff; background: #eef5ff; }
.thinking-waiting { color: #6f86a8; font-size: 11px; line-height: 1.6; }
.thinking-pulse {
  width: 7px; height: 7px; border-radius: 50%; background: #5b8def;
  animation: thinking-pulse 1s ease-in-out infinite;
}
@keyframes thinking-pulse {
  0%, 100% { opacity: 0.35; transform: scale(0.85); }
  50% { opacity: 1; transform: scale(1); }
}
.thinking-toggle {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 8px; border: 1px solid #dbe7fb; border-radius: 7px;
  color: #4d73b8; font-size: 10px; background: #f5f9ff; cursor: pointer;
}
.thinking-steps { margin-top: 8px; padding: 10px; border: 1px solid #e7edf6; border-radius: 8px; background: #f8fbff; }
.thinking-step { position: relative; padding-left: 14px; margin-bottom: 10px; }
.thinking-step:last-child { margin-bottom: 0; }
.thinking-step::before {
  content: ""; position: absolute; left: 4px; top: 8px; bottom: -10px; width: 1px; background: #d7e3f3;
}
.thinking-step:last-child::before { display: none; }
.step-head { display: flex; align-items: center; gap: 8px; }
.step-order {
  display: grid; width: 18px; height: 18px; place-items: center;
  border-radius: 50%; color: white; font-size: 9px; background: #5b8def;
}
.thinking-step.status-error .step-order { background: #d95b5b; }
.step-meta strong { display: block; color: #3f5574; font-size: 11px; }
.step-meta small { color: #8b97a8; font-size: 9px; }
.step-summary { margin-top: 5px; color: #5d6c80; font-size: 11px; line-height: 1.6; }
.step-detail { margin-top: 6px; }
.step-detail summary { color: #6f7f95; font-size: 10px; cursor: pointer; }
.detail-block { margin-top: 6px; }
.detail-block span { display: block; margin-bottom: 3px; color: #8b97a8; font-size: 9px; }
.detail-block pre {
  margin: 0; padding: 8px; border-radius: 6px; overflow: auto;
  color: #4d5f78; font-size: 10px; line-height: 1.5; background: white;
}
.step-error { margin-top: 5px; color: #c44; font-size: 10px; }
.typing { display: flex; gap: 4px; padding: 13px; }
.typing i { width: 5px; height: 5px; border-radius: 50%; background: #a6b2c2; }

.quick-prompts { display: flex; flex-wrap: wrap; gap: 7px; padding: 8px 15px 0; border-top: 1px solid #edf0f4; }
.quick-prompts button { padding: 6px 9px; border: 1px solid #e4e9ef; border-radius: 14px; color: #7b8797; font-size: 10px; background: white; cursor: pointer; }
.chat-input { position: relative; margin: 9px 15px 13px; }
.chat-input textarea { width: 100%; resize: none; padding: 10px 46px 22px 11px; border: 1px solid #dfe5ed; border-radius: 9px; outline: 0; color: #546276; font-size: 12px; line-height: 1.6; }
.chat-input textarea:focus { border-color: #91b4f5; box-shadow: 0 0 0 3px #eff5ff; }
.chat-input button { position: absolute; right: 9px; bottom: 18px; display: grid; width: 29px; height: 29px; place-items: center; border: 0; border-radius: 7px; color: white; background: var(--primary); cursor: pointer; }
.chat-input button:disabled { opacity: .5; cursor: not-allowed; }
.chat-input span { position: absolute; bottom: 6px; left: 11px; color: #aab3bf; font-size: 9px; }

/* 右侧面板 */
.draft-column { display: grid; align-content: start; gap: 11px; overflow-y: auto; }
.draft-head { display: flex; align-items: center; justify-content: space-between; padding: 13px 14px 11px; border-bottom: 1px solid #e9edf2; }
.draft-head span { color: #99a3b1; font-size: 9px; }
.draft-head h3 { margin-top: 4px; font-size: 14px; }
.draft-head .parse-ok { display: inline-flex; align-items: center; gap: 3px; color: #2da97e; font-size: 11px; }
.draft-head .parse-error { display: inline-flex; align-items: center; gap: 3px; color: #d05c5c; font-size: 11px; }
.draft-head .parse-waiting { color: #b0bac6; font-size: 10px; }

.draft-content { padding: 12px 14px 14px; }
.draft-title h4 { margin-top: 8px; color: #3c4b60; font-size: 13px; }
.draft-title p { margin-top: 5px; color: #9fa9b6; font-size: 10px; }
.field-grid { display: grid; margin-top: 15px; grid-template-columns: 1fr 1fr; gap: 14px 12px; }
.field-grid span, .field-grid strong { display: block; }
.field-grid span { color: #9ba5b2; font-size: 10px; }
.field-grid strong { margin-top: 5px; color: #556276; font-size: 11px; font-weight: 500; }
.red-text { color: #d95252 !important; }
.warn-text { color: #d07a2a !important; }

/* 错误恢复面板 */
.recover-panel { margin: 0 14px 14px; padding: 12px; border: 1px solid #fde2c8; border-radius: 8px; background: #fffaf5; }
.recover-title { display: flex; align-items: center; gap: 5px; color: #c06020; font-size: 11px; font-weight: 600; margin-bottom: 10px; }
.candidate-group { margin-bottom: 10px; }
.cand-label { display: flex; align-items: center; gap: 4px; color: #7a8599; font-size: 10px; margin-bottom: 6px; }
.cand-list { display: flex; flex-wrap: wrap; gap: 6px; }
.cand-item { padding: 5px 10px; border: 1px solid #dce4ef; border-radius: 14px; color: #546276; font-size: 11px; background: white; cursor: pointer; transition: all .15s; }
.cand-item:hover { border-color: #3477e7; color: #3477e7; }
.cand-item.selected { border-color: #27b37d; color: #27b37d; background: #f2fbf7; font-weight: 600; }
.cand-extra { margin-left: 4px; color: #9aa4b2; font-size: 9px; }
.cand-selected { display: flex; align-items: center; gap: 4px; margin-top: 6px; color: #27b37d; font-size: 10px; }
.no-cand-tip p { color: #b0bac6; font-size: 10px; line-height: 1.6; }

/* 报告 */
.report-content { padding: 12px 14px 14px; }
.report-period span, .report-period strong { display: block; }
.report-period span { color: #9ba5b2; font-size: 10px; }
.report-period strong { margin-top: 5px; color: #46556a; font-size: 12px; }
.metric-grid { display: grid; margin-top: 12px; grid-template-columns: repeat(4, 1fr); gap: 7px; }
.metric-grid div { padding: 8px 6px; border: 1px solid #e8edf4; border-radius: 7px; background: #fbfcfe; }
.metric-grid span, .metric-grid strong { display: block; text-align: center; }
.metric-grid span { color: #9aa5b2; font-size: 9px; }
.metric-grid strong { margin-top: 4px; color: #3f4e63; font-size: 15px; }
.report-narrative { margin-top: 12px; color: #5c697b; font-size: 11px; line-height: 1.75; white-space: pre-wrap; }

/* 空状态 */
.draft-placeholder { display: flex; align-items: center; justify-content: center; height: 100px; color: #b0bac6; font-size: 11px; text-align: center; line-height: 1.8; padding: 14px; }

/* 洞察卡片 */
.insight-card { padding: 13px 14px; }
.section-mini-head { display: flex; align-items: center; justify-content: space-between; }
.section-mini-head span { display: inline-flex; align-items: center; gap: 5px; color: #5e6b7d; font-size: 11px; font-weight: 600; }
.section-mini-head b { color: #2fa77c; font-size: 10px; }
.risk-reason { margin-top: 10px; color: #7a5960; font-size: 11px; line-height: 1.7; }
.review-tip { display: flex; gap: 7px; margin-top: 9px; padding: 8px; border-radius: 6px; background: #fff5e9; }
.review-tip i { width: 6px; height: 6px; flex: none; margin-top: 5px; border-radius: 50%; background: #e69942; }
.review-tip span { color: #b3722f; font-size: 10px; line-height: 1.6; }
.created-task { display: grid; gap: 5px; margin-top: 10px; }
.created-task strong { color: #46556a; font-size: 12px; }
.created-task span { color: #8f9baa; font-size: 10px; }
.sop-answer { margin-top: 10px; color: #5d6b7d; font-size: 11px; line-height: 1.7; }
.sop-steps { display: grid; gap: 5px; margin-top: 9px; }
.sop-steps span { padding: 6px 8px; border-radius: 6px; color: #4f6d98; font-size: 10px; background: #f3f7ff; }
.sop-placeholder { margin-top: 9px; color: #aab3bf; font-size: 10px; }

/* 提交按钮 */
.submit-draft { display: flex; width: 100%; align-items: center; justify-content: center; gap: 5px; padding: 11px; border: 0; border-radius: 8px; color: white; font-size: 12px; background: var(--primary); box-shadow: 0 5px 14px rgba(36,107,254,.2); cursor: pointer; }
.submit-draft.created { background: #28a779; }
.submit-draft.submit-error { background: #e8863a; box-shadow: 0 5px 14px rgba(200,100,30,.2); }
.submit-draft:disabled { opacity: .5; cursor: not-allowed; }

/* 历史 Drawer */
.history-loading, .history-empty { padding: 20px; color: #b0bac6; font-size: 12px; text-align: center; }
.history-list { display: grid; gap: 12px; padding: 4px 0; }
.history-item { padding: 10px 12px; border-radius: 8px; background: #f8fafb; }
.history-item.user { background: #eef4ff; }
.history-role { color: #9aa4b2; font-size: 10px; margin-bottom: 4px; }
.history-text { color: #546276; font-size: 11px; line-height: 1.7; white-space: pre-wrap; }
.history-text.history-error { color: #cc4444; }
.history-meta { margin-top: 4px; color: #27b37d; font-size: 10px; }

/* 查询结果 */
.query-desc { padding: 8px 14px; color: #7a8899; font-size: 10px; border-bottom: 1px solid #edf0f4; }
.query-list { padding: 8px 10px 10px; display: grid; gap: 7px; }
.query-item { padding: 9px 11px; border: 1px solid #e8edf4; border-radius: 8px; background: white; }
.query-item.overdue { border-color: #fcd6c3; background: #fffaf8; }
.qi-header { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; }
.qi-risk { padding: 2px 6px; border-radius: 4px; font-size: 9px; font-weight: 600; }
.qi-risk.risk-low { color: #2e8b5a; background: #e8f7ef; }
.qi-risk.risk-medium { color: #8c6a18; background: #fff8e0; }
.qi-risk.risk-high { color: #c04020; background: #fef0ec; }
.qi-risk.risk-critical { color: white; background: #c02020; }
.qi-id { color: #b0bac6; font-size: 9px; }
.qi-overdue-tag { margin-left: auto; padding: 1px 5px; border-radius: 3px; color: #c04020; font-size: 9px; background: #fde8e0; font-weight: 600; }
.qi-title { color: #3c4b60; font-size: 12px; font-weight: 500; line-height: 1.4; }
.qi-meta { margin-top: 4px; color: #9aa4b2; font-size: 10px; }
</style>
