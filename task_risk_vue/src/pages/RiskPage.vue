<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Check, Clock, Close, Edit, Plus, Search, Tickets, Warning,
} from "@element-plus/icons-vue";
import PageHeader from "../components/PageHeader.vue";
import RiskBadge from "../components/RiskBadge.vue";
import { getPendingReviewTasks, getTaskById, reviewTask } from "../api/tasks.js";
import {
  createRiskRule, deleteRiskRule, getRiskRules, getRiskStats,
  getRiskTickets, getTaskRiskRecords, updateRiskRule,
} from "../api/risk.js";
import { currentUserId } from "../store/app.js";
import { formatDateTime, RISK_OPTIONS, riskLabel, typeLabel } from "../utils/mappers.js";

// ── 统计指标 ──────────────────────────────────────────────────────────────────
const stats = ref({ pending_count: 0, critical_count: 0, escalated_count: 0, high_count: 0, approved_today: 0 });

async function loadStats() {
  try {
    const data = await getRiskStats();
    stats.value = data;
  } catch { /* silent */ }
}

// ── 标签页 ────────────────────────────────────────────────────────────────────
const activeTab = ref("待审核");
const search = ref("");

// ── 待审核 ────────────────────────────────────────────────────────────────────
const pendingList = ref([]);
const pendingTotal = ref(0);
const pendingPage = ref(1);
const pendingLoading = ref(false);

async function loadPending() {
  pendingLoading.value = true;
  try {
    const data = await getPendingReviewTasks({ page: pendingPage.value, page_size: 20 });
    pendingList.value = data.items || [];
    pendingTotal.value = data.total;
  } catch (e) {
    ElMessage.error(e.message || "加载待审核任务失败");
  } finally {
    pendingLoading.value = false;
  }
}

const filteredPending = computed(() => {
  if (!search.value) return pendingList.value;
  const q = search.value.toLowerCase();
  return pendingList.value.filter((t) => `${t.title}${t.id}`.toLowerCase().includes(q));
});

// ── 风险工单 ──────────────────────────────────────────────────────────────────
const ticketList = ref([]);
const ticketTotal = ref(0);
const ticketPage = ref(1);
const ticketLoading = ref(false);

async function loadTickets() {
  ticketLoading.value = true;
  try {
    const data = await getRiskTickets({ page: ticketPage.value, page_size: 20 });
    ticketList.value = data.items || [];
    ticketTotal.value = data.total;
  } catch (e) {
    ElMessage.error(e.message || "加载风险工单失败");
  } finally {
    ticketLoading.value = false;
  }
}

const filteredTickets = computed(() => {
  if (!search.value) return ticketList.value;
  const q = search.value.toLowerCase();
  return ticketList.value.filter((t) => `${t.title}${t.id}`.toLowerCase().includes(q));
});

// ── 任务详情+风险记录 ──────────────────────────────────────────────────────────
const detailOpen = ref(false);
const detailLoading = ref(false);
const actionLoading = ref(false);
const selectedTask = ref(null);
const taskRiskRecords = ref([]);
const riskRecordsLoading = ref(false);

async function openDetail(taskItem) {
  detailOpen.value = true;
  detailLoading.value = true;
  selectedTask.value = taskItem;
  try {
    const detail = await getTaskById(taskItem.id);
    selectedTask.value = detail;
    await loadTaskRiskRecords(taskItem.id);
  } catch {
    // 保留列表行数据
  } finally {
    detailLoading.value = false;
  }
}

async function loadTaskRiskRecords(taskId) {
  riskRecordsLoading.value = true;
  try {
    const data = await getTaskRiskRecords(taskId);
    taskRiskRecords.value = (data.items || []).reverse();
  } catch {
    taskRiskRecords.value = [];
  } finally {
    riskRecordsLoading.value = false;
  }
}

// 最新一条风险记录（用于详情展示）
const latestRecord = computed(() => taskRiskRecords.value[0] || null);

async function handleReviewAction(actionType) {
  const actionMap = { approve: "approved", reject: "rejected", escalate: "escalated" };
  const labelMap = { approve: "通过", reject: "驳回", escalate: "升级为工单" };
  const label = labelMap[actionType];

  try {
    const { value: comment } = await ElMessageBox.prompt(
      `确认将此风险事项「${label}」吗？`,
      `风险审核 — ${label}`,
      { confirmButtonText: "确认", cancelButtonText: "取消", inputPlaceholder: "审核备注（可选）" }
    );
    actionLoading.value = true;
    await reviewTask(selectedTask.value.id, {
      action: actionMap[actionType],
      reviewer_id: currentUserId.value,
      comment: comment || undefined,
    });
    ElMessage.success(`已${label}`);
    detailOpen.value = false;
    await loadStats();
    await loadPending();
    await loadTickets();
  } catch (e) {
    if (e !== "cancel" && e?.message) ElMessage.error(e.message);
  } finally {
    actionLoading.value = false;
  }
}

// ── 风险规则管理 ───────────────────────────────────────────────────────────────
const ruleList = ref([]);
const ruleLoading = ref(false);
const ruleDialogOpen = ref(false);
const ruleDialogTitle = ref("新增规则");
const editingRuleId = ref(null);

const RULE_TYPE_OPTIONS = [
  { value: "keyword", label: "关键词规则" },
  { value: "type_baseline", label: "任务类型基线" },
  { value: "composite", label: "复合规则" },
];

const BASELINE_OPTIONS = [
  { value: "low", label: "低风险" },
  { value: "medium", label: "中风险" },
  { value: "high", label: "高风险" },
  { value: "critical", label: "紧急风险" },
];

const ruleForm = ref({
  name: "",
  description: "",
  rule_type: "keyword",
  keywords: "",
  task_types: "",
  baseline_level: "medium",
  is_active: true,
});

async function loadRules() {
  ruleLoading.value = true;
  try {
    const data = await getRiskRules({ include_inactive: true });
    ruleList.value = data.items || [];
  } catch (e) {
    ElMessage.error(e.message || "加载规则失败");
  } finally {
    ruleLoading.value = false;
  }
}

function openCreateRule() {
  ruleDialogTitle.value = "新增风险规则";
  editingRuleId.value = null;
  ruleForm.value = { name: "", description: "", rule_type: "keyword", keywords: "", task_types: "", baseline_level: "medium", is_active: true };
  ruleDialogOpen.value = true;
}

function openEditRule(rule) {
  ruleDialogTitle.value = "编辑风险规则";
  editingRuleId.value = rule.id;
  ruleForm.value = {
    name: rule.name,
    description: rule.description || "",
    rule_type: rule.rule_type,
    keywords: (rule.keywords || []).join("，"),
    task_types: (rule.task_types || []).join("，"),
    baseline_level: rule.baseline_level,
    is_active: rule.is_active,
  };
  ruleDialogOpen.value = true;
}

function parseCommaList(str) {
  return str.split(/[，,\s]+/).map((s) => s.trim()).filter(Boolean);
}

async function handleSaveRule() {
  if (!ruleForm.value.name.trim()) { ElMessage.warning("规则名称不能为空"); return; }
  const body = {
    name: ruleForm.value.name.trim(),
    description: ruleForm.value.description.trim() || undefined,
    rule_type: ruleForm.value.rule_type,
    keywords: parseCommaList(ruleForm.value.keywords),
    task_types: parseCommaList(ruleForm.value.task_types),
    baseline_level: ruleForm.value.baseline_level,
    is_active: ruleForm.value.is_active,
  };
  try {
    if (editingRuleId.value) {
      await updateRiskRule(editingRuleId.value, body);
      ElMessage.success("规则已更新");
    } else {
      await createRiskRule(body);
      ElMessage.success("规则已创建");
    }
    ruleDialogOpen.value = false;
    await loadRules();
  } catch (e) {
    ElMessage.error(e.message || "操作失败");
  }
}

async function handleToggleActive(rule) {
  try {
    await updateRiskRule(rule.id, { is_active: !rule.is_active });
    rule.is_active = !rule.is_active;
    ElMessage.success(rule.is_active ? "规则已启用" : "规则已停用");
  } catch (e) {
    ElMessage.error(e.message || "操作失败");
  }
}

async function handleDeleteRule(rule) {
  try {
    await ElMessageBox.confirm(`确认删除规则「${rule.name}」吗？`, "删除规则", { type: "warning" });
    await deleteRiskRule(rule.id);
    ElMessage.success("已删除");
    await loadRules();
  } catch (e) {
    if (e !== "cancel" && e?.message) ElMessage.error(e.message);
  }
}

// ── 初始化 ────────────────────────────────────────────────────────────────────
function loadCurrentTab() {
  if (activeTab.value === "待审核") loadPending();
  else if (activeTab.value === "风险工单") loadTickets();
  else if (activeTab.value === "规则配置") loadRules();
}

watch(activeTab, () => {
  search.value = "";
  loadCurrentTab();
});

onMounted(async () => {
  await loadStats();
  await loadPending();
});
</script>

<template>
  <PageHeader title="风险中心" desc="集中审核高风险事项，及时升级患者安全、设备异常与合规风险。" eyebrow="RISK CONTROL">
    <button class="secondary-btn"><el-icon><Tickets /></el-icon>导出风险台账</button>
  </PageHeader>

  <!-- 指标卡 -->
  <div class="risk-metrics">
    <div class="metric-card">
      <span class="metric-icon orange"><el-icon><Clock /></el-icon></span>
      <div><strong>{{ stats.pending_count }}</strong><small>待审核事项</small></div>
    </div>
    <div class="metric-card">
      <span class="metric-icon red"><el-icon><Warning /></el-icon></span>
      <div><strong>{{ stats.critical_count }}</strong><small>紧急风险</small></div>
    </div>
    <div class="metric-card">
      <span class="metric-icon purple"><el-icon><Tickets /></el-icon></span>
      <div><strong>{{ stats.escalated_count }}</strong><small>升级中工单</small></div>
    </div>
    <div class="metric-card">
      <span class="metric-icon green"><el-icon><Check /></el-icon></span>
      <div><strong>{{ stats.approved_today }}</strong><small>今日已审核通过</small></div>
    </div>
  </div>

  <section class="card">
    <!-- 标签页 -->
    <div class="tab-bar">
      <button
        v-for="tab in ['待审核','风险工单','规则配置']"
        :key="tab"
        class="tab-button"
        :class="{ active: activeTab === tab }"
        @click="activeTab = tab"
      >
        {{ tab }}
        <b v-if="tab === '待审核' && stats.pending_count > 0" class="tab-badge">{{ stats.pending_count }}</b>
        <b v-else-if="tab === '风险工单' && stats.escalated_count > 0" class="tab-badge">{{ stats.escalated_count }}</b>
      </button>
    </div>

    <!-- 工具栏（规则配置 tab 有独立操作区） -->
    <div v-if="activeTab !== '规则配置'" class="toolbar">
      <el-input v-model="search" :prefix-icon="Search" placeholder="搜索风险标题或编号" clearable style="width:220px" />
      <span class="toolbar-spacer"></span>
      <span class="risk-rule-tag"><i></i> Risk Agent 规则库已更新</span>
    </div>

    <!-- ── 待审核 ─────────────────────────────────────────── -->
    <template v-if="activeTab === '待审核'">
      <table class="list-table" v-loading="pendingLoading">
        <thead>
          <tr>
            <th>风险事项</th><th>类型</th><th>风险等级</th>
            <th>负责人</th><th>创建时间</th><th>审核状态</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="task in filteredPending" :key="task.id">
            <td>
              <strong class="table-title">{{ task.title }}</strong>
              <span class="table-sub">#{{ task.id }}</span>
            </td>
            <td><span class="source-chip">{{ typeLabel(task.type) }}</span></td>
            <td><RiskBadge :level="task.risk_level" compact /></td>
            <td>用户 #{{ task.assignee_id }}</td>
            <td>{{ formatDateTime(task.created_at) }}</td>
            <td><span class="status-dot waiting">待审核</span></td>
            <td>
              <button class="ghost-btn" @click="openDetail(task)">审核详情</button>
            </td>
          </tr>
          <tr v-if="!filteredPending.length && !pendingLoading">
            <td colspan="7" class="empty-row">暂无待审核风险事项</td>
          </tr>
        </tbody>
      </table>
      <div class="pagination-row">
        <span>共 {{ pendingTotal }} 条</span>
        <el-pagination small background layout="prev, pager, next"
          :total="pendingTotal" :page-size="20" :current-page="pendingPage"
          @current-change="(p) => { pendingPage = p; loadPending(); }"
        />
      </div>
    </template>

    <!-- ── 风险工单 ─────────────────────────────────────────── -->
    <template v-else-if="activeTab === '风险工单'">
      <table class="list-table" v-loading="ticketLoading">
        <thead>
          <tr>
            <th>工单标题</th><th>类型</th><th>风险等级</th>
            <th>负责人</th><th>创建时间</th><th>审核人</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="ticket in filteredTickets" :key="ticket.id">
            <td>
              <strong class="table-title">{{ ticket.title }}</strong>
              <span class="table-sub">#{{ ticket.id }}</span>
            </td>
            <td><span class="source-chip">{{ typeLabel(ticket.type) }}</span></td>
            <td><RiskBadge :level="ticket.risk_level" compact /></td>
            <td>用户 #{{ ticket.assignee_id }}</td>
            <td>{{ formatDateTime(ticket.created_at) }}</td>
            <td>{{ ticket.reviewer_id ? `用户 #${ticket.reviewer_id}` : '-' }}</td>
            <td>
              <button class="ghost-btn" @click="openDetail(ticket)">查看详情</button>
            </td>
          </tr>
          <tr v-if="!filteredTickets.length && !ticketLoading">
            <td colspan="7" class="empty-row">暂无升级工单</td>
          </tr>
        </tbody>
      </table>
      <div class="pagination-row">
        <span>共 {{ ticketTotal }} 条工单</span>
        <el-pagination small background layout="prev, pager, next"
          :total="ticketTotal" :page-size="20" :current-page="ticketPage"
          @current-change="(p) => { ticketPage = p; loadTickets(); }"
        />
      </div>
    </template>

    <!-- ── 规则配置 ─────────────────────────────────────────── -->
    <template v-else-if="activeTab === '规则配置'">
      <div class="rule-toolbar">
        <span class="rule-count">共 {{ ruleList.length }} 条规则</span>
        <span class="toolbar-spacer"></span>
        <button class="primary-btn" @click="openCreateRule">
          <el-icon><Plus /></el-icon>新增规则
        </button>
      </div>
      <table class="list-table" v-loading="ruleLoading">
        <thead>
          <tr>
            <th>规则名称</th><th>类型</th><th>触发关键词</th>
            <th>适用任务类型</th><th>基线等级</th><th>状态</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="rule in ruleList" :key="rule.id" :class="{ 'row-inactive': !rule.is_active }">
            <td>
              <strong>{{ rule.name }}</strong>
              <span v-if="rule.description" class="table-sub">{{ rule.description }}</span>
            </td>
            <td>
              <span class="source-chip">
                {{ rule.rule_type === 'keyword' ? '关键词' : rule.rule_type === 'type_baseline' ? '类型基线' : '复合' }}
              </span>
            </td>
            <td>
              <div class="keyword-tags">
                <span v-for="kw in (rule.keywords || []).slice(0, 4)" :key="kw" class="kw-tag">{{ kw }}</span>
                <span v-if="(rule.keywords || []).length > 4" class="kw-more">+{{ rule.keywords.length - 4 }}</span>
              </div>
            </td>
            <td>
              <span v-if="!(rule.task_types || []).length" class="text-muted">全部类型</span>
              <span v-else>{{ rule.task_types.join('、') }}</span>
            </td>
            <td><RiskBadge :level="rule.baseline_level" compact /></td>
            <td>
              <el-switch
                :model-value="rule.is_active"
                @change="handleToggleActive(rule)"
                active-color="#2868da"
                size="small"
              />
            </td>
            <td>
              <button class="ghost-btn" @click="openEditRule(rule)"><el-icon><Edit /></el-icon>编辑</button>
              <button class="ghost-btn danger-btn" @click="handleDeleteRule(rule)"><el-icon><Close /></el-icon>删除</button>
            </td>
          </tr>
          <tr v-if="!ruleList.length && !ruleLoading">
            <td colspan="7" class="empty-row">暂无风险规则</td>
          </tr>
        </tbody>
      </table>
    </template>
  </section>

  <!-- ── 审核详情抽屉 ────────────────────────────────────────────── -->
  <el-drawer v-model="detailOpen" size="520px">
    <template v-if="selectedTask" #header>
      <div class="drawer-title">
        <h3>{{ selectedTask.title }}</h3>
        <p>#{{ selectedTask.id }} · {{ typeLabel(selectedTask.type) }}</p>
      </div>
    </template>

    <div v-if="detailLoading" class="drawer-loading"><el-skeleton :rows="8" animated /></div>

    <template v-else-if="selectedTask">
      <!-- 风险等级横幅 -->
      <div class="risk-banner" :class="selectedTask.risk_level">
        <RiskBadge :level="selectedTask.risk_level" />
        <span class="banner-text">{{ riskLabel(selectedTask.risk_level) }}</span>
        <span class="banner-time">{{ formatDateTime(selectedTask.created_at) }}</span>
      </div>

      <!-- 风险判断依据（来自最新风险记录） -->
      <div class="detail-section">
        <h4>风险判断依据</h4>
        <div v-if="latestRecord" class="note-box danger">
          {{ latestRecord.reason || selectedTask.risk_reason || '（暂无风险原因）' }}
        </div>
        <div v-else class="note-box danger">{{ selectedTask.risk_reason || '（暂无风险原因）' }}</div>
      </div>

      <!-- 命中关键词与规则 -->
      <div v-if="latestRecord" class="detail-section">
        <h4>命中关键词 & 规则</h4>
        <div class="keyword-row">
          <span class="kw-label">关键词</span>
          <template v-if="(latestRecord.keywords_hit || []).length">
            <span v-for="kw in latestRecord.keywords_hit" :key="kw" class="kw-tag danger">{{ kw }}</span>
          </template>
          <span v-else class="text-muted">无</span>
        </div>
        <div class="keyword-row" style="margin-top:8px">
          <span class="kw-label">规则</span>
          <template v-if="(latestRecord.rule_hit || []).length">
            <span v-for="r in latestRecord.rule_hit" :key="r" class="kw-tag">{{ r }}</span>
          </template>
          <span v-else class="text-muted">无</span>
        </div>
      </div>

      <!-- Agent 建议 -->
      <div class="detail-section">
        <h4>Agent 建议处理动作</h4>
        <div class="note-box warning">
          {{ (latestRecord && latestRecord.suggested_action) || selectedTask.risk_suggested_action || '请结合任务详情人工判断处理动作。' }}
        </div>
      </div>

      <!-- 历史风险评估记录 -->
      <div class="detail-section" v-loading="riskRecordsLoading">
        <h4>风险评估历史（共 {{ taskRiskRecords.length }} 次）</h4>
        <div v-if="!taskRiskRecords.length" class="tab-empty">暂无历史记录</div>
        <div v-else class="history-list">
          <div v-for="rec in taskRiskRecords" :key="rec.id" class="history-item">
            <div class="history-header">
              <RiskBadge :level="rec.risk_level" compact />
              <span class="history-status">{{ rec.review_status }}</span>
              <span class="history-time">{{ formatDateTime(rec.created_at) }}</span>
            </div>
            <p v-if="rec.reason" class="history-reason">{{ rec.reason }}</p>
          </div>
        </div>
      </div>

      <!-- LLM 原始判断（折叠展示） -->
      <div v-if="latestRecord && latestRecord.llm_judgement" class="detail-section">
        <h4>LLM 判断原文</h4>
        <div class="llm-box">
          <div class="llm-row"><span>置信度</span><b>{{ (latestRecord.llm_judgement.confidence * 100).toFixed(0) }}%</b></div>
          <div class="llm-row"><span>LLM 等级</span><b>{{ latestRecord.llm_judgement.level }}</b></div>
          <div v-if="(latestRecord.llm_judgement.signals || []).length" class="llm-row">
            <span>信号</span>
            <b>{{ latestRecord.llm_judgement.signals.join(' · ') }}</b>
          </div>
        </div>
      </div>

      <!-- 审核操作 -->
      <div
        v-if="selectedTask.review_status === 'pending'"
        class="drawer-footer risk-actions"
        v-loading="actionLoading"
      >
        <button class="secondary-btn danger-btn" @click="handleReviewAction('reject')">驳回</button>
        <button class="secondary-btn" @click="handleReviewAction('escalate')">
          <el-icon><Plus /></el-icon>升级工单
        </button>
        <button class="primary-btn" @click="handleReviewAction('approve')">
          <el-icon><Check /></el-icon>审核通过
        </button>
      </div>
      <div v-else class="drawer-footer">
        <span class="reviewed-tip">已审核：{{ selectedTask.review_status }} · {{ formatDateTime(selectedTask.reviewed_at) }}</span>
      </div>
    </template>
  </el-drawer>

  <!-- ── 规则新增/编辑弹窗 ──────────────────────────────────────── -->
  <el-dialog v-model="ruleDialogOpen" :title="ruleDialogTitle" width="540px">
    <el-form label-position="top" class="rule-form">
      <el-form-item label="规则名称 *">
        <el-input v-model="ruleForm.name" placeholder="如：患者安全关键词" />
      </el-form-item>
      <el-form-item label="规则类型">
        <el-select v-model="ruleForm.rule_type" style="width:100%">
          <el-option v-for="opt in RULE_TYPE_OPTIONS" :key="opt.value" :value="opt.value" :label="opt.label" />
        </el-select>
      </el-form-item>
      <el-form-item label="触发关键词（逗号或顿号分隔）">
        <el-input v-model="ruleForm.keywords" type="textarea" :rows="2" placeholder="如：死亡，感染，输液反应" />
      </el-form-item>
      <el-form-item label="适用任务类型（逗号分隔，空则全部）">
        <el-input v-model="ruleForm.task_types" placeholder="如：adverse_event，device_anomaly" />
      </el-form-item>
      <el-form-item label="命中后基线风险等级">
        <el-select v-model="ruleForm.baseline_level" style="width:100%">
          <el-option v-for="opt in BASELINE_OPTIONS" :key="opt.value" :value="opt.value" :label="opt.label" />
        </el-select>
      </el-form-item>
      <el-form-item label="规则说明">
        <el-input v-model="ruleForm.description" type="textarea" :rows="2" placeholder="规则作用说明（可选）" />
      </el-form-item>
      <el-form-item label="是否启用">
        <el-switch v-model="ruleForm.is_active" active-color="#2868da" />
      </el-form-item>
    </el-form>
    <template #footer>
      <button class="secondary-btn" @click="ruleDialogOpen = false">取消</button>
      <button class="primary-btn" @click="handleSaveRule">保存</button>
    </template>
  </el-dialog>
</template>

<style scoped>
/* ── 指标卡 ─────────────────────────────────────────────────────── */
.risk-metrics { display: grid; margin-bottom: 14px; grid-template-columns: repeat(4,1fr); gap: 12px; }
.metric-card { display: flex; align-items: center; gap: 11px; padding: 13px 15px; border: 1px solid #ebeff4; border-radius: 11px; background: white; box-shadow: var(--shadow, 0 2px 8px rgba(0,0,0,.04)); }
.metric-card strong { display: block; color: #334158; font-size: 22px; line-height: 1.2; }
.metric-card small { display: block; margin-top: 2px; color: #8995a5; font-size: 10px; }
.metric-icon { display: grid; width: 38px; height: 38px; place-items: center; border-radius: 9px; flex-shrink: 0; }
.metric-icon.orange { color: #df842e; background: #fff4e9; }
.metric-icon.red { color: #db5757; background: #fff0f0; }
.metric-icon.purple { color: #722ed1; background: #f9f0ff; }
.metric-icon.green { color: #2aa479; background: #eaf8f3; }
/* ── 标签页 ─────────────────────────────────────────────────────── */
.tab-badge { display: inline-flex; align-items: center; justify-content: center; min-width: 17px; height: 17px; padding: 0 4px; margin-left: 5px; border-radius: 8px; background: #ff4d4f; color: white; font-size: 10px; }
/* ── 规则工具栏 ─────────────────────────────────────────────────── */
.rule-toolbar { display: flex; align-items: center; padding: 10px 15px; border-bottom: 1px solid #edf0f4; }
.rule-count { font-size: 12px; color: #7a8798; }
/* ── 关键词标签 ─────────────────────────────────────────────────── */
.keyword-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.kw-tag { padding: 1px 6px; border-radius: 3px; font-size: 11px; background: #eef1f4; color: #4a586c; }
.kw-tag.danger { background: #fff1f0; color: #f5222d; }
.kw-more { font-size: 10px; color: #8490a0; }
.kw-label { font-size: 11px; color: #8490a0; margin-right: 6px; min-width: 40px; }
.keyword-row { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.text-muted { color: #aab3bf; font-size: 11px; }
.row-inactive td { opacity: 0.5; }
/* ── 详情抽屉 ───────────────────────────────────────────────────── */
.risk-banner { display: flex; align-items: center; gap: 10px; padding: 11px 12px; border-radius: 8px; margin-bottom: 14px; }
.risk-banner.low { background: #f0fff4; }
.risk-banner.medium { background: #fffbe6; }
.risk-banner.high { background: #fff7e6; }
.risk-banner.critical { background: #fff1f0; }
.banner-text { font-size: 12px; font-weight: 600; color: #4a586c; }
.banner-time { margin-left: auto; font-size: 11px; color: #aab3bf; }
.drawer-loading { padding: 20px; }
.detail-section { padding: 12px 0; border-bottom: 1px solid #edf0f4; }
.detail-section:last-of-type { border-bottom: 0; }
.detail-section h4 { margin: 0 0 10px; font-size: 12px; color: #5a6475; font-weight: 600; }
.note-box.danger { background: #fff5f5; border-left: 3px solid #f5222d; }
.note-box.warning { background: #fffbe6; border-left: 3px solid #faad14; }
/* ── 历史记录 ───────────────────────────────────────────────────── */
.history-list { display: flex; flex-direction: column; gap: 8px; }
.history-item { padding: 8px 10px; background: #f8fafc; border-radius: 6px; border: 1px solid #edf0f4; }
.history-header { display: flex; align-items: center; gap: 8px; }
.history-status { font-size: 11px; color: #8490a0; }
.history-time { margin-left: auto; font-size: 10px; color: #aab3bf; }
.history-reason { margin: 6px 0 0; font-size: 11px; color: #4a586c; line-height: 1.5; }
/* ── LLM 判断 ───────────────────────────────────────────────────── */
.llm-box { background: #f8fafc; border-radius: 6px; padding: 10px 12px; border: 1px solid #edf0f4; }
.llm-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 11px; color: #7a8798; border-top: 1px solid #f0f2f5; }
.llm-row:first-child { border-top: 0; }
.llm-row b { color: #4a586c; }
/* ── 审核操作区 ─────────────────────────────────────────────────── */
.risk-actions { display: flex; justify-content: flex-end; gap: 10px; padding: 14px 0 4px; }
.reviewed-tip { font-size: 11px; color: #8490a0; padding: 14px 0 4px; display: block; }
.tab-empty { padding: 24px; color: #aab3bf; text-align: center; font-size: 12px; }
.empty-row { padding: 32px; color: #aab3bf; text-align: center; font-size: 12px; }
/* ── 规则表单 ───────────────────────────────────────────────────── */
.rule-form { padding: 4px 0; }
/* ── 工具栏规则标签 ─────────────────────────────────────────────── */
.risk-rule-tag { display: flex; align-items: center; gap: 6px; color: #8a96a5; font-size: 10px; }
.risk-rule-tag i { width: 7px; height: 7px; border-radius: 50%; background: #2db17e; display: inline-block; }
</style>
