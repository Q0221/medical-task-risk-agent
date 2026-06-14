<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { AlarmClock, ArrowRight, CircleCheck, DataLine, Document, Warning } from "@element-plus/icons-vue";
import MetricCard from "../components/MetricCard.vue";
import PageHeader from "../components/PageHeader.vue";
import RiskBadge from "../components/RiskBadge.vue";
import { appState, currentUser, currentUserId } from "../store/app";
import { getPendingReviewTasks, getTasks } from "../api/tasks.js";
import { statusClass, statusLabel, formatDue, formatDateTime } from "../utils/mappers.js";

const router = useRouter();
const isManager = computed(() => ["manager", "admin"].includes(appState.role));
const isOperator = computed(() => ["operator", "admin"].includes(appState.role));

// 从 API 获取的任务数据
const taskItems = ref([]);
const taskTotal = ref(0);
const pendingReviewTasks = ref([]);
const statsLoaded = ref(false);

// 派生统计
const countByStatus = computed(() => {
  const map = {};
  for (const t of taskItems.value) {
    map[t.status] = (map[t.status] || 0) + 1;
  }
  return map;
});

const inProgressCount = computed(() => (countByStatus.value.in_progress || 0) + (countByStatus.value.pending || 0));
const awaitingReviewCount = computed(() => countByStatus.value.awaiting_review || 0);
const completedCount = computed(() => countByStatus.value.completed || 0);
const overdueCount = computed(() => countByStatus.value.overdue || 0);

const recentTasks = computed(() => taskItems.value.slice(0, 5));
const pendingRisks = computed(() => pendingReviewTasks.value.slice(0, 4));
const openTaskStatuses = new Set(["pending", "in_progress", "blocked", "overdue"]);
const reminderTasks = computed(() =>
  taskItems.value
    .filter((task) => openTaskStatuses.has(task.status) && (task.remind_at || task.due_at))
    .sort((a, b) => taskReminderTs(b) - taskReminderTs(a))
    .slice(0, 5)
);

const metrics = computed(() => {
  if (isOperator.value) return [
    { label: "待补充知识", value: 12, desc: "较昨日新增 3 项", icon: Document, tone: "orange", trend: "+3" },
    { label: "SOP 文档总数", value: 286, desc: "本周更新 8 篇", icon: DataLine, tone: "blue", trend: "+8" },
    { label: "今日完成补充", value: 7, desc: "平均处理 1.8 天", icon: CircleCheck, tone: "green", trend: "+18%" },
    { label: "低置信度检索", value: 9, desc: "需要关注的问答", icon: Warning, tone: "red", trend: "-6%" },
  ];
  if (isManager.value) return [
    { label: "部门任务总数", value: statsLoaded.value ? taskTotal.value : "…", desc: `进行中 ${inProgressCount.value} 项`, icon: DataLine, tone: "blue", trend: "" },
    { label: "待审核风险", value: statsLoaded.value ? awaitingReviewCount.value : "…", desc: "高风险事项请及时处理", icon: Warning, tone: "red", trend: "" },
    { label: "已完成任务", value: statsLoaded.value ? completedCount.value : "…", desc: "本批次完成情况", icon: CircleCheck, tone: "green", trend: "" },
    { label: "已逾期任务", value: statsLoaded.value ? overdueCount.value : "…", desc: "需要跟进处理", icon: AlarmClock, tone: "orange", trend: "" },
  ];
  return [
    { label: "任务总数", value: statsLoaded.value ? taskTotal.value : "…", desc: `进行中 ${inProgressCount.value} 项`, icon: DataLine, tone: "blue", trend: "" },
    { label: "待审核", value: statsLoaded.value ? awaitingReviewCount.value : "…", desc: "需要人工审核", icon: Warning, tone: "red", trend: "" },
    { label: "已完成", value: statsLoaded.value ? completedCount.value : "…", desc: "任务完成数量", icon: CircleCheck, tone: "green", trend: "" },
    { label: "已逾期", value: statsLoaded.value ? overdueCount.value : "…", desc: "未来 24 小时到期", icon: AlarmClock, tone: "orange", trend: "" },
  ];
});

const greeting = computed(() => {
  if (!statsLoaded.value) return "正在加载数据...";
  if (appState.role === "operator") return "知识库还有 12 项待补充";
  if (isManager.value) return awaitingReviewCount.value > 0 ? `部门有 ${awaitingReviewCount.value} 项风险等待审核` : "部门暂无待审核风险";
  return overdueCount.value > 0 ? `有 ${overdueCount.value} 项已逾期任务需要处理` : `共有 ${inProgressCount.value} 项任务进行中`;
});

async function loadStats() {
  try {
    const taskParams = { page: 1, page_size: 100 };
    if (!isManager.value) taskParams.assignee_id = currentUserId.value;
    const reviewPromise = isManager.value
      ? getPendingReviewTasks({ page: 1, page_size: 20 })
      : Promise.resolve({ items: [], total: 0 });
    const [taskData, reviewData] = await Promise.all([
      getTasks(taskParams),
      reviewPromise,
    ]);
    taskItems.value = taskData.items;
    taskTotal.value = taskData.total;
    pendingReviewTasks.value = reviewData.items;
  } catch {
    // 加载失败时保持默认值，不影响页面渲染
  } finally {
    statsLoaded.value = true;
  }
}

function taskReminderTs(task) {
  const ts = new Date(task.remind_at || task.due_at || task.created_at).getTime();
  return Number.isNaN(ts) ? 0 : ts;
}

onMounted(loadStats);
watch(() => appState.role, loadStats);
</script>

<template>
  <PageHeader title="早上好，欢迎回来" :desc="`${currentUser.name}，${greeting}。`" eyebrow="TODAY OVERVIEW">
    <button class="secondary-btn"><el-icon><DataLine /></el-icon>导出日报</button>
    <button class="primary-btn" @click="router.push('/assistant')">发起智能协同<el-icon><ArrowRight /></el-icon></button>
  </PageHeader>

  <div class="metrics-grid">
    <MetricCard v-for="item in metrics" :key="item.label" v-bind="item" />
  </div>

  <div class="dashboard-grid">
    <section class="card task-overview">
      <div class="card-head">
        <div><h3>任务进展概览</h3><p>近 7 天任务流转趋势</p></div>
        <el-select size="small" model-value="本周" style="width: 82px"><el-option label="本周" value="本周" /></el-select>
      </div>
      <div class="chart-wrap">
        <div class="chart-legend"><span><i class="blue"></i>新增任务</span><span><i class="green"></i>已完成</span></div>
        <div class="bar-chart">
          <div v-for="(day, index) in ['周一','周二','周三','周四','周五','周六','周日']" :key="day" class="bar-col">
            <div class="bars"><i :style="{ height: [52,70,60,86,72,44,58][index] + '%' }"></i><b :style="{ height: [38,56,73,62,80,52,46][index] + '%' }"></b></div>
            <span>{{ day }}</span>
          </div>
        </div>
      </div>
    </section>

    <section class="card priority-card">
      <div class="card-head">
        <div><h3>{{ isOperator ? "知识补充进度" : "风险等级分布" }}</h3><p>{{ isOperator ? "近 30 天知识空缺处理情况" : "当前未完成任务风险构成" }}</p></div>
      </div>
      <div class="donut-wrap">
        <div class="donut"><strong>{{ isOperator ? "82%" : "42" }}</strong><span>{{ isOperator ? "完成率" : "总任务" }}</span></div>
        <div class="donut-legend">
          <span><i class="red"></i>{{ isOperator ? "待补充" : "紧急风险" }}<b>{{ isOperator ? 12 : 3 }}</b></span>
          <span><i class="orange"></i>{{ isOperator ? "处理中" : "高风险" }}<b>{{ isOperator ? 8 : 8 }}</b></span>
          <span><i class="yellow"></i>{{ isOperator ? "已完成" : "中风险" }}<b>{{ isOperator ? 46 : 12 }}</b></span>
          <span><i class="green"></i>{{ isOperator ? "已归档" : "低风险" }}<b>{{ isOperator ? 19 : 19 }}</b></span>
        </div>
      </div>
    </section>
  </div>

  <div class="dashboard-grid lower">
    <section class="card latest-task">
      <div class="card-head">
        <div><h3>近期任务</h3><p>优先处理即将到期和高风险事项</p></div>
        <button class="text-link" @click="router.push('/tasks')">全部任务 <el-icon><ArrowRight /></el-icon></button>
      </div>
      <table class="list-table">
        <tbody>
          <template v-if="!statsLoaded">
            <tr><td colspan="4" style="padding:16px;color:#aab3bf;text-align:center;font-size:12px">加载中...</td></tr>
          </template>
          <template v-else-if="!recentTasks.length">
            <tr><td colspan="4" style="padding:16px;color:#aab3bf;text-align:center;font-size:12px">暂无任务数据</td></tr>
          </template>
          <template v-else>
            <tr v-for="task in recentTasks" :key="task.id">
              <td><strong class="table-title">{{ task.title }}</strong><span class="table-sub">#{{ task.id }}</span></td>
              <td><RiskBadge :level="task.risk_level" compact /></td>
              <td><span class="status-dot" :class="statusClass(task.status)">{{ statusLabel(task.status) }}</span></td>
              <td class="due-cell">{{ formatDue(task.due_at) }}</td>
            </tr>
          </template>
        </tbody>
      </table>
    </section>

    <section class="card pending-card">
      <div class="card-head">
        <div><h3>{{ isManager ? "待审核风险" : "今日提醒" }}</h3><p>{{ isManager ? "高风险事项需要及时决策" : "按计划推进今日事项" }}</p></div>
      </div>
      <div v-if="isManager" class="risk-mini-list">
        <button v-for="risk in pendingRisks" :key="risk.id" @click="router.push('/risk')">
          <RiskBadge :level="risk.risk_level" compact /><strong>{{ risk.title }}</strong><span>医院 ID {{ risk.hospital_id ?? '-' }} · {{ formatDateTime(risk.created_at) }}</span>
        </button>
        <div v-if="!pendingRisks.length" class="mini-empty">暂无待审核风险</div>
      </div>
      <div v-else class="reminder-list">
        <div v-for="item in reminderTasks" :key="item.id">
          <i></i>
          <p>
            <strong>{{ formatDue(item.remind_at || item.due_at) }}</strong>
            <span>{{ item.title }}</span>
          </p>
        </div>
        <div v-if="!reminderTasks.length" class="mini-empty">暂无未完成提醒任务</div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.dashboard-grid { display: grid; grid-template-columns: 1.52fr .78fr; gap: 14px; margin-top: 15px; }
.dashboard-grid.lower { grid-template-columns: 1.52fr .78fr; }
.chart-wrap { padding: 2px 20px 16px; }
.chart-legend { display: flex; justify-content: end; gap: 15px; color: #8d99a9; font-size: 10px; }
.chart-legend i, .donut-legend i { display: inline-block; width: 7px; height: 7px; margin-right: 5px; border-radius: 50%; }
.blue { background: #4a85f4; }.green { background: #35b88a; }.red { background: #eb6868; }.orange { background: #ee984f; }.yellow { background: #e4bf4f; }
.bar-chart { display: flex; height: 153px; align-items: end; justify-content: space-around; margin-top: 10px; padding-top: 10px; border-bottom: 1px solid #edf0f4; background: repeating-linear-gradient(to bottom,#edf0f4 0,#edf0f4 1px,transparent 1px,transparent 38px); }
.bar-col { display: flex; height: 100%; flex-direction: column; justify-content: end; align-items: center; }
.bars { display: flex; height: 119px; align-items: end; gap: 4px; }.bars i, .bars b { display: block; width: 12px; border-radius: 3px 3px 0 0; }.bars i { background: #5d91f0; }.bars b { background: #51c29b; }
.bar-col span { margin: 8px 0 -17px; color: #9ba5b2; font-size: 10px; }
.donut-wrap { display: flex; align-items: center; gap: 27px; padding: 14px 20px 25px; }
.donut { display: grid; width: 126px; height: 126px; flex: none; place-content: center; border-radius: 50%; text-align: center; background: radial-gradient(circle,#fff 55%,transparent 56%), conic-gradient(#eb6868 0 8%,#ee984f 8% 27%,#e4bf4f 27% 55%,#35b88a 55% 100%); }
.donut strong { font-size: 22px; }.donut span { margin-top: 4px; color: #98a3b1; font-size: 10px; }
.donut-legend { display: grid; flex: 1; gap: 12px; }
.donut-legend span { color: #768397; font-size: 11px; }.donut-legend b { float: right; color: #475569; }
.latest-task td { padding-top: 11px; padding-bottom: 11px; }.due-cell { color: #8692a3 !important; white-space: nowrap; }
.risk-mini-list { display: grid; gap: 0; padding: 0 14px 10px; }
.risk-mini-list button { padding: 12px 4px; border: 0; border-top: 1px solid #edf0f4; text-align: left; background: transparent; }
.risk-mini-list strong, .risk-mini-list span { display: block; }.risk-mini-list strong { margin-top: 8px; color: #46556a; font-size: 11px; }.risk-mini-list span { margin-top: 5px; color: #9ca5b2; font-size: 10px; }
.mini-empty { padding: 18px 4px; border-top: 1px solid #edf0f4; color: #a6afbb; font-size: 11px; text-align: center; }
.reminder-list { display: grid; gap: 0; padding: 0 16px 10px; }.reminder-list div { display: flex; gap: 11px; padding: 12px 0; border-top: 1px solid #edf0f4; }.reminder-list i { width: 8px; height: 8px; margin-top: 4px; border-radius: 50%; background: #4a86f5; }.reminder-list strong,.reminder-list span { display: block; }.reminder-list strong { color: #526176; font-size: 11px; }.reminder-list span { margin-top: 5px; color: #8f99a7; font-size: 10px; line-height: 1.5; }
</style>
