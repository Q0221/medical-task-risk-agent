<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Check, Close, Connection, Clock, Document, Edit, Key,
  Plus, Search, Setting, Tools, UserFilled, View,
} from "@element-plus/icons-vue";
import PageHeader from "../components/PageHeader.vue";
import RiskBadge from "../components/RiskBadge.vue";
import { getAgentTraces } from "../api/traces.js";
import { getHealth, getReady } from "../api/health.js";
import {
  createDictItem, deleteDictItem, getAdminUsers, getDictItems,
  getNotifyChannels, testNotifyChannel, updateAdminUser, updateDictItem,
  updateNotifyChannel,
} from "../api/admin.js";
import {
  createRiskRule, deleteRiskRule, getRiskRules, updateRiskRule,
} from "../api/risk.js";
import { formatDateTime, traceNodeLabel } from "../utils/mappers.js";

// ── 标签页 ─────────────────────────────────────────────────────────────────────
const tab = ref("Agent Trace");

// ── 系统状态 ──────────────────────────────────────────────────────────────────
const health = ref(null);
const ready = ref(null);

async function checkSystem() {
  try {
    const [h, r] = await Promise.all([getHealth(), getReady()]);
    health.value = h;
    ready.value = r;
    ElMessage.success(`服务正常：MySQL=${r.mysql ? "ok" : "fail"}，Redis=${r.redis ? "ok" : "fail"}`);
  } catch (e) {
    ElMessage.error(e.message || "系统状态检查失败");
  }
}

// ── Agent Trace ───────────────────────────────────────────────────────────────
const traces = ref([]);
const traceTotal = ref(0);
const tracePage = ref(1);
const tracePageSize = ref(20);
const traceLoading = ref(false);
const traceQuery = ref("");
const traceNodeFilter = ref("");
const traceSelected = ref(null);
const traceDetailOpen = ref(false);

const okCount = computed(() => traces.value.filter((t) => t.status === "ok").length);
const avgDuration = computed(() => {
  if (!traces.value.length) return "0ms";
  const avg = traces.value.reduce((s, t) => s + (t.duration_ms || 0), 0) / traces.value.length;
  return `${Math.round(avg)}ms`;
});

async function loadTraces() {
  traceLoading.value = true;
  try {
    const params = { page: tracePage.value, page_size: tracePageSize.value };
    if (traceNodeFilter.value) params.node = traceNodeFilter.value;
    if (traceQuery.value.trim()) params.trace_id = traceQuery.value.trim();
    const data = await getAgentTraces(params);
    traces.value = data.items;
    traceTotal.value = data.total;
    if (!traceSelected.value && data.items.length) traceSelected.value = data.items[0];
  } catch (e) {
    ElMessage.error(e.message || "Trace 加载失败");
  } finally {
    traceLoading.value = false;
  }
}

// ── 工具日志 ───────────────────────────────────────────────────────────────────
const toolLogs = ref([]);
const toolTotal = ref(0);
const toolPage = ref(1);
const toolLoading = ref(false);
const toolSelected = ref(null);
const toolDetailOpen = ref(false);

async function loadToolLogs() {
  toolLoading.value = true;
  try {
    const data = await getAgentTraces({ page: toolPage.value, page_size: 20, node: "tool_call" });
    toolLogs.value = data.items;
    toolTotal.value = data.total;
  } catch (e) {
    ElMessage.error(e.message || "工具日志加载失败");
  } finally {
    toolLoading.value = false;
  }
}

// ── 风险规则（复用 risk.js）────────────────────────────────────────────────────
const ruleList = ref([]);
const ruleLoading = ref(false);
const ruleDialogOpen = ref(false);
const editingRuleId = ref(null);
const ruleDialogTitle = ref("新增规则");

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
  name: "", description: "", rule_type: "keyword",
  keywords: "", task_types: "", baseline_level: "medium", is_active: true,
});

async function loadRules() {
  ruleLoading.value = true;
  try {
    const data = await getRiskRules({ include_inactive: true });
    ruleList.value = data.items || [];
  } catch (e) {
    ElMessage.error(e.message || "规则加载失败");
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

async function handleToggleRule(rule) {
  try {
    await updateRiskRule(rule.id, { is_active: !rule.is_active });
    rule.is_active = !rule.is_active;
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

// ── 通知渠道配置 ───────────────────────────────────────────────────────────────
const channels = ref([]);
const channelLoading = ref(false);
const channelSaving = ref({});
const channelTesting = ref({});
const channelForms = ref({});

async function loadChannels() {
  channelLoading.value = true;
  try {
    const data = await getNotifyChannels();
    channels.value = data;
    data.forEach((ch) => {
      channelForms.value[ch.config_key] = {
        ...ch.config_value,
        is_active: ch.is_active,
      };
    });
  } catch (e) {
    ElMessage.error(e.message || "加载渠道配置失败");
  } finally {
    channelLoading.value = false;
  }
}

async function handleSaveChannel(ch) {
  const form = channelForms.value[ch.config_key];
  const configValue = { ...form };
  const isActive = configValue.is_active;
  delete configValue.is_active;

  channelSaving.value[ch.config_key] = true;
  try {
    await updateNotifyChannel(ch.config_key, { config_value: configValue, is_active: isActive });
    ElMessage.success(`${ch.label} 配置已保存`);
    ch.config_value = configValue;
    ch.is_active = isActive;
  } catch (e) {
    ElMessage.error(e.message || "保存失败");
  } finally {
    channelSaving.value[ch.config_key] = false;
  }
}

async function handleTestChannel(ch) {
  const form = channelForms.value[ch.config_key];
  const configValue = { ...form };
  delete configValue.is_active;

  channelTesting.value[ch.config_key] = true;
  try {
    const result = await testNotifyChannel(ch.config_key, { config_value: configValue });
    if (result.success) {
      ElMessage.success(result.message);
    } else {
      ElMessage.warning(result.message);
    }
  } catch (e) {
    ElMessage.error(e.message || "测试失败");
  } finally {
    channelTesting.value[ch.config_key] = false;
  }
}

// ── 人员权限 ───────────────────────────────────────────────────────────────────
const userList = ref([]);
const userTotal = ref(0);
const userPage = ref(1);
const userLoading = ref(false);
const userSearch = ref("");
const userEditOpen = ref(false);
const userEditTarget = ref(null);
const userEditForm = ref({ is_active: true, department: "", role_codes: [] });

const ALL_ROLES = [
  { code: "admin", name: "系统管理员" },
  { code: "manager", name: "主管" },
  { code: "customer_service", name: "客服" },
  { code: "medical_support", name: "医学支持" },
  { code: "product_ops", name: "产品运营" },
  { code: "qa", name: "质控" },
  { code: "compliance", name: "合规" },
];

async function loadUsers() {
  userLoading.value = true;
  try {
    const params = { page: userPage.value, page_size: 20 };
    if (userSearch.value.trim()) params.search = userSearch.value.trim();
    const data = await getAdminUsers(params);
    userList.value = data.items;
    userTotal.value = data.total;
  } catch (e) {
    ElMessage.error(e.message || "加载用户失败");
  } finally {
    userLoading.value = false;
  }
}

function openUserEdit(user) {
  userEditTarget.value = user;
  userEditForm.value = {
    is_active: user.is_active,
    department: user.department || "",
    role_codes: [...(user.roles || [])],
  };
  userEditOpen.value = true;
}

async function handleSaveUser() {
  try {
    await updateAdminUser(userEditTarget.value.id, {
      is_active: userEditForm.value.is_active,
      department: userEditForm.value.department || undefined,
      role_codes: userEditForm.value.role_codes,
    });
    ElMessage.success("用户信息已更新");
    userEditOpen.value = false;
    await loadUsers();
  } catch (e) {
    ElMessage.error(e.message || "更新失败");
  }
}

async function handleToggleUser(user) {
  try {
    await updateAdminUser(user.id, { is_active: !user.is_active });
    user.is_active = !user.is_active;
    ElMessage.success(user.is_active ? "账号已启用" : "账号已停用");
  } catch (e) {
    ElMessage.error(e.message || "操作失败");
  }
}

// ── 业务字典 ───────────────────────────────────────────────────────────────────
const dictList = ref([]);
const dictLoading = ref(false);
const dictDialogOpen = ref(false);
const editingDictId = ref(null);
const dictDialogTitle = ref("新增字典项");

const dictForm = ref({
  config_key: "", label: "", description: "",
  config_value: '{"value": ""}', sort_order: 0,
});

async function loadDictItems() {
  dictLoading.value = true;
  try {
    const data = await getDictItems({ include_inactive: true });
    dictList.value = data.items || [];
  } catch (e) {
    ElMessage.error(e.message || "加载字典失败");
  } finally {
    dictLoading.value = false;
  }
}

function openCreateDict() {
  dictDialogTitle.value = "新增字典项";
  editingDictId.value = null;
  dictForm.value = { config_key: "", label: "", description: "", config_value: '{"value": ""}', sort_order: 0 };
  dictDialogOpen.value = true;
}

function openEditDict(item) {
  dictDialogTitle.value = "编辑字典项";
  editingDictId.value = item.id;
  dictForm.value = {
    config_key: item.config_key,
    label: item.label,
    description: item.description || "",
    config_value: JSON.stringify(item.config_value, null, 2),
    sort_order: item.sort_order,
  };
  dictDialogOpen.value = true;
}

async function handleSaveDict() {
  if (!dictForm.value.label.trim()) { ElMessage.warning("名称不能为空"); return; }
  let parsedValue;
  try {
    parsedValue = JSON.parse(dictForm.value.config_value);
  } catch {
    ElMessage.error("配置值 JSON 格式有误");
    return;
  }
  const body = {
    config_key: dictForm.value.config_key,
    label: dictForm.value.label.trim(),
    description: dictForm.value.description.trim() || undefined,
    config_value: parsedValue,
    sort_order: dictForm.value.sort_order,
  };
  try {
    if (editingDictId.value) {
      await updateDictItem(editingDictId.value, body);
      ElMessage.success("字典项已更新");
    } else {
      await createDictItem(body);
      ElMessage.success("字典项已创建");
    }
    dictDialogOpen.value = false;
    await loadDictItems();
  } catch (e) {
    ElMessage.error(e.message || "操作失败");
  }
}

async function handleDeleteDict(item) {
  try {
    await ElMessageBox.confirm(`确认删除「${item.label}」吗？`, "删除字典项", { type: "warning" });
    await deleteDictItem(item.id);
    ElMessage.success("已删除");
    await loadDictItems();
  } catch (e) {
    if (e !== "cancel" && e?.message) ElMessage.error(e.message);
  }
}

async function handleToggleDict(item) {
  try {
    await updateDictItem(item.id, { is_active: !item.is_active });
    item.is_active = !item.is_active;
  } catch (e) {
    ElMessage.error(e.message || "操作失败");
  }
}

// ── 初始化 ─────────────────────────────────────────────────────────────────────
function loadCurrentTab() {
  if (tab.value === "Agent Trace") loadTraces();
  else if (tab.value === "工具日志") loadToolLogs();
  else if (tab.value === "风险规则") loadRules();
  else if (tab.value === "通知渠道") loadChannels();
  else if (tab.value === "人员权限") loadUsers();
  else if (tab.value === "基础字典") loadDictItems();
}

watch(tab, loadCurrentTab);

onMounted(async () => {
  await checkSystem();
  await loadTraces();
});
</script>

<template>
  <PageHeader title="系统管理" desc="管理智能体链路、风险规则、通知策略与人员权限。" eyebrow="ADMIN CONSOLE">
    <button class="secondary-btn" @click="checkSystem"><el-icon><Setting /></el-icon>系统状态</button>
  </PageHeader>

  <!-- 顶部指标卡 -->
  <section class="admin-grid">
    <div class="admin-card">
      <span class="ac-icon"><el-icon><Connection /></el-icon></span>
      <div><strong>{{ ready?.mysql && ready?.redis ? "2 / 2" : "- / 2" }}</strong><small>依赖就绪</small></div>
    </div>
    <div class="admin-card">
      <span class="ac-icon blue"><el-icon><Clock /></el-icon></span>
      <div><strong>{{ avgDuration }}</strong><small>当前页平均耗时</small></div>
    </div>
    <div class="admin-card">
      <span class="ac-icon green"><el-icon><Tools /></el-icon></span>
      <div><strong>{{ okCount }}</strong><small>成功节点</small></div>
    </div>
    <div class="admin-card">
      <span class="ac-icon orange"><el-icon><Document /></el-icon></span>
      <div><strong>{{ traceTotal }}</strong><small>Trace 记录</small></div>
    </div>
  </section>

  <section class="card">
    <!-- 标签页 -->
    <div class="tab-bar">
      <button
        v-for="t in ['Agent Trace','工具日志','风险规则','通知渠道','人员权限','基础字典']"
        :key="t" class="tab-button" :class="{ active: tab === t }" @click="tab = t"
      >{{ t }}</button>
    </div>

    <!-- ══ Agent Trace ══════════════════════════════════════════════ -->
    <template v-if="tab === 'Agent Trace'">
      <div class="toolbar">
        <el-input v-model="traceQuery" :prefix-icon="Search" placeholder="Trace ID" clearable style="width:200px" @keyup.enter="loadTraces" />
        <el-select v-model="traceNodeFilter" placeholder="节点" clearable style="width:140px" @change="loadTraces">
          <el-option v-for="node in ['supervisor','task_agent','risk_agent','rag_agent','notify_agent','summary_agent','human_review','tool_call']" :key="node" :label="traceNodeLabel(node)" :value="node" />
        </el-select>
        <button class="small-btn" @click="loadTraces">查询</button>
        <span class="toolbar-spacer"></span>
        <span class="trace-note"><i></i>本地 Agent Trace</span>
      </div>
      <table class="list-table" v-loading="traceLoading">
        <thead><tr><th>Trace ID</th><th>节点</th><th>工具</th><th>耗时</th><th>重试</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="item in traces" :key="item.id">
            <td><strong class="trace-id">{{ item.trace_id }}</strong><span class="table-sub">{{ formatDateTime(item.created_at) }}</span></td>
            <td>{{ traceNodeLabel(item.node) }}</td>
            <td><span class="route-text">{{ item.tool_name || '-' }}</span></td>
            <td>{{ item.duration_ms }}ms</td>
            <td>{{ item.retry_count }}</td>
            <td><span class="status-dot" :class="item.status === 'ok' ? 'done' : item.status === 'error' ? 'overdue' : 'waiting'">{{ item.status }}</span></td>
            <td><button class="ghost-btn" @click="() => { traceSelected = item; traceDetailOpen = true; }"><el-icon><View /></el-icon>详情</button></td>
          </tr>
          <tr v-if="!traces.length && !traceLoading"><td colspan="7" class="empty-row">暂无 Trace 记录</td></tr>
        </tbody>
      </table>
      <div class="pagination-row">
        <span>共 {{ traceTotal }} 条</span>
        <el-pagination small background layout="prev, pager, next"
          :total="traceTotal" :page-size="tracePageSize" :current-page="tracePage"
          @current-change="(p) => { tracePage = p; loadTraces(); }"
        />
      </div>
    </template>

    <!-- ══ 工具日志 ══════════════════════════════════════════════════ -->
    <template v-else-if="tab === '工具日志'">
      <div class="toolbar">
        <span class="toolbar-spacer"></span>
        <button class="small-btn" @click="loadToolLogs">刷新</button>
      </div>
      <table class="list-table" v-loading="toolLoading">
        <thead><tr><th>工具名称</th><th>Trace ID</th><th>状态</th><th>耗时</th><th>重试</th><th>时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="item in toolLogs" :key="item.id">
            <td><strong>{{ item.tool_name || '（未命名）' }}</strong></td>
            <td><span class="trace-id">{{ item.trace_id }}</span></td>
            <td><span class="status-dot" :class="item.status === 'ok' ? 'done' : item.status === 'error' ? 'overdue' : 'waiting'">{{ item.status }}</span></td>
            <td>{{ item.duration_ms }}ms</td>
            <td>{{ item.retry_count }}</td>
            <td>{{ formatDateTime(item.created_at) }}</td>
            <td><button class="ghost-btn" @click="() => { toolSelected = item; toolDetailOpen = true; }"><el-icon><View /></el-icon>详情</button></td>
          </tr>
          <tr v-if="!toolLogs.length && !toolLoading"><td colspan="7" class="empty-row">暂无工具调用记录</td></tr>
        </tbody>
      </table>
      <div class="pagination-row">
        <span>共 {{ toolTotal }} 条工具调用</span>
        <el-pagination small background layout="prev, pager, next"
          :total="toolTotal" :page-size="20" :current-page="toolPage"
          @current-change="(p) => { toolPage = p; loadToolLogs(); }"
        />
      </div>
    </template>

    <!-- ══ 风险规则 ══════════════════════════════════════════════════ -->
    <template v-else-if="tab === '风险规则'">
      <div class="rule-toolbar">
        <span class="rule-count">共 {{ ruleList.length }} 条规则</span>
        <span class="toolbar-spacer"></span>
        <button class="primary-btn" @click="openCreateRule"><el-icon><Plus /></el-icon>新增规则</button>
      </div>
      <table class="list-table" v-loading="ruleLoading">
        <thead><tr><th>规则名称</th><th>类型</th><th>触发关键词</th><th>适用类型</th><th>基线等级</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="rule in ruleList" :key="rule.id" :class="{ 'row-inactive': !rule.is_active }">
            <td>
              <strong>{{ rule.name }}</strong>
              <span v-if="rule.description" class="table-sub">{{ rule.description }}</span>
            </td>
            <td><span class="source-chip">{{ rule.rule_type === 'keyword' ? '关键词' : rule.rule_type === 'type_baseline' ? '类型基线' : '复合' }}</span></td>
            <td>
              <div class="kw-wrap">
                <span v-for="kw in (rule.keywords || []).slice(0, 4)" :key="kw" class="kw-tag">{{ kw }}</span>
                <span v-if="(rule.keywords || []).length > 4" class="kw-more">+{{ rule.keywords.length - 4 }}</span>
              </div>
            </td>
            <td><span v-if="!(rule.task_types || []).length" class="text-muted">全部</span><span v-else>{{ rule.task_types.join('、') }}</span></td>
            <td><RiskBadge :level="rule.baseline_level" compact /></td>
            <td><el-switch :model-value="rule.is_active" @change="handleToggleRule(rule)" active-color="#2868da" size="small" /></td>
            <td>
              <button class="ghost-btn" @click="openEditRule(rule)"><el-icon><Edit /></el-icon>编辑</button>
              <button class="ghost-btn danger-btn" @click="handleDeleteRule(rule)"><el-icon><Close /></el-icon>删除</button>
            </td>
          </tr>
          <tr v-if="!ruleList.length && !ruleLoading"><td colspan="7" class="empty-row">暂无规则</td></tr>
        </tbody>
      </table>
    </template>

    <!-- ══ 通知渠道 ══════════════════════════════════════════════════ -->
    <template v-else-if="tab === '通知渠道'">
      <div v-if="channelLoading" style="padding:32px;text-align:center"><el-skeleton :rows="6" animated /></div>
      <div v-else class="channel-list">
        <div v-for="ch in channels" :key="ch.config_key" class="channel-card">
          <div class="channel-header">
            <span class="channel-name">{{ ch.label }}</span>
            <el-switch
              v-model="channelForms[ch.config_key].is_active"
              active-color="#2868da"
              size="small"
            />
          </div>

          <!-- 站内消息：只有开关 -->
          <div v-if="ch.config_key === 'im'" class="channel-im-tip">
            站内消息为内置渠道，无需额外配置，启用后自动生效。
          </div>

          <!-- 企业微信 -->
          <template v-else-if="ch.config_key === 'wxwork'">
            <el-form label-position="top" size="small">
              <el-form-item label="Webhook URL">
                <el-input v-model="channelForms['wxwork'].webhook_url" placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..." />
              </el-form-item>
              <el-form-item label="@所有人">
                <el-switch v-model="channelForms['wxwork'].mention_all" active-color="#2868da" />
              </el-form-item>
            </el-form>
          </template>

          <!-- 邮件 -->
          <template v-else-if="ch.config_key === 'email'">
            <el-form label-position="top" size="small" class="channel-form-grid">
              <el-form-item label="SMTP 主机">
                <el-input v-model="channelForms['email'].smtp_host" placeholder="smtp.example.com" />
              </el-form-item>
              <el-form-item label="端口">
                <el-input-number v-model="channelForms['email'].smtp_port" :min="1" :max="65535" style="width:100%" />
              </el-form-item>
              <el-form-item label="用户名">
                <el-input v-model="channelForms['email'].smtp_user" placeholder="user@example.com" />
              </el-form-item>
              <el-form-item label="密码">
                <el-input v-model="channelForms['email'].smtp_password" type="password" show-password placeholder="SMTP 密码" />
              </el-form-item>
              <el-form-item label="发件人地址" style="grid-column: 1 / -1">
                <el-input v-model="channelForms['email'].smtp_from" placeholder="noreply@example.com" />
              </el-form-item>
              <el-form-item label="启用 SSL">
                <el-switch v-model="channelForms['email'].use_ssl" active-color="#2868da" />
              </el-form-item>
            </el-form>
          </template>

          <div class="channel-footer">
            <button class="secondary-btn" :disabled="channelTesting[ch.config_key]" @click="handleTestChannel(ch)">
              {{ channelTesting[ch.config_key] ? '测试中...' : '测试发送' }}
            </button>
            <button class="primary-btn" :disabled="channelSaving[ch.config_key]" @click="handleSaveChannel(ch)">
              {{ channelSaving[ch.config_key] ? '保存中...' : '保存配置' }}
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- ══ 人员权限 ══════════════════════════════════════════════════ -->
    <template v-else-if="tab === '人员权限'">
      <div class="toolbar">
        <el-input v-model="userSearch" :prefix-icon="Search" placeholder="姓名/工号/邮箱" clearable style="width:200px" @keyup.enter="loadUsers" />
        <button class="small-btn" @click="loadUsers">查询</button>
      </div>
      <table class="list-table" v-loading="userLoading">
        <thead><tr><th>姓名</th><th>工号</th><th>部门</th><th>角色</th><th>联系方式</th><th>账号状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="user in userList" :key="user.id">
            <td><strong>{{ user.name }}</strong></td>
            <td><span class="trace-id">{{ user.employee_no }}</span></td>
            <td>{{ user.department || '-' }}</td>
            <td>
              <div class="role-tags">
                <span v-for="name in user.role_names" :key="name" class="role-tag">{{ name }}</span>
                <span v-if="!user.role_names.length" class="text-muted">无角色</span>
              </div>
            </td>
            <td>
              <span v-if="user.email" class="table-sub">{{ user.email }}</span>
              <span v-if="user.phone" class="table-sub">{{ user.phone }}</span>
              <span v-if="!user.email && !user.phone" class="text-muted">-</span>
            </td>
            <td>
              <el-switch :model-value="user.is_active" @change="handleToggleUser(user)"
                active-color="#2868da" size="small"
                :active-text="user.is_active ? '启用' : '停用'"
              />
            </td>
            <td><button class="ghost-btn" @click="openUserEdit(user)"><el-icon><Edit /></el-icon>编辑</button></td>
          </tr>
          <tr v-if="!userList.length && !userLoading"><td colspan="7" class="empty-row">暂无用户</td></tr>
        </tbody>
      </table>
      <div class="pagination-row">
        <span>共 {{ userTotal }} 位员工</span>
        <el-pagination small background layout="prev, pager, next"
          :total="userTotal" :page-size="20" :current-page="userPage"
          @current-change="(p) => { userPage = p; loadUsers(); }"
        />
      </div>
    </template>

    <!-- ══ 基础字典 ══════════════════════════════════════════════════ -->
    <template v-else-if="tab === '基础字典'">
      <div class="rule-toolbar">
        <span class="rule-count">共 {{ dictList.length }} 条配置</span>
        <span class="toolbar-spacer"></span>
        <button class="primary-btn" @click="openCreateDict"><el-icon><Plus /></el-icon>新增字典项</button>
      </div>
      <table class="list-table" v-loading="dictLoading">
        <thead><tr><th>名称</th><th>键名</th><th>配置值</th><th>排序</th><th>状态</th><th>更新时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="item in dictList" :key="item.id" :class="{ 'row-inactive': !item.is_active }">
            <td>
              <strong>{{ item.label }}</strong>
              <span v-if="item.description" class="table-sub">{{ item.description }}</span>
            </td>
            <td><span class="trace-id">{{ item.config_key }}</span></td>
            <td><code class="dict-value">{{ JSON.stringify(item.config_value) }}</code></td>
            <td>{{ item.sort_order }}</td>
            <td><el-switch :model-value="item.is_active" @change="handleToggleDict(item)" active-color="#2868da" size="small" /></td>
            <td>{{ formatDateTime(item.updated_at) }}</td>
            <td>
              <button class="ghost-btn" @click="openEditDict(item)"><el-icon><Edit /></el-icon>编辑</button>
              <button class="ghost-btn danger-btn" @click="handleDeleteDict(item)"><el-icon><Close /></el-icon>删除</button>
            </td>
          </tr>
          <tr v-if="!dictList.length && !dictLoading"><td colspan="7" class="empty-row">暂无字典项</td></tr>
        </tbody>
      </table>
    </template>
  </section>

  <!-- ── Trace 详情抽屉 ───────────────────────────────────────────── -->
  <el-drawer v-if="traceSelected" v-model="traceDetailOpen" size="540px">
    <template #header>
      <div class="drawer-title">
        <h3>Trace 执行详情</h3>
        <p>{{ traceSelected.trace_id }} · {{ traceNodeLabel(traceSelected.node) }}</p>
      </div>
    </template>
    <div class="trace-banner">
      <span>状态</span><strong>{{ traceSelected.status }}</strong><b>{{ traceSelected.duration_ms }}ms</b>
    </div>
    <div class="detail-section">
      <h4>基础信息</h4>
      <div class="info-grid">
        <div class="info-item"><span>节点</span><strong>{{ traceNodeLabel(traceSelected.node) }}</strong></div>
        <div class="info-item"><span>重试</span><strong>{{ traceSelected.retry_count }}</strong></div>
        <div class="info-item"><span>时间</span><strong>{{ formatDateTime(traceSelected.created_at) }}</strong></div>
        <div class="info-item"><span>会话</span><strong>{{ traceSelected.session_id || '-' }}</strong></div>
      </div>
    </div>
    <div class="detail-section"><h4>输入数据</h4><pre>{{ JSON.stringify(traceSelected.input_data || {}, null, 2) }}</pre></div>
    <div class="detail-section"><h4>输出数据</h4><pre>{{ JSON.stringify(traceSelected.output_data || {}, null, 2) }}</pre></div>
    <div v-if="traceSelected.error_message" class="detail-section">
      <h4>错误信息</h4><div class="note-box danger">{{ traceSelected.error_message }}</div>
    </div>
  </el-drawer>

  <!-- ── 工具日志详情抽屉 ─────────────────────────────────────────── -->
  <el-drawer v-if="toolSelected" v-model="toolDetailOpen" size="540px">
    <template #header>
      <div class="drawer-title">
        <h3>{{ toolSelected.tool_name || '工具调用详情' }}</h3>
        <p>{{ toolSelected.trace_id }} · {{ formatDateTime(toolSelected.created_at) }}</p>
      </div>
    </template>
    <div class="trace-banner">
      <span>状态</span><strong>{{ toolSelected.status }}</strong><b>{{ toolSelected.duration_ms }}ms</b>
    </div>
    <div class="detail-section"><h4>输入参数</h4><pre>{{ JSON.stringify(toolSelected.input_data || {}, null, 2) }}</pre></div>
    <div class="detail-section"><h4>输出结果</h4><pre>{{ JSON.stringify(toolSelected.output_data || {}, null, 2) }}</pre></div>
    <div v-if="toolSelected.error_message" class="detail-section">
      <h4>错误信息</h4><div class="note-box danger">{{ toolSelected.error_message }}</div>
    </div>
  </el-drawer>

  <!-- ── 规则编辑弹窗 ─────────────────────────────────────────────── -->
  <el-dialog v-model="ruleDialogOpen" :title="ruleDialogTitle" width="540px">
    <el-form label-position="top">
      <el-form-item label="规则名称 *"><el-input v-model="ruleForm.name" /></el-form-item>
      <el-form-item label="规则类型">
        <el-select v-model="ruleForm.rule_type" style="width:100%">
          <el-option v-for="opt in RULE_TYPE_OPTIONS" :key="opt.value" :value="opt.value" :label="opt.label" />
        </el-select>
      </el-form-item>
      <el-form-item label="触发关键词（逗号分隔）">
        <el-input v-model="ruleForm.keywords" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="适用任务类型（逗号分隔，空=全部）">
        <el-input v-model="ruleForm.task_types" />
      </el-form-item>
      <el-form-item label="基线风险等级">
        <el-select v-model="ruleForm.baseline_level" style="width:100%">
          <el-option v-for="opt in BASELINE_OPTIONS" :key="opt.value" :value="opt.value" :label="opt.label" />
        </el-select>
      </el-form-item>
      <el-form-item label="规则说明">
        <el-input v-model="ruleForm.description" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="启用">
        <el-switch v-model="ruleForm.is_active" active-color="#2868da" />
      </el-form-item>
    </el-form>
    <template #footer>
      <button class="secondary-btn" @click="ruleDialogOpen = false">取消</button>
      <button class="primary-btn" @click="handleSaveRule">保存</button>
    </template>
  </el-dialog>

  <!-- ── 用户编辑弹窗 ─────────────────────────────────────────────── -->
  <el-dialog v-if="userEditTarget" v-model="userEditOpen" title="编辑用户" width="480px">
    <el-form label-position="top">
      <el-form-item label="姓名"><el-input :model-value="userEditTarget.name" disabled /></el-form-item>
      <el-form-item label="部门"><el-input v-model="userEditForm.department" placeholder="部门名称" /></el-form-item>
      <el-form-item label="角色">
        <el-select v-model="userEditForm.role_codes" multiple placeholder="选择角色" style="width:100%">
          <el-option v-for="r in ALL_ROLES" :key="r.code" :value="r.code" :label="r.name" />
        </el-select>
      </el-form-item>
      <el-form-item label="账号状态">
        <el-switch v-model="userEditForm.is_active" active-color="#2868da"
          active-text="启用" inactive-text="停用"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <button class="secondary-btn" @click="userEditOpen = false">取消</button>
      <button class="primary-btn" @click="handleSaveUser">保存</button>
    </template>
  </el-dialog>

  <!-- ── 字典编辑弹窗 ─────────────────────────────────────────────── -->
  <el-dialog v-model="dictDialogOpen" :title="dictDialogTitle" width="500px">
    <el-form label-position="top">
      <el-form-item label="键名（唯一）">
        <el-input v-model="dictForm.config_key" :disabled="editingDictId !== null" placeholder="如：risk_review_timeout_hours" />
      </el-form-item>
      <el-form-item label="名称 *"><el-input v-model="dictForm.label" /></el-form-item>
      <el-form-item label="说明"><el-input v-model="dictForm.description" type="textarea" :rows="2" /></el-form-item>
      <el-form-item label="配置值（JSON）">
        <el-input v-model="dictForm.config_value" type="textarea" :rows="3" placeholder='{"value": 30}' />
      </el-form-item>
      <el-form-item label="排序号"><el-input-number v-model="dictForm.sort_order" :min="0" /></el-form-item>
    </el-form>
    <template #footer>
      <button class="secondary-btn" @click="dictDialogOpen = false">取消</button>
      <button class="primary-btn" @click="handleSaveDict">保存</button>
    </template>
  </el-dialog>
</template>

<style scoped>
/* ── 顶部指标卡 ───────────────────────────────────────────────────── */
.admin-grid { display: grid; margin-bottom: 14px; grid-template-columns: repeat(4,1fr); gap: 12px; }
.admin-card { display: flex; align-items: center; gap: 11px; padding: 14px 15px; border: 1px solid #ebeff4; border-radius: 10px; background: white; box-shadow: var(--shadow); }
.admin-card strong { display: block; color: #3d4c61; font-size: 18px; }
.admin-card small { display: block; margin-top: 3px; color: #929dab; font-size: 10px; }
.ac-icon { display: grid; width: 34px; height: 34px; place-items: center; border-radius: 9px; color: #3477e7; background: #edf4ff; flex-shrink: 0; }
.ac-icon.blue { color: #2868da; background: #edf4ff; }
.ac-icon.green { color: #2aa479; background: #eaf8f3; }
.ac-icon.orange { color: #df842e; background: #fff4e9; }
/* ── 工具栏 ───────────────────────────────────────────────────────── */
.rule-toolbar { display: flex; align-items: center; padding: 10px 15px; border-bottom: 1px solid #edf0f4; }
.rule-count { font-size: 12px; color: #7a8798; }
.trace-note { display: flex; align-items: center; gap: 6px; color: #8290a2; font-size: 10px; }
.trace-note i { width: 7px; height: 7px; border-radius: 50%; background: #2eb17e; display: inline-block; }
.trace-id { color: #3373de; font-family: Consolas, monospace; font-size: 11px; }
.route-text { display: block; max-width: 180px; overflow: hidden; color: #718095; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
/* ── 规则/字典表格 ────────────────────────────────────────────────── */
.kw-wrap { display: flex; flex-wrap: wrap; gap: 3px; }
.kw-tag { padding: 1px 6px; border-radius: 3px; font-size: 11px; background: #eef1f4; color: #4a586c; }
.kw-more { font-size: 10px; color: #8490a0; }
.text-muted { color: #aab3bf; font-size: 11px; }
.row-inactive td { opacity: 0.5; }
.dict-value { display: block; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; color: #3a5070; font-family: Consolas, monospace; }
/* ── 通知渠道 ─────────────────────────────────────────────────────── */
.channel-list { display: flex; flex-direction: column; gap: 16px; padding: 16px; }
.channel-card { padding: 16px 20px; border: 1px solid #e6eaf0; border-radius: 10px; background: #fafbfd; }
.channel-header { display: flex; align-items: center; margin-bottom: 14px; }
.channel-name { flex: 1; font-size: 14px; font-weight: 600; color: #334158; }
.channel-im-tip { font-size: 12px; color: #8a96a5; padding: 8px 0; }
.channel-form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
.channel-footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; padding-top: 12px; border-top: 1px solid #edf0f4; }
/* ── 人员权限 ─────────────────────────────────────────────────────── */
.role-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.role-tag { padding: 2px 8px; border-radius: 10px; font-size: 10px; background: #edf4ff; color: #3373de; }
/* ── Trace 抽屉 ───────────────────────────────────────────────────── */
.trace-banner { display: flex; align-items: center; gap: 9px; padding: 11px 12px; border-radius: 8px; background: #fff7e9; margin-bottom: 14px; }
.trace-banner span { color: #a67c46; font-size: 10px; }
.trace-banner strong { color: #b46f27; font-size: 12px; }
.trace-banner b { margin-left: auto; color: #8d98a6; font-size: 11px; }
.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.info-item span { display: block; font-size: 10px; color: #9da6b4; margin-bottom: 3px; }
.info-item strong { font-size: 12px; color: #475566; }
pre { overflow: auto; margin: 0; padding: 12px; border-radius: 7px; color: #526174; font-family: Consolas, monospace; font-size: 11px; line-height: 1.7; background: #f6f8fb; }
.detail-section { padding: 12px 0; border-bottom: 1px solid #edf0f4; }
.detail-section:last-of-type { border-bottom: 0; }
.detail-section h4 { margin: 0 0 10px; font-size: 12px; color: #5a6475; font-weight: 600; }
.empty-row { padding: 32px; color: #aab3bf; text-align: center; font-size: 12px; }
</style>
