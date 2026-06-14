<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  AlarmClock,
  ArrowDown,
  Bell,
  ChatDotRound,
  Check,
  CircleCheck,
  Clock,
  DataAnalysis,
  Document,
  Files,
  Grid,
  House,
  Lock,
  Management,
  Refresh,
  Search,
  Setting,
  SwitchButton,
  UserFilled,
  Warning,
  View,
} from "@element-plus/icons-vue";
import { appState, currentUser, currentUserId, logout, roles, unreadCount } from "../store/app";
import { getNotifications, markBatchRead, markNotificationRead, retryNotification } from "../api/notifications.js";
import { formatDateTime, notificationKindLabel, notificationStatusLabel, typeLabel } from "../utils/mappers.js";

const route = useRoute();
const router = useRouter();

// ─── 通知抽屉 ─────────────────────────────────────────────────────────────────
const notificationOpen = ref(false);
const notificationLoading = ref(false);
const activeFilter = ref("all");
const notifiedReminderIds = new Set();
let notificationTimer = null;

const FILTER_TABS = [
  { key: "all",     label: "全部" },
  { key: "reminder", label: "任务提醒" },
  { key: "overdue",  label: "逾期" },
  { key: "risk",     label: "风险审核" },
  { key: "knowledge", label: "知识" },
  { key: "system",   label: "系统通知" },
];

const KIND_TO_FILTER = {
  task_created: "reminder",
  task_reminder: "reminder",
  task_overdue: "overdue",
  risk_review_required: "risk",
  knowledge_gap_assigned: "knowledge",
  daily_summary: "system",
  weekly_summary: "system",
};

// ─── 导航 ──────────────────────────────────────────────────────────────────────
const navItems = [
  { path: "/dashboard", label: "总览工作台", icon: House },
  { path: "/assistant", label: "智能协同",   icon: ChatDotRound },
  { path: "/tasks",     label: "任务中心",   icon: Grid },
  { path: "/risk",      label: "风险中心",   icon: Warning, roles: ["manager", "admin"] },
  { path: "/records",   label: "业务档案",   icon: Files },
  { path: "/knowledge", label: "知识中心",   icon: Document },
  { path: "/reports",   label: "统计报告",   icon: DataAnalysis },
];

const visibleItems = computed(() => navItems.filter((item) => !item.roles || item.roles.includes(appState.role)));
const currentTitle = computed(() => route.meta.title || "总览工作台");

// ─── 通知列表计算 ──────────────────────────────────────────────────────────────
const filteredNotifications = computed(() => {
  if (activeFilter.value === "all") return appState.notifications;
  return appState.notifications.filter((item) => item.filterKey === activeFilter.value);
});

const filterCounts = computed(() => {
  const counts = { all: 0 };
  for (const tab of FILTER_TABS) counts[tab.key] = 0;
  for (const item of appState.notifications) {
    if (!item.is_read) {
      counts.all++;
      if (item.filterKey) counts[item.filterKey] = (counts[item.filterKey] || 0) + 1;
    }
  }
  return counts;
});

// ─── 通知数据转换 ──────────────────────────────────────────────────────────────
const closedTaskStatuses = new Set(["completed", "cancelled"]);

function toNotificationItem(raw) {
  const kind = raw.kind || "";
  const filterKey = KIND_TO_FILTER[kind] || "system";
  const isReminder = kind === "task_reminder" || kind === "task_created";
  const isOverdue = kind === "task_overdue";
  const isRisk = kind === "risk_review_required";
  const isKnowledge = kind === "knowledge_gap_assigned";
  const isSummary = kind.includes("summary");
  const isClosedTask = closedTaskStatuses.has(raw.task_status);
  const isActiveReminder = (kind === "task_reminder" || isOverdue) && !isClosedTask;

  // 展示规则：标题与描述
  let displayTitle = raw.title || notificationKindLabel(kind);
  let displayDesc = raw.content || "";
  let instruction = "";

  if (isReminder && raw.task_title) {
    displayTitle = raw.task_title;
    displayDesc = `类型：${typeLabel(raw.task_type || "")}  ·  提醒时间到，请确认处理进度`;
    instruction = isClosedTask ? "该任务已完成或取消，提醒仅供记录。" : "请进入任务详情确认进度，完成后可标记完成。";
  } else if (isOverdue && raw.task_title) {
    displayTitle = `【逾期】${raw.task_title}`;
    displayDesc = `任务已逾期，当前状态：${notificationStatusLabel(raw.task_status || "")}`;
    instruction = isClosedTask ? "任务已关闭。" : "请尽快处理或更新截止时间。";
  } else if (isRisk && raw.task_title) {
    displayTitle = `风险审核：${raw.task_title}`;
    displayDesc = raw.task_risk_level ? `风险等级：${raw.task_risk_level.toUpperCase()}  ·  需要人工审核` : "需要人工风险审核";
    instruction = "请在风险中心完成审核操作。";
  } else if (isKnowledge) {
    displayDesc = "知识空缺任务已分配给您，请及时处理。";
    instruction = "前往知识中心查看详情。";
  } else if (isSummary) {
    displayDesc = (raw.content || "").slice(0, 100) + ((raw.content || "").length > 100 ? "…" : "");
  }

  return {
    id: raw.id,
    filterKey,
    isReminder,
    isOverdue,
    isRisk,
    isKnowledge,
    isSummary,
    isActiveReminder,
    isClosedTask,
    is_read: raw.is_read,
    title: displayTitle,
    desc: displayDesc,
    instruction,
    time: formatDateTime(raw.created_at),
    taskId: raw.task_id,
    kindLabel: notificationKindLabel(kind),
    statusLabel: notificationStatusLabel(raw.status),
    isFailed: ["failed", "dead"].includes(raw.status),
    raw,
  };
}

// ─── 加载通知 ──────────────────────────────────────────────────────────────────
async function loadNotifications(options = {}) {
  notificationLoading.value = true;
  try {
    const data = await getNotifications({ page: 1, page_size: 30 });
    const items = (data.items || []).map(toNotificationItem);
    // 未读提醒冒泡在前，其余按时间倒序
    items.sort((a, b) => {
      if (a.isActiveReminder !== b.isActiveReminder) return a.isActiveReminder ? -1 : 1;
      if (a.is_read !== b.is_read) return a.is_read ? 1 : -1;
      return b.id - a.id;
    });
    appState.notifications = items;
    // 同步未读数到 store
    appState.unreadTotal = data.unread_count ?? items.filter((i) => !i.is_read).length;

    if (!options.silent && !options.prime) {
      // 新的活跃提醒弹出 toast
      items
        .filter((item) => item.isActiveReminder && !item.is_read && !notifiedReminderIds.has(item.id))
        .forEach((item) => {
          notifiedReminderIds.add(item.id);
          ElMessage({ type: item.isOverdue ? "error" : "warning", message: item.title, duration: 6000, showClose: true });
        });
    } else {
      items.filter((item) => item.isActiveReminder).forEach((item) => notifiedReminderIds.add(item.id));
    }
  } catch (err) {
    if (!options.silent) ElMessage.warning(err.message || "通知加载失败");
  } finally {
    notificationLoading.value = false;
  }
}

// ─── 已读操作 ──────────────────────────────────────────────────────────────────
async function handleMarkRead(item, event) {
  event?.stopPropagation();
  if (item.is_read) return;
  try {
    await markNotificationRead(item.id);
    item.is_read = true;
    appState.unreadTotal = Math.max(0, (appState.unreadTotal || 0) - 1);
  } catch {
    // 静默失败，下次刷新时同步
  }
}

async function handleMarkAllRead() {
  try {
    const result = await markBatchRead(null);
    ElMessage.success(`已标记 ${result.marked} 条为已读`);
    await loadNotifications({ silent: true });
  } catch (err) {
    ElMessage.error(err.message || "批量已读失败");
  }
}

// ─── 跳转与操作 ───────────────────────────────────────────────────────────────
function openTaskFromNotification(item) {
  if (!item.taskId) return;
  handleMarkRead(item);
  notificationOpen.value = false;
  router.push({ path: "/tasks", query: { task_id: item.taskId } });
}

function navigateFromNotification(item) {
  handleMarkRead(item);
  if (item.taskId) {
    notificationOpen.value = false;
    router.push({ path: item.isRisk ? "/risk" : "/tasks", query: { task_id: item.taskId } });
  } else if (item.isSummary) {
    notificationOpen.value = false;
    router.push("/reports");
  } else if (item.isKnowledge) {
    notificationOpen.value = false;
    router.push("/knowledge");
  }
}

async function handleRetryNotification(item, event) {
  event?.stopPropagation();
  try {
    await retryNotification(item.id);
    ElMessage.success("通知已重新加入发送队列");
    await loadNotifications({ silent: true });
  } catch (err) {
    ElMessage.error(err.message || "重试失败");
  }
}

// ─── 用户菜单 ──────────────────────────────────────────────────────────────────
function handleDropdownCommand(command) {
  if (command === "switch") { logout(); router.replace("/login"); return; }
  if (command === "logout") { handleLogout(); return; }
}

async function handleLogout() {
  try {
    await ElMessageBox.confirm("确认退出当前账号吗？", "退出登录", {
      confirmButtonText: "确认退出", cancelButtonText: "取消", type: "warning",
    });
    logout();
    await router.replace("/login");
    ElMessage.success("已退出登录");
  } catch { /* cancelled */ }
}

// ─── 生命周期 ──────────────────────────────────────────────────────────────────
watch(notificationOpen, (open) => {
  if (open) loadNotifications({ silent: true });
});

onMounted(() => {
  loadNotifications({ prime: true });
  notificationTimer = window.setInterval(() => loadNotifications({ silent: true }), 30000);
});

onBeforeUnmount(() => {
  if (notificationTimer) window.clearInterval(notificationTimer);
});

// ─── unreadCount 改为读 store ──────────────────────────────────────────────────
const badgeCount = computed(() => appState.unreadTotal ?? unreadCount.value ?? 0);
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">M</div>
        <div><strong>MedFlow</strong><span>智能协同平台</span></div>
      </div>

      <div class="workspace-card">
        <span>当前工作空间</span>
        <strong>医疗任务协同中心</strong>
      </div>

      <nav class="main-nav">
        <span class="nav-caption">工作台</span>
        <router-link v-for="item in visibleItems" :key="item.path" :to="item.path" class="nav-item">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </router-link>
        <span v-if="appState.role === 'admin'" class="nav-caption system-caption">系统</span>
        <router-link v-if="appState.role === 'admin'" to="/admin" class="nav-item">
          <el-icon><Setting /></el-icon><span>系统管理</span>
        </router-link>
      </nav>

      <div class="sidebar-bottom">
        <div class="assist-mini">
          <div class="assist-mini-icon"><el-icon><Management /></el-icon></div>
          <div><strong>AI 服务正常</strong><span>5 个 Agent 在线</span></div>
          <i></i>
        </div>
        <div class="sidebar-user">
          <div class="avatar">{{ currentUser.initials }}</div>
          <div><strong>{{ currentUser.name }}</strong><span>{{ currentUser.dept }}</span></div>
        </div>
      </div>
    </aside>

    <main class="main-stage">
      <header class="topbar">
        <div>
          <span class="breadcrumb">MedFlow / {{ currentTitle }}</span>
          <h2>{{ currentTitle }}</h2>
        </div>
        <div class="topbar-actions">
          <div class="global-search">
            <el-icon><Search /></el-icon><span>搜索任务、医院或 trace_id</span><kbd>⌘ K</kbd>
          </div>

          <!-- 通知铃铛 -->
          <button class="icon-btn notification-btn" @click="notificationOpen = true">
            <el-icon><Bell /></el-icon>
            <b v-if="badgeCount > 0">{{ badgeCount > 99 ? "99+" : badgeCount }}</b>
          </button>

          <el-dropdown trigger="click" @command="handleDropdownCommand">
            <button class="role-switch">
              <div class="top-avatar">{{ currentUser.initials }}</div>
              <div><strong>{{ currentUser.name }}</strong><span>{{ currentUser.label || roles[appState.role]?.label }}</span></div>
              <el-icon><ArrowDown /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="switch"><el-icon><UserFilled /></el-icon>切换账号</el-dropdown-item>
                <el-dropdown-item divided command="logout"><el-icon><SwitchButton /></el-icon>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>
      <section class="content-stage">
        <router-view />
      </section>
    </main>
  </div>

  <!-- ───────────── 通知中心抽屉 ───────────── -->
  <el-drawer
    v-model="notificationOpen"
    title=""
    :with-header="false"
    size="460px"
    direction="rtl"
    class="notification-drawer"
  >
    <!-- 抽屉头部 -->
    <div class="nd-head">
      <strong class="nd-title">通知中心</strong>
      <span v-if="badgeCount > 0" class="nd-badge">{{ badgeCount }} 条未读</span>
      <span v-else class="nd-badge read">全部已读</span>
      <div class="nd-head-actions">
        <button class="nd-action-btn" :disabled="badgeCount === 0" @click="handleMarkAllRead">
          <el-icon><CircleCheck /></el-icon>全部已读
        </button>
        <button class="nd-action-btn" @click="loadNotifications()">
          <el-icon><Refresh /></el-icon>
        </button>
      </div>
    </div>

    <!-- 类型筛选 -->
    <div class="nd-filter">
      <button
        v-for="tab in FILTER_TABS"
        :key="tab.key"
        class="nd-filter-btn"
        :class="{ active: activeFilter === tab.key }"
        @click="activeFilter = tab.key"
      >
        {{ tab.label }}
        <span v-if="filterCounts[tab.key] > 0" class="nd-filter-dot">{{ filterCounts[tab.key] }}</span>
      </button>
    </div>

    <!-- 通知列表 -->
    <div class="nd-list" v-loading="notificationLoading">
      <div
        v-for="item in filteredNotifications"
        :key="item.id"
        class="nd-item"
        :class="[
          item.filterKey,
          { unread: !item.is_read, 'active-reminder': item.isActiveReminder, closed: item.isClosedTask }
        ]"
        @click="navigateFromNotification(item)"
      >
        <!-- 左侧类型图标 -->
        <div class="nd-icon" :class="item.filterKey">
          <el-icon v-if="item.isOverdue"><Warning /></el-icon>
          <el-icon v-else-if="item.isRisk"><Lock /></el-icon>
          <el-icon v-else-if="item.isKnowledge"><Document /></el-icon>
          <el-icon v-else-if="item.isSummary"><DataAnalysis /></el-icon>
          <el-icon v-else-if="item.isReminder"><AlarmClock /></el-icon>
          <el-icon v-else><Bell /></el-icon>
        </div>

        <!-- 内容区 -->
        <div class="nd-content">
          <div class="nd-title-row">
            <strong class="nd-item-title" :class="{ read: item.is_read }">{{ item.title }}</strong>
            <span class="nd-kind-tag" :class="item.filterKey">{{ item.kindLabel }}</span>
          </div>

          <p v-if="item.desc" class="nd-desc">{{ item.desc }}</p>

          <div v-if="item.instruction && !item.isClosedTask" class="nd-instruction">
            <el-icon><Clock /></el-icon>{{ item.instruction }}
          </div>

          <!-- 任务快捷跳转 -->
          <div class="nd-meta-row">
            <span class="nd-time">{{ item.time }}</span>
            <span v-if="item.isClosedTask" class="nd-closed-tag">任务已关闭</span>
            <span v-else-if="item.isFailed" class="nd-failed-tag">{{ item.statusLabel }}</span>
          </div>
        </div>

        <!-- 右侧操作按钮 -->
        <div class="nd-actions" @click.stop>
          <button
            v-if="item.taskId && !item.isSummary"
            class="nd-btn"
            title="查看任务"
            @click="openTaskFromNotification(item)"
          ><el-icon><View /></el-icon></button>
          <button
            v-if="!item.is_read"
            class="nd-btn"
            title="标记已读"
            @click="handleMarkRead(item, $event)"
          ><el-icon><Check /></el-icon></button>
          <button
            v-if="item.isFailed"
            class="nd-btn retry"
            title="重试发送"
            @click="handleRetryNotification(item, $event)"
          ><el-icon><Refresh /></el-icon></button>
        </div>
      </div>

      <div v-if="!notificationLoading && !filteredNotifications.length" class="nd-empty">
        <el-icon><Bell /></el-icon>
        <span>暂无{{ activeFilter === "all" ? "" : FILTER_TABS.find(t => t.key === activeFilter)?.label }}通知</span>
      </div>
    </div>
  </el-drawer>
</template>

<style>
/* 通知抽屉全局样式（无 scoped，覆盖 el-drawer） */
.notification-drawer .el-drawer__body {
  padding: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
</style>

<style scoped>
/* ── 主布局 ─────────────────────────────────────── */
.app-shell { display: flex; height: 100vh; background: #f1f4f8; overflow: hidden; }
.sidebar { display: flex; width: 210px; min-width: 210px; height: 100vh; flex-direction: column; background: #1b2533; color: #cdd6e3; overflow-y: auto; }
.brand { display: flex; align-items: center; gap: 10px; padding: 20px 16px 14px; border-bottom: 1px solid rgba(255,255,255,.06); }
.brand-mark { display: grid; width: 30px; height: 30px; flex: none; place-items: center; border-radius: 8px; font-size: 14px; font-weight: 900; color: #fff; background: linear-gradient(135deg,#3d72e8,#2a5bd6); }
.brand strong { font-size: 13px; color: #e8edf3; display: block; }
.brand span { font-size: 9px; color: #6b7d93; }
.workspace-card { margin: 12px 12px 0; padding: 9px 12px; border-radius: 8px; background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.06); }
.workspace-card span { display: block; font-size: 9px; color: #5b6d80; margin-bottom: 2px; }
.workspace-card strong { font-size: 11px; color: #b8c4d2; }
.main-nav { flex: 1; padding: 12px 10px; }
.nav-caption { display: block; padding: 10px 6px 4px; font-size: 9px; color: #49596b; text-transform: uppercase; letter-spacing: .05em; }
.system-caption { margin-top: 8px; border-top: 1px solid rgba(255,255,255,.05); padding-top: 12px; }
.nav-item { display: flex; align-items: center; gap: 9px; padding: 8px 10px; border-radius: 7px; text-decoration: none; color: #8a9db3; font-size: 12px; transition: background .15s, color .15s; }
.nav-item:hover { background: rgba(255,255,255,.06); color: #c8d5e2; }
.nav-item.router-link-active { background: rgba(61,114,232,.2); color: #7aa8f8; }
.sidebar-bottom { padding: 12px; border-top: 1px solid rgba(255,255,255,.06); }
.assist-mini { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 7px; background: rgba(255,255,255,.04); margin-bottom: 8px; }
.assist-mini-icon { display: grid; width: 24px; height: 24px; flex: none; place-items: center; border-radius: 6px; background: rgba(61,114,232,.25); color: #7aa8f8; font-size: 12px; }
.assist-mini strong { display: block; font-size: 10px; color: #b2bece; }
.assist-mini span { display: block; font-size: 8px; color: #5e7087; }
.assist-mini i { width: 6px; height: 6px; flex: none; border-radius: 50%; background: #3eb389; margin-left: auto; }
.sidebar-user { display: flex; align-items: center; gap: 9px; padding: 6px 4px; }
.avatar { display: grid; width: 28px; height: 28px; flex: none; place-items: center; border-radius: 50%; font-size: 11px; font-weight: 700; color: #fff; background: linear-gradient(135deg,#4e89f0,#3060d0); }

/* ── 主内容区 ────────────────────────────────────── */
.main-stage { display: flex; flex: 1; min-width: 0; flex-direction: column; overflow: hidden; }
.topbar { display: flex; align-items: center; justify-content: space-between; padding: 0 24px; height: 56px; flex: none; background: #fff; border-bottom: 1px solid #eef1f5; }
.breadcrumb { display: block; font-size: 9px; color: #9aa5b3; }
.topbar h2 { font-size: 14px; color: #2d3f52; font-weight: 700; margin: 0; }
.topbar-actions { display: flex; align-items: center; gap: 10px; }
.global-search { display: flex; align-items: center; gap: 7px; padding: 6px 12px; border-radius: 7px; font-size: 11px; color: #9aa5b3; background: #f4f7fa; cursor: pointer; border: 1px solid #eaecef; }
.global-search kbd { padding: 1px 5px; border-radius: 3px; background: #e8ecf0; font-size: 9px; }
.icon-btn { display: grid; width: 34px; height: 34px; place-items: center; border: none; border-radius: 8px; color: #6b7e94; background: #f4f7fa; cursor: pointer; position: relative; transition: background .15s; }
.icon-btn:hover { background: #e8edf3; }
.notification-btn b { position: absolute; top: 2px; right: 2px; display: grid; min-width: 15px; height: 15px; place-items: center; padding: 0 3px; border-radius: 8px; font-size: 8px; font-weight: 700; color: #fff; background: #e53e3e; }
.role-switch { display: flex; align-items: center; gap: 8px; padding: 5px 10px; border: none; border-radius: 8px; background: #f4f7fa; cursor: pointer; transition: background .15s; }
.role-switch:hover { background: #e8edf3; }
.top-avatar { display: grid; width: 26px; height: 26px; flex: none; place-items: center; border-radius: 50%; font-size: 11px; font-weight: 700; color: #fff; background: linear-gradient(135deg,#4e89f0,#3060d0); }
.role-switch strong, .role-switch span { display: block; text-align: left; }
.role-switch strong { font-size: 11px; color: #3a4a5c; }
.role-switch span { font-size: 9px; color: #8a97a7; }
.content-stage { flex: 1; overflow-y: auto; padding: 18px 24px 24px; }

/* ── 通知抽屉内部 ─────────────────────────────────── */
.nd-head { display: flex; align-items: center; gap: 8px; padding: 16px 20px 12px; border-bottom: 1px solid #eef1f5; flex: none; }
.nd-title { font-size: 15px; font-weight: 700; color: #2d3f52; }
.nd-badge { padding: 2px 8px; border-radius: 10px; font-size: 10px; background: #fee2e2; color: #c53030; }
.nd-badge.read { background: #e8f5e9; color: #2e7d32; }
.nd-head-actions { display: flex; align-items: center; gap: 6px; margin-left: auto; }
.nd-action-btn { display: inline-flex; align-items: center; gap: 4px; padding: 5px 10px; border: 1px solid #d9dfe8; border-radius: 6px; font-size: 11px; color: #566378; background: none; cursor: pointer; }
.nd-action-btn:hover:not(:disabled) { border-color: #3476e5; color: #3476e5; }
.nd-action-btn:disabled { opacity: 0.45; cursor: not-allowed; }

/* 筛选 tabs */
.nd-filter { display: flex; gap: 4px; padding: 8px 16px; border-bottom: 1px solid #eef1f5; flex-wrap: wrap; flex: none; }
.nd-filter-btn { position: relative; display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; border: 1px solid #e4e8ed; border-radius: 14px; font-size: 11px; color: #7a8898; background: none; cursor: pointer; transition: all .15s; }
.nd-filter-btn:hover { border-color: #3476e5; color: #3476e5; }
.nd-filter-btn.active { border-color: #3476e5; color: #3476e5; background: #edf4ff; font-weight: 600; }
.nd-filter-dot { display: inline-grid; min-width: 16px; height: 16px; place-items: center; border-radius: 8px; font-size: 9px; font-weight: 700; color: #fff; background: #e53e3e; padding: 0 3px; }

/* 通知列表 */
.nd-list { flex: 1; overflow-y: auto; }
.nd-item { display: flex; align-items: flex-start; gap: 10px; padding: 12px 16px; border-bottom: 1px solid #f2f4f7; cursor: pointer; transition: background .15s; position: relative; }
.nd-item:hover { background: #f8fafc; }
.nd-item.unread { background: #fafbff; }
.nd-item.unread::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; border-radius: 0 2px 2px 0; background: #3476e5; }
.nd-item.active-reminder.reminder::before { background: #e67e22; }
.nd-item.active-reminder.overdue::before { background: #e53e3e; }
.nd-item.risk::before { background: #e53e3e !important; }
.nd-item.closed { opacity: 0.6; }

/* 图标 */
.nd-icon { display: grid; width: 32px; height: 32px; flex: none; place-items: center; border-radius: 8px; font-size: 14px; margin-top: 1px; }
.nd-icon.reminder { background: #ebf3ff; color: #3476e5; }
.nd-icon.overdue   { background: #fff0f0; color: #e53e3e; }
.nd-icon.risk      { background: #fff0f0; color: #e53e3e; }
.nd-icon.knowledge { background: #e8f7f2; color: #1e8f6f; }
.nd-icon.system    { background: #f0f4ff; color: #5b6ae8; }

/* 内容 */
.nd-content { flex: 1; min-width: 0; }
.nd-title-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.nd-item-title { font-size: 12px; color: #3a4a5c; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0; }
.nd-item-title.read { color: #9aa5b3; font-weight: 400; }
.nd-kind-tag { flex: none; padding: 1px 6px; border-radius: 3px; font-size: 9px; font-weight: 500; background: #f0f4f8; color: #6b7a8c; }
.nd-kind-tag.overdue { background: #fff0f0; color: #c53030; }
.nd-kind-tag.risk    { background: #fff0f0; color: #c53030; }
.nd-kind-tag.reminder { background: #ebf3ff; color: #2b63c9; }
.nd-kind-tag.knowledge { background: #e8f7f2; color: #176b52; }
.nd-kind-tag.system  { background: #eef0ff; color: #4752c8; }
.nd-desc { margin: 4px 0 0; font-size: 11px; color: #7a8898; line-height: 1.5; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.nd-instruction { display: flex; align-items: center; gap: 4px; margin-top: 5px; font-size: 10px; color: #e67e22; }
.nd-item.overdue .nd-instruction { color: #e53e3e; }
.nd-meta-row { display: flex; align-items: center; gap: 8px; margin-top: 5px; }
.nd-time { font-size: 10px; color: #aab3be; }
.nd-closed-tag { padding: 1px 5px; border-radius: 3px; font-size: 9px; background: #f0f2f5; color: #9aa5b3; }
.nd-failed-tag { padding: 1px 5px; border-radius: 3px; font-size: 9px; background: #fff0f0; color: #c53030; }

/* 操作按钮 */
.nd-actions { display: flex; flex-direction: column; gap: 4px; flex: none; }
.nd-btn { display: grid; width: 24px; height: 24px; place-items: center; border: 1px solid #e4e8ed; border-radius: 5px; font-size: 11px; color: #7a8898; background: none; cursor: pointer; }
.nd-btn:hover { border-color: #3476e5; color: #3476e5; background: #edf4ff; }
.nd-btn.retry:hover { border-color: #e67e22; color: #e67e22; background: #fff4eb; }

/* 空态 */
.nd-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; padding: 48px 24px; color: #b0b9c5; font-size: 12px; }
.nd-empty .el-icon { font-size: 32px; opacity: 0.35; }
</style>
