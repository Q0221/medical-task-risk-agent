<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { DataAnalysis, Download, Plus, Refresh, TrendCharts } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import MetricCard from "../components/MetricCard.vue";
import PageHeader from "../components/PageHeader.vue";
import { getSummary } from "../api/summary.js";
import {
  downloadReport,
  getChartAssignee,
  getChartRisk,
  getChartTrend,
  getChartType,
  getReportDetail,
  getReportHistory,
} from "../api/reports.js";
import { formatDateTime, notificationKindLabel, typeLabel } from "../utils/mappers.js";

// ─── 报告生成区 ───────────────────────────────────────────────────────────────
const range = ref("本周");
const summary = ref(null);
const generating = ref(false);
let generationToken = 0;

const stats = computed(() => summary.value?.stats);
const metrics = computed(() => [
  { label: range.value === "本周" ? "本周新增任务" : "今日新增任务", value: stats.value?.total_created ?? "待生成", desc: `高风险 ${stats.value?.total_high_risk ?? 0} 项`, icon: DataAnalysis, tone: "blue", trend: "" },
  { label: "已完成任务", value: stats.value?.total_completed ?? "待生成", desc: `取消 ${stats.value?.total_cancelled ?? 0} 项`, icon: TrendCharts, tone: "green", trend: "" },
  { label: "逾期任务", value: stats.value?.total_overdue ?? "待生成", desc: "需要持续跟进", icon: Refresh, tone: "orange", trend: "" },
  { label: "待审核风险", value: stats.value?.total_pending_review ?? "待生成", desc: `知识空缺 ${stats.value?.total_knowledge_gap ?? 0} 项`, icon: DataAnalysis, tone: "red", trend: "" },
]);
const reportTitle = computed(() => {
  if (!summary.value) return `${range.value === "本周" ? "周报" : "日报"}内容`;
  return summary.value.summary_type === "weekly" ? "周报内容" : "日报内容";
});

// ─── 日期区间计算 ──────────────────────────────────────────────────────────────
function toDateStr(d) {
  return d.toISOString().slice(0, 10);
}
const chartDateRange = computed(() => {
  const today = new Date();
  if (range.value === "今日") {
    return { date_start: toDateStr(today), date_end: toDateStr(today) };
  }
  const monday = new Date(today);
  monday.setDate(today.getDate() - today.getDay() + (today.getDay() === 0 ? -6 : 1));
  return { date_start: toDateStr(monday), date_end: toDateStr(today) };
});

// ─── 图表数据 ──────────────────────────────────────────────────────────────────
const trendData = ref({ points: [], days: 14 });
const typeData = ref({ items: [], total: 0 });
const riskData = ref({ items: [], total: 0 });
const assigneeData = ref({ items: [] });
const chartLoading = ref(false);

const trendMaxCreated = computed(() => Math.max(...trendData.value.points.map((p) => p.created), 1));
const trendMaxCompleted = computed(() => Math.max(...trendData.value.points.map((p) => p.completed), 1));
const trendDisplayMax = computed(() => Math.max(trendMaxCreated.value, trendMaxCompleted.value));

// 趋势图显示最近 14 天，但仅渲染最后 7 点（节省空间）
const trendPoints = computed(() => trendData.value.points.slice(-7));

function trendBarH(value) {
  return Math.round((value / trendDisplayMax.value) * 100) + "%";
}
function typeBarW(pct) {
  return pct + "%";
}

// ─── 历史报告 ──────────────────────────────────────────────────────────────────
const reports = ref([]);
const reportsTotal = ref(0);
const listLoading = ref(false);

// 详情抽屉
const detailDrawerVisible = ref(false);
const selectedReport = ref(null);
const detailLoading = ref(false);
const downloadingId = ref(null);

// ─── 生命周期 ──────────────────────────────────────────────────────────────────
let active = true;

async function loadCharts() {
  chartLoading.value = true;
  try {
    const params = chartDateRange.value;
    const [trend, type, risk, assignee] = await Promise.all([
      getChartTrend(14),
      getChartType(params),
      getChartRisk(params),
      getChartAssignee(params),
    ]);
    trendData.value = trend;
    typeData.value = type;
    riskData.value = risk;
    assigneeData.value = assignee;
  } catch (err) {
    if (active) ElMessage.error(err.message || "加载图表数据失败");
  } finally {
    if (active) chartLoading.value = false;
  }
}

async function loadReports() {
  listLoading.value = true;
  try {
    const result = await getReportHistory({ page: 1, page_size: 10 });
    if (active) {
      reports.value = result.items || [];
      reportsTotal.value = result.total || 0;
    }
  } catch (err) {
    if (active) {
      reports.value = [];
      ElMessage.error(err.message || "加载报告记录失败");
    }
  } finally {
    if (active) listLoading.value = false;
  }
}

async function loadPageData() {
  await Promise.all([loadCharts(), loadReports()]);
}

async function generateReport() {
  const token = ++generationToken;
  generating.value = true;
  try {
    const result = await getSummary({
      type: range.value === "本周" ? "weekly" : "daily",
      write_notif: true,
    });
    if (!active || token !== generationToken) return;
    summary.value = result;
    ElMessage.success(`${result.summary_type === "weekly" ? "周报" : "日报"}已生成`);
    // 生成后立即刷新历史列表，让新报告出现在下方记录中
    await loadReports();
  } catch (err) {
    if (active && token === generationToken) {
      ElMessage.error(err.message || "生成报告失败");
    }
  } finally {
    // 无论早退出还是正常完成，都重置加载状态
    if (active) generating.value = false;
  }
}

async function openReportDetail(item) {
  detailDrawerVisible.value = true;
  selectedReport.value = null;
  detailLoading.value = true;
  try {
    selectedReport.value = await getReportDetail(item.id);
  } catch (err) {
    ElMessage.error(err.message || "加载报告详情失败");
    detailDrawerVisible.value = false;
  } finally {
    detailLoading.value = false;
  }
}

async function handleDownload(item, format) {
  downloadingId.value = `${item.id}-${format}`;
  try {
    await downloadReport(item.id, format);
    ElMessage.success(`${format === "word" ? "Word" : "PDF"} 已下载`);
  } catch (err) {
    ElMessage.error(err.message || "下载失败");
  } finally {
    downloadingId.value = null;
  }
}

onMounted(loadPageData);

watch(range, () => {
  summary.value = null;
  loadCharts();
});

onBeforeUnmount(() => {
  active = false;
  generationToken += 1;
});
</script>

<template>
  <PageHeader title="统计报告" desc="查看任务执行情况，按需手动生成日报或周报。" eyebrow="REPORTING">
    <el-select v-model="range" style="width: 100px"><el-option label="本周" value="本周" /><el-option label="今日" value="今日" /></el-select>
    <button class="secondary-btn" :disabled="chartLoading || listLoading" @click="loadPageData"><el-icon><Refresh /></el-icon>刷新</button>
    <button class="primary-btn" :disabled="generating" @click="generateReport"><el-icon><Plus /></el-icon>{{ generating ? "生成中..." : "生成报告" }}</button>
  </PageHeader>

  <!-- 概览指标 -->
  <div class="metrics-grid" v-loading="generating">
    <MetricCard v-for="item in metrics" :key="item.label" v-bind="item" />
  </div>

  <!-- 生成的报告正文 -->
  <section class="card report-content-card" v-loading="generating">
    <div class="card-head">
      <div><h3>{{ reportTitle }}</h3><p>{{ stats?.date_range || "请选择日报/周报并点击生成报告。" }}</p></div>
      <span class="chip-note">通知 ID：{{ summary?.notification_id ?? "未生成" }}</span>
    </div>
    <div v-if="summary" class="report-content">
      <p class="report-narrative">{{ summary.narrative }}</p>
      <div class="summary-breakdown">
        <div>
          <strong>按任务类型</strong>
          <span v-for="typeItem in summary.stats.by_type" :key="typeItem.type">{{ typeLabel(typeItem.type) }}：{{ typeItem.count }}</span>
          <span v-if="!summary.stats.by_type.length">暂无类型数据</span>
        </div>
        <div>
          <strong>按负责人</strong>
          <span v-for="assigneeItem in summary.stats.by_assignee.slice(0, 8)" :key="assigneeItem.assignee_id">
            {{ assigneeItem.name }}：完成 {{ assigneeItem.completed }}/{{ assigneeItem.total }}，逾期 {{ assigneeItem.overdue }}
          </span>
          <span v-if="!summary.stats.by_assignee.length">暂无负责人数据</span>
        </div>
      </div>
    </div>
    <div v-else class="report-placeholder">
      <strong>尚未生成报告</strong>
      <span>选择"今日"或"本周"，点击右上角"生成报告"后，报告正文会显示在这里。</span>
    </div>
  </section>

  <!-- 图表区域：趋势 + 类型分布 -->
  <div class="report-grid" v-loading="chartLoading">
    <!-- 趋势折线图（CSS 柱状实现） -->
    <section class="card">
      <div class="card-head">
        <div><h3>任务完成趋势</h3><p>最近 7 天新增任务与完成数量</p></div>
        <span class="chart-note"><i class="dot-blue"></i>新增 <i class="dot-green"></i>已完成</span>
      </div>
      <div class="report-chart">
        <div v-for="point in trendPoints" :key="point.date">
          <span>{{ point.created }}</span>
          <i :style="{ height: trendBarH(point.created) }"></i>
          <b :style="{ height: trendBarH(point.completed) }"></b>
          <small>{{ point.date }}</small>
        </div>
        <div v-if="!trendPoints.length" class="chart-empty">暂无数据</div>
      </div>
    </section>

    <!-- 任务类型分布 -->
    <section class="card category-card">
      <div class="card-head"><div><h3>任务类型分布</h3><p>{{ range }}新增任务构成（共 {{ typeData.total }} 条）</p></div></div>
      <div class="category-list">
        <div v-for="typeItem in typeData.items.slice(0, 6)" :key="typeItem.type">
          <span>{{ typeItem.label }}</span>
          <i><b :style="{ width: typeBarW(typeItem.pct) }"></b></i>
          <strong>{{ typeItem.count }}</strong>
        </div>
        <div v-if="!typeData.items.length" class="chart-empty">暂无数据</div>
      </div>
    </section>
  </div>

  <!-- 图表区域：风险分布 + 负责人排行 -->
  <div class="report-grid lower" v-loading="chartLoading">
    <!-- 风险分布 -->
    <section class="card">
      <div class="card-head"><div><h3>风险处理概览</h3><p>{{ range }}风险分级与审核情况（共 {{ riskData.total }} 条）</p></div></div>
      <div class="risk-summary">
        <div v-for="riskItem in riskData.items" :key="riskItem.level">
          <b :class="riskItem.level"></b>
          <strong>{{ riskItem.count }}</strong>
          <span>{{ riskItem.label }}</span>
          <small>已审核 {{ riskItem.reviewed }} 项</small>
        </div>
      </div>
    </section>

    <!-- 负责人排行 -->
    <section class="card">
      <div class="card-head"><div><h3>负责人完成排行</h3><p>{{ range }}任务完成率 Top 10</p></div></div>
      <div class="assignee-rank" v-if="assigneeData.items.length">
        <div v-for="(person, idx) in assigneeData.items" :key="person.name" class="rank-row">
          <span class="rank-no" :class="{ top3: idx < 3 }">{{ idx + 1 }}</span>
          <span class="rank-name">{{ person.name }}</span>
          <div class="rank-bar-wrap">
            <div class="rank-bar" :style="{ width: person.completion_rate + '%' }"></div>
          </div>
          <span class="rank-rate">{{ person.completion_rate }}%</span>
          <span class="rank-detail">{{ person.completed }}/{{ person.total }}</span>
        </div>
      </div>
      <div v-else class="chart-empty">暂无数据</div>
    </section>
  </div>

  <!-- 历史报告列表 -->
  <section class="card history-card">
    <div class="card-head">
      <div><h3>日报与周报</h3><p>手动生成后的报告通知记录（共 {{ reportsTotal }} 条）</p></div>
      <button class="text-link" @click="loadReports"><el-icon><Refresh /></el-icon></button>
    </div>
    <div class="report-list" v-loading="listLoading">
      <div v-for="reportItem in reports" :key="reportItem.id">
        <div class="report-icon" :class="reportItem.kind"><el-icon><DataAnalysis /></el-icon></div>
        <p class="report-info" @click="openReportDetail(reportItem)">
          <strong>{{ reportItem.title }}</strong>
          <span>{{ formatDateTime(reportItem.created_at) }} · {{ reportItem.kind_label }} · {{ reportItem.status }}</span>
          <em>{{ reportItem.preview }}</em>
        </p>
        <div class="dl-btns">
          <button
            class="dl-btn"
            title="下载 Word"
            :disabled="downloadingId === `${reportItem.id}-word`"
            @click.stop="handleDownload(reportItem, 'word')"
          ><el-icon><Download /></el-icon>Word</button>
          <button
            class="dl-btn pdf"
            title="下载 PDF"
            :disabled="downloadingId === `${reportItem.id}-pdf`"
            @click.stop="handleDownload(reportItem, 'pdf')"
          ><el-icon><Download /></el-icon>PDF</button>
        </div>
      </div>
      <div v-if="!reports.length && !listLoading" class="report-empty">暂无报告记录，点击"生成报告"创建</div>
    </div>
  </section>

  <!-- 报告详情抽屉 -->
  <el-drawer v-model="detailDrawerVisible" title="报告详情" size="480px" destroy-on-close>
    <div v-loading="detailLoading" class="detail-body">
      <template v-if="selectedReport">
        <div class="detail-meta">
          <span class="meta-tag">{{ selectedReport.kind === "daily_summary" ? "日报" : "周报" }}</span>
          <span class="meta-time">{{ formatDateTime(selectedReport.created_at) }}</span>
          <span class="meta-status">{{ selectedReport.status }}</span>
        </div>
        <h2 class="detail-title">{{ selectedReport.title }}</h2>
        <p class="detail-content">{{ selectedReport.content }}</p>
        <div class="detail-actions">
          <button class="primary-btn" :disabled="downloadingId === `${selectedReport.id}-word`" @click="handleDownload(selectedReport, 'word')">
            <el-icon><Download /></el-icon>下载 Word
          </button>
          <button class="secondary-btn" :disabled="downloadingId === `${selectedReport.id}-pdf`" @click="handleDownload(selectedReport, 'pdf')">
            <el-icon><Download /></el-icon>下载 PDF
          </button>
        </div>
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
/* 生成的报告正文卡片 */
.report-content-card { margin-top: 14px; }
.report-content { padding: 0 16px 16px; }
.report-narrative { color: #4d5d73; font-size: 12px; line-height: 1.9; white-space: pre-wrap; }
.summary-breakdown { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 14px; }
.summary-breakdown div { padding: 12px; border-radius: 8px; background: #f8fafc; }
.summary-breakdown strong,.summary-breakdown span { display: block; }
.summary-breakdown strong { margin-bottom: 8px; color: #4f5f73; font-size: 11px; }
.summary-breakdown span { color: #7f8b9a; font-size: 10px; line-height: 1.8; }
.report-placeholder { display: grid; gap: 7px; padding: 28px 16px 30px; border-top: 1px solid #eef1f4; color: #8a96a6; text-align: center; }
.report-placeholder strong { color: #526176; font-size: 13px; }
.report-placeholder span { font-size: 11px; }

/* 图表布局 */
.report-grid { display: grid; margin-top: 14px; grid-template-columns: 1.46fr .84fr; gap: 14px; }
.report-grid.lower { grid-template-columns: 1fr 1fr; }

/* 图例 */
.chart-note { display: inline-flex; align-items: center; gap: 6px; color: #9ba5b2; font-size: 10px; }
.dot-blue { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #5d91ef; }
.dot-green { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #4cbc95; margin-left: 5px; }
.chip-note { display: inline-flex; align-items: center; gap: 6px; color: #9ba5b2; font-size: 10px; }
.chart-empty { display: flex; align-items: center; justify-content: center; height: 80px; color: #b0b8c4; font-size: 11px; }

/* 趋势柱状图 */
.report-chart { display: flex; height: 182px; align-items: end; justify-content: space-around; padding: 15px 18px 25px; border-top: 1px solid #f0f2f5; background: repeating-linear-gradient(to bottom,#eff2f5 0,#eff2f5 1px,transparent 1px,transparent 39px); }
.report-chart > div { position: relative; display: flex; width: 45px; height: 100%; align-items: end; justify-content: center; gap: 4px; }
.report-chart i,.report-chart b { display: block; width: 13px; border-radius: 3px 3px 0 0; transition: height 0.4s ease; }
.report-chart i { background: #6397f0; }
.report-chart b { background: #50bd96; }
.report-chart small { position: absolute; bottom: -18px; color: #99a3b1; font-size: 9px; }
.report-chart span { position: absolute; top: -13px; color: #7f8b9b; font-size: 9px; }

/* 类型分布条形图 */
.category-card .card-head { padding-bottom: 4px; }
.category-list { display: grid; gap: 17px; padding: 9px 18px 19px; }
.category-list > div { display: grid; align-items: center; grid-template-columns: 70px 1fr 26px; gap: 8px; }
.category-list span { color: #748195; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.category-list i { height: 6px; overflow: hidden; border-radius: 5px; background: #eef1f5; }
.category-list b { display: block; height: 100%; border-radius: 5px; background: linear-gradient(90deg,#3979e9,#77a8f7); transition: width 0.4s ease; }
.category-list strong { color: #667589; font-size: 11px; text-align: right; }

/* 风险分布 */
.risk-summary { display: grid; padding: 9px 16px 18px; grid-template-columns: repeat(4,1fr); gap: 8px; }
.risk-summary > div { position: relative; padding: 13px 12px; overflow: hidden; border: 1px solid #edf0f3; border-radius: 8px; }
.risk-summary b { position: absolute; top: 0; right: 0; left: 0; height: 3px; }
.risk-summary b.critical { background: #e45b5b; }
.risk-summary b.high { background: #ee9143; }
.risk-summary b.medium { background: #deb33e; }
.risk-summary b.low { background: #3eb389; }
.risk-summary strong,.risk-summary span,.risk-summary small { display: block; }
.risk-summary strong { color: #3e4c61; font-size: 20px; }
.risk-summary span { margin-top: 5px; color: #6f7d90; font-size: 11px; }
.risk-summary small { margin-top: 9px; color: #a0a9b5; font-size: 9px; }

/* 负责人排行 */
.assignee-rank { padding: 6px 16px 14px; }
.rank-row { display: grid; grid-template-columns: 20px 70px 1fr 36px 50px; align-items: center; gap: 8px; padding: 5px 0; border-top: 1px solid #f2f4f7; }
.rank-no { font-size: 10px; font-weight: 700; color: #aab3be; text-align: center; }
.rank-no.top3 { color: #3e78e0; }
.rank-name { font-size: 11px; color: #566378; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rank-bar-wrap { height: 5px; border-radius: 3px; background: #eef1f5; overflow: hidden; }
.rank-bar { height: 100%; border-radius: 3px; background: linear-gradient(90deg,#3979e9,#77a8f7); transition: width 0.4s ease; }
.rank-rate { font-size: 10px; font-weight: 700; color: #3e78e0; text-align: right; }
.rank-detail { font-size: 9px; color: #a0abb8; text-align: right; }

/* 历史报告列表 */
.history-card { margin-top: 14px; }
.report-list { padding: 0 15px 9px; }
.report-list > div { display: flex; align-items: center; gap: 10px; padding: 10px 2px; border-top: 1px solid #eef1f4; }
.report-icon { display: grid; width: 29px; height: 29px; flex: none; place-items: center; border-radius: 7px; color: #3476e5; background: #edf4ff; }
.report-icon.weekly_summary { color: #1e8f6f; background: #e8f7f2; }
.report-info { flex: 1; cursor: pointer; min-width: 0; }
.report-info:hover strong { color: #3476e5; }
.report-list strong,.report-list span,.report-list em { display: block; }
.report-list strong { color: #566377; font-size: 11px; }
.report-list span { margin-top: 2px; color: #9ca5b2; font-size: 9px; }
.report-list em { margin-top: 3px; color: #b0b9c5; font-size: 9px; font-style: normal; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dl-btns { display: flex; gap: 5px; flex-shrink: 0; }
.dl-btn { display: inline-flex; align-items: center; gap: 3px; padding: 3px 8px; border: 1px solid #d4dae3; border-radius: 5px; font-size: 10px; color: #5c7094; background: none; cursor: pointer; white-space: nowrap; }
.dl-btn:hover:not(:disabled) { border-color: #3476e5; color: #3476e5; }
.dl-btn.pdf { color: #c0392b; }
.dl-btn.pdf:hover:not(:disabled) { border-color: #c0392b; }
.dl-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.report-empty { justify-content: center; color: #a5afbb; font-size: 11px; padding: 18px 0; }

/* 详情抽屉 */
.detail-body { padding: 0 4px; }
.detail-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.meta-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; background: #edf4ff; color: #3476e5; }
.meta-time { font-size: 11px; color: #9aa3b1; }
.meta-status { font-size: 10px; color: #9aa3b1; margin-left: auto; }
.detail-title { font-size: 15px; font-weight: 700; color: #3a4a5c; margin-bottom: 14px; line-height: 1.4; }
.detail-content { font-size: 12px; line-height: 1.9; color: #4d5d73; white-space: pre-wrap; background: #f8fafc; border-radius: 8px; padding: 14px 16px; margin-bottom: 20px; }
.detail-actions { display: flex; gap: 10px; }
</style>
