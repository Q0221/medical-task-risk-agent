<script setup>
import { onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  CircleCheck,
  Document,
  Edit,
  Plus,
  Search,
  View,
} from "@element-plus/icons-vue";
import PageHeader from "../components/PageHeader.vue";
import {
  archiveGap,
  archiveSop,
  createSop,
  getGapDetail,
  getKnowledgeStats,
  getSopCategories,
  getSopDetail,
  listGaps,
  listSops,
  newSopVersion,
  processGap,
  queryKnowledge,
  reviewGap,
  updateSop,
} from "../api/knowledge.js";
import { currentUserId } from "../store/app.js";
import { formatDateTime } from "../utils/mappers.js";

// ---------------------------------------------------------------------------
// 总览统计
// ---------------------------------------------------------------------------
const stats = ref({ sop_total: 0, sop_active: 0, sop_draft: 0, gap_open: 0, gap_in_progress: 0, gap_resolved: 0, recent_30d_hits: 0 });

// ---------------------------------------------------------------------------
// Tab 切换
// ---------------------------------------------------------------------------
const activeTab = ref("sop"); // "sop" | "gap" | "archive"

// ---------------------------------------------------------------------------
// RAG 问答面板
// ---------------------------------------------------------------------------
const question = ref("不良事件发生后应该在多少天内上报？负责人是谁？");
const taskId = ref("");
const knowledgeLoading = ref(false);
const knowledgeResult = ref(null);

async function askKnowledge() {
  const q = question.value.trim();
  if (!q) { ElMessage.warning("请输入 SOP 问题"); return; }
  knowledgeLoading.value = true;
  try {
    knowledgeResult.value = await queryKnowledge({
      question: q,
      task_id: taskId.value ? Number(taskId.value) : undefined,
      user_id: currentUserId.value,
    });
    // 若生成了新的知识空缺，刷新空缺列表和统计
    if (knowledgeResult.value?.is_gap) {
      await Promise.all([loadStats(), loadGaps()]);
      ElMessage.warning("检测到知识空缺，已自动创建补充任务");
    }
  } catch (e) {
    ElMessage.error(e.message || "知识问答失败");
  } finally {
    knowledgeLoading.value = false;
  }
}

// ---------------------------------------------------------------------------
// SOP 文档列表
// ---------------------------------------------------------------------------
const sopSearch = ref("");
const sopCategoryFilter = ref("");
const sopPage = ref(1);
const sopPageSize = ref(20);
const sopLoading = ref(false);
const sops = ref([]);
const sopTotal = ref(0);
const sopCategories = ref([]);

async function loadSops() {
  sopLoading.value = true;
  try {
    const data = await listSops({
      page: sopPage.value,
      page_size: sopPageSize.value,
      search: sopSearch.value || undefined,
      category: sopCategoryFilter.value || undefined,
    });
    sops.value = data.items;
    sopTotal.value = data.total;
  } catch {
    sops.value = [];
    sopTotal.value = 0;
  } finally {
    sopLoading.value = false;
  }
}

function onSopSearch() { sopPage.value = 1; loadSops(); }

// ---------------------------------------------------------------------------
// 知识空缺列表
// ---------------------------------------------------------------------------
const gapSearch = ref("");
const gapStatusFilter = ref("");
const gapPage = ref(1);
const gapPageSize = ref(20);
const gapLoading = ref(false);
const gaps = ref([]);
const gapTotal = ref(0);

async function loadGaps() {
  gapLoading.value = true;
  try {
    const data = await listGaps({
      page: gapPage.value,
      page_size: gapPageSize.value,
      search: gapSearch.value || undefined,
      status: gapStatusFilter.value || undefined,
    });
    gaps.value = data.items;
    gapTotal.value = data.total;
  } catch {
    gaps.value = [];
    gapTotal.value = 0;
  } finally {
    gapLoading.value = false;
  }
}

function onGapSearch() { gapPage.value = 1; loadGaps(); }

// ---------------------------------------------------------------------------
// 归档记录（已关闭的 Gap）
// ---------------------------------------------------------------------------
const archiveLoading = ref(false);
const archives = ref([]);
const archiveTotal = ref(0);
const archivePage = ref(1);

async function loadArchives() {
  archiveLoading.value = true;
  try {
    const data = await listGaps({
      page: archivePage.value,
      page_size: 20,
      status: "closed",
    });
    archives.value = data.items;
    archiveTotal.value = data.total;
  } catch {
    archives.value = [];
    archiveTotal.value = 0;
  } finally {
    archiveLoading.value = false;
  }
}

// ---------------------------------------------------------------------------
// 统计数据
// ---------------------------------------------------------------------------
async function loadStats() {
  try { stats.value = await getKnowledgeStats(); } catch { /* 保持默认 */ }
}

// ---------------------------------------------------------------------------
// SOP 详情抽屉
// ---------------------------------------------------------------------------
const sopDetailOpen = ref(false);
const sopDetailLoading = ref(false);
const selectedSop = ref(null);

async function openSopDetail(item) {
  sopDetailOpen.value = true;
  sopDetailLoading.value = true;
  selectedSop.value = item;
  try {
    selectedSop.value = await getSopDetail(item.id);
  } catch { /* 保持列表行数据 */ }
  finally { sopDetailLoading.value = false; }
}

// ---------------------------------------------------------------------------
// 新建 SOP 抽屉
// ---------------------------------------------------------------------------
const createSopOpen = ref(false);
const createSopLoading = ref(false);
const createSopForm = ref({ code: "", title: "", category: "", department: "", version: "v1.0", tags: "", content: "", status: "active" });

async function submitCreateSop() {
  if (!createSopForm.value.code || !createSopForm.value.title) {
    ElMessage.warning("SOP 编号和标题为必填"); return;
  }
  createSopLoading.value = true;
  try {
    await createSop({
      ...createSopForm.value,
      tags: createSopForm.value.tags ? createSopForm.value.tags.split(/[,，\s]+/).filter(Boolean) : [],
    });
    ElMessage.success("SOP 文档已创建");
    createSopOpen.value = false;
    await Promise.all([loadSops(), loadStats()]);
    Object.assign(createSopForm.value, { code: "", title: "", category: "", department: "", version: "v1.0", tags: "", content: "", status: "active" });
  } catch (e) {
    ElMessage.error(e.message || "创建失败");
  } finally {
    createSopLoading.value = false;
  }
}

// ---------------------------------------------------------------------------
// 发布新版本抽屉
// ---------------------------------------------------------------------------
const newVersionOpen = ref(false);
const newVersionLoading = ref(false);
const newVersionForm = ref({ version: "", change_summary: "", content: "" });
const newVersionTarget = ref(null);

function openNewVersion(item) {
  newVersionTarget.value = item;
  newVersionForm.value = { version: "", change_summary: "", content: item.content || "" };
  newVersionOpen.value = true;
}

async function submitNewVersion() {
  if (!newVersionForm.value.version) { ElMessage.warning("请填写新版本号"); return; }
  newVersionLoading.value = true;
  try {
    await newSopVersion(newVersionTarget.value.id, newVersionForm.value);
    ElMessage.success("新版本已发布");
    newVersionOpen.value = false;
    await loadSops();
  } catch (e) {
    ElMessage.error(e.message || "发布失败");
  } finally { newVersionLoading.value = false; }
}

async function doArchiveSop(item) {
  await ElMessageBox.confirm(`确认归档「${item.title}」？归档后不可检索。`, "归档确认", { type: "warning" });
  try {
    await archiveSop(item.id);
    ElMessage.success("已归档");
    await Promise.all([loadSops(), loadStats()]);
  } catch (e) {
    if (e !== "cancel") ElMessage.error(e.message || "操作失败");
  }
}

// ---------------------------------------------------------------------------
// Gap 处理抽屉
// ---------------------------------------------------------------------------
const gapDetailOpen = ref(false);
const gapDetailLoading = ref(false);
const selectedGap = ref(null);
const gapResolutionNote = ref("");
const gapSubmitting = ref(false);

async function openGapDetail(item) {
  gapDetailOpen.value = true;
  gapDetailLoading.value = true;
  selectedGap.value = item;
  gapResolutionNote.value = item.resolution_note || "";
  try {
    selectedGap.value = await getGapDetail(item.id);
    gapResolutionNote.value = selectedGap.value.resolution_note || "";
  } catch { /* 保持列表行数据 */ }
  finally { gapDetailLoading.value = false; }
}

async function submitGapProcess(action) {
  if (!gapResolutionNote.value.trim()) { ElMessage.warning("请填写补充内容"); return; }
  gapSubmitting.value = true;
  try {
    await processGap(selectedGap.value.id, { resolution_note: gapResolutionNote.value, action });
    ElMessage.success(action === "save_draft" ? "草稿已保存" : "已提交审核");
    gapDetailOpen.value = false;
    await Promise.all([loadGaps(), loadStats()]);
  } catch (e) {
    ElMessage.error(e.message || "操作失败");
  } finally { gapSubmitting.value = false; }
}

async function submitGapReview(action) {
  const label = action === "approve" ? "通过并归档" : "驳回";
  await ElMessageBox.confirm(`确认${label}此知识空缺任务？`, "审核确认", { type: "warning" });
  try {
    await reviewGap(selectedGap.value.id, { action });
    ElMessage.success(action === "approve" ? "已审核通过" : "已驳回");
    gapDetailOpen.value = false;
    await Promise.all([loadGaps(), loadStats()]);
  } catch (e) {
    if (e !== "cancel") ElMessage.error(e.message || "操作失败");
  }
}

async function doArchiveGap(item) {
  await ElMessageBox.confirm("确认归档此知识空缺任务？", "确认", { type: "warning" });
  try {
    await archiveGap(item.id);
    ElMessage.success("已归档");
    await Promise.all([loadGaps(), loadStats()]);
  } catch (e) {
    if (e !== "cancel") ElMessage.error(e.message || "操作失败");
  }
}

// ---------------------------------------------------------------------------
// Tab 切换联动
// ---------------------------------------------------------------------------
watch(activeTab, (tab) => {
  if (tab === "sop") loadSops();
  else if (tab === "gap") loadGaps();
  else loadArchives();
});

// ---------------------------------------------------------------------------
// 状态标签
// ---------------------------------------------------------------------------
const GAP_STATUS_LABEL = { open: "待处理", in_progress: "处理中", resolved: "待审核", closed: "已归档" };
const GAP_STATUS_CLASS = { open: "waiting", in_progress: "processing", resolved: "review", closed: "done" };
const SOP_STATUS_LABEL = { active: "有效", draft: "草稿", archived: "已归档" };

function gapStatusLabel(s) { return GAP_STATUS_LABEL[s] ?? s; }
function gapStatusClass(s) { return GAP_STATUS_CLASS[s] ?? "processing"; }
function sopStatusLabel(s) { return SOP_STATUS_LABEL[s] ?? s; }
function confidenceClass(c) { return c == null ? "" : c < 0.5 ? "low" : c < 0.7 ? "mid" : "high"; }

// ---------------------------------------------------------------------------
// 初始化
// ---------------------------------------------------------------------------
onMounted(async () => {
  await Promise.all([loadStats(), loadSops(), getSopCategories().then(d => sopCategories.value = d.categories || []).catch(() => {})]);
});
</script>

<template>
  <PageHeader title="知识中心" desc="管理企业 SOP 与知识空缺任务，形成「检索 - 发现 - 补充 - 更新」的持续优化闭环。" eyebrow="KNOWLEDGE HUB">
    <button class="secondary-btn" @click="activeTab = 'sop'"><el-icon><Document /></el-icon>检索测试</button>
    <button class="primary-btn" @click="createSopOpen = true"><el-icon><Plus /></el-icon>新建 SOP</button>
  </PageHeader>

  <!-- 顶部横幅 -->
  <div class="knowledge-banner">
    <div>
      <span>KNOWLEDGE QUALITY</span>
      <h3>让每一次业务问答，都成为知识库变得更好的机会。</h3>
      <p>RAG Agent 自动识别低置信度检索与无有效 SOP 场景，并生成知识补充任务。</p>
    </div>
    <div class="quality-score">
      <strong>{{ stats.sop_active }}</strong>
      <span>有效 SOP</span>
    </div>
  </div>

  <!-- RAG 问答面板 -->
  <section class="card query-panel" v-loading="knowledgeLoading">
    <div class="query-inputs">
      <el-input v-model="question" type="textarea" :rows="3" placeholder="输入 SOP 问题或业务处置问题" />
      <div>
        <el-input v-model="taskId" placeholder="关联任务 ID（可选）" />
        <button class="primary-btn" @click="askKnowledge">开始问答</button>
      </div>
    </div>
    <div v-if="knowledgeResult" class="knowledge-result">
      <div class="result-head">
        <strong>回答置信度 {{ Math.round((knowledgeResult.confidence || 0) * 100) }}%</strong>
        <span :class="{ gap: knowledgeResult.is_gap }">
          {{ knowledgeResult.is_gap ? `知识空缺 #${knowledgeResult.gap_task_id || '-'}` : '已命中 SOP' }}
        </span>
      </div>
      <p>{{ knowledgeResult.answer }}</p>
      <div v-if="knowledgeResult.key_steps?.length" class="step-list">
        <span v-for="step in knowledgeResult.key_steps" :key="step">{{ step }}</span>
      </div>
      <div v-if="knowledgeResult.references?.length" class="reference-line">
        引用：{{ knowledgeResult.references.join(" / ") }}
      </div>
      <div v-if="knowledgeResult.hits?.length" class="hit-list">
        <div v-for="hit in knowledgeResult.hits" :key="hit.doc_id">
          <strong>{{ hit.title }}</strong>
          <span>{{ hit.doc_id }} · {{ Math.round(hit.score * 100) }}%</span>
          <p>{{ hit.snippet }}</p>
        </div>
      </div>
      <div v-if="knowledgeResult.is_gap" class="gap-reason">{{ knowledgeResult.gap_reason }}</div>
    </div>
  </section>

  <!-- 主内容区 -->
  <section class="card">
    <div class="tab-bar">
      <button class="tab-button" :class="{ active: activeTab === 'sop' }" @click="activeTab = 'sop'">
        SOP 知识库 <b>{{ stats.sop_active }}</b>
      </button>
      <button class="tab-button" :class="{ active: activeTab === 'gap' }" @click="activeTab = 'gap'">
        知识空缺任务 <b>{{ stats.gap_open + stats.gap_in_progress }}</b>
      </button>
      <button class="tab-button" :class="{ active: activeTab === 'archive' }" @click="activeTab = 'archive'">
        补充记录 <b>{{ stats.gap_resolved }}</b>
      </button>
    </div>

    <!-- ======================================== SOP Tab -->
    <template v-if="activeTab === 'sop'">
      <div class="toolbar">
        <el-input v-model="sopSearch" :prefix-icon="Search" placeholder="搜索 SOP 标题、编号或分类" clearable style="width:220px" @change="onSopSearch" @clear="onSopSearch" />
        <el-select v-model="sopCategoryFilter" placeholder="全部分类" clearable style="width:130px" @change="onSopSearch">
          <el-option v-for="cat in sopCategories" :key="cat" :label="cat" :value="cat" />
        </el-select>
        <span class="toolbar-spacer" />
        <span class="kb-update"><i></i> 共 {{ sopTotal }} 篇文档</span>
      </div>
      <table v-loading="sopLoading" class="list-table">
        <thead>
          <tr><th>文档信息</th><th>分类</th><th>维护部门</th><th>版本</th><th>最近更新</th><th>命中次数</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in sops" :key="item.id">
            <td>
              <strong class="table-title">{{ item.title }}</strong>
              <span class="table-sub">{{ item.code }} · {{ (item.tags || []).join(" / ") }}</span>
            </td>
            <td><span class="soft-chip blue">{{ item.category || "—" }}</span></td>
            <td>{{ item.department || "—" }}</td>
            <td>{{ item.version }}</td>
            <td>{{ formatDateTime(item.updated_at) }}</td>
            <td><span class="hit">{{ item.hit_count }}</span></td>
            <td><span class="sop-status" :class="item.status">{{ sopStatusLabel(item.status) }}</span></td>
            <td class="action-cell">
              <button class="ghost-btn" @click="openSopDetail(item)"><el-icon><View /></el-icon>查看</button>
              <button class="ghost-btn" @click="openNewVersion(item)"><el-icon><Edit /></el-icon>新版</button>
            </td>
          </tr>
          <tr v-if="!sopLoading && sops.length === 0">
            <td colspan="8" class="empty-row">暂无 SOP 文档</td>
          </tr>
        </tbody>
      </table>
      <div class="pagination-row">
        <span>共 {{ sopTotal }} 篇文档</span>
        <el-pagination v-model:current-page="sopPage" small background layout="prev, pager, next" :total="sopTotal" :page-size="sopPageSize" @current-change="loadSops" />
      </div>
    </template>

    <!-- ======================================== Gap Tab -->
    <template v-if="activeTab === 'gap'">
      <div class="toolbar">
        <el-input v-model="gapSearch" :prefix-icon="Search" placeholder="搜索知识空缺问题" clearable style="width:220px" @change="onGapSearch" @clear="onGapSearch" />
        <el-select v-model="gapStatusFilter" placeholder="全部状态" clearable style="width:130px" @change="onGapSearch">
          <el-option label="待处理" value="open" />
          <el-option label="处理中" value="in_progress" />
          <el-option label="待审核" value="resolved" />
        </el-select>
        <span class="toolbar-spacer" />
        <span class="kb-update"><i style="background:#f5a623"></i> 共 {{ gapTotal }} 条待处理</span>
      </div>
      <table v-loading="gapLoading" class="list-table">
        <thead>
          <tr><th>知识空缺任务</th><th>检索置信度</th><th>责任人</th><th>来源任务</th><th>创建时间</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in gaps" :key="item.id">
            <td>
              <strong class="table-title">{{ item.original_question }}</strong>
              <span class="table-sub">KG-{{ String(item.id).padStart(8, '0') }}</span>
            </td>
            <td>
              <span class="confidence" :class="confidenceClass(item.confidence)">
                {{ item.confidence != null ? Math.round(item.confidence * 100) + '%' : '—' }}
              </span>
            </td>
            <td>{{ item.assignee_name || `uid:${item.assignee_id}` }}</td>
            <td>{{ item.source_task_id ? `#${item.source_task_id}` : "直接提问" }}</td>
            <td>{{ formatDateTime(item.created_at) }}</td>
            <td><span class="gap-status" :class="gapStatusClass(item.status)">{{ gapStatusLabel(item.status) }}</span></td>
            <td class="action-cell">
              <button class="ghost-btn" @click="openGapDetail(item)"><el-icon><Edit /></el-icon>处理</button>
              <button class="ghost-btn danger" @click="doArchiveGap(item)">归档</button>
            </td>
          </tr>
          <tr v-if="!gapLoading && gaps.length === 0">
            <td colspan="7" class="empty-row">暂无知识空缺任务</td>
          </tr>
        </tbody>
      </table>
      <div class="pagination-row">
        <span>共 {{ gapTotal }} 条</span>
        <el-pagination v-model:current-page="gapPage" small background layout="prev, pager, next" :total="gapTotal" :page-size="gapPageSize" @current-change="loadGaps" />
      </div>
    </template>

    <!-- ======================================== Archive Tab -->
    <template v-if="activeTab === 'archive'">
      <div class="toolbar">
        <span class="toolbar-spacer" />
        <span class="kb-update"><el-icon><CircleCheck /></el-icon> 已归档 {{ archiveTotal }} 条记录</span>
      </div>
      <table v-loading="archiveLoading" class="list-table">
        <thead>
          <tr><th>原始问题</th><th>责任人</th><th>处理说明</th><th>归档时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in archives" :key="item.id">
            <td>
              <strong class="table-title">{{ item.original_question }}</strong>
              <span class="table-sub">KG-{{ String(item.id).padStart(8, '0') }}</span>
            </td>
            <td>{{ item.assignee_name || `uid:${item.assignee_id}` }}</td>
            <td class="resolution-cell">{{ item.resolution_note || "—" }}</td>
            <td>{{ formatDateTime(item.updated_at) }}</td>
          </tr>
          <tr v-if="!archiveLoading && archives.length === 0">
            <td colspan="4" class="empty-row">暂无归档记录</td>
          </tr>
        </tbody>
      </table>
      <div class="pagination-row">
        <span>共 {{ archiveTotal }} 条归档记录</span>
        <el-pagination v-model:current-page="archivePage" small background layout="prev, pager, next" :total="archiveTotal" :page-size="20" @current-change="loadArchives" />
      </div>
    </template>
  </section>

  <!-- ======================================================= SOP 详情抽屉 -->
  <el-drawer v-model="sopDetailOpen" size="560px" destroy-on-close>
    <template v-if="selectedSop" #header>
      <div class="drawer-title">
        <h3>{{ selectedSop.title }}</h3>
        <p>{{ selectedSop.code }} · {{ selectedSop.version }} · {{ selectedSop.department || '—' }}</p>
      </div>
    </template>
    <div v-if="sopDetailLoading"><el-skeleton :rows="5" animated /></div>
    <template v-else-if="selectedSop">
      <div class="detail-section">
        <h4>基本信息</h4>
        <div class="info-grid">
          <div class="info-item"><span>分类</span><strong>{{ selectedSop.category || '—' }}</strong></div>
          <div class="info-item"><span>版本</span><strong>{{ selectedSop.version }}</strong></div>
          <div class="info-item"><span>状态</span><strong>{{ sopStatusLabel(selectedSop.status) }}</strong></div>
          <div class="info-item"><span>命中次数</span><strong>{{ selectedSop.hit_count }}</strong></div>
        </div>
      </div>
      <div v-if="(selectedSop.tags || []).length" class="detail-section">
        <h4>标签</h4>
        <div class="chip-row">
          <span v-for="tag in selectedSop.tags" :key="tag" class="soft-chip blue">{{ tag }}</span>
        </div>
      </div>
      <div v-if="selectedSop.content" class="detail-section">
        <h4>文档内容</h4>
        <div class="content-box">{{ selectedSop.content }}</div>
      </div>
      <div class="drawer-footer">
        <button class="secondary-btn" @click="openNewVersion(selectedSop); sopDetailOpen = false">发布新版本</button>
        <button class="danger-btn" @click="doArchiveSop(selectedSop); sopDetailOpen = false">归档</button>
      </div>
    </template>
  </el-drawer>

  <!-- ======================================================= 新建 SOP 抽屉 -->
  <el-drawer v-model="createSopOpen" size="500px" title="新建 SOP 文档" destroy-on-close>
    <div class="form-body">
      <div class="form-row">
        <label>SOP 编号 <em>*</em></label>
        <el-input v-model="createSopForm.code" placeholder="如 SOP-ADV-002" />
      </div>
      <div class="form-row">
        <label>标题 <em>*</em></label>
        <el-input v-model="createSopForm.title" placeholder="SOP 文档标题" />
      </div>
      <div class="form-row two-col">
        <div>
          <label>分类</label>
          <el-input v-model="createSopForm.category" placeholder="如 设备异常" />
        </div>
        <div>
          <label>维护部门</label>
          <el-input v-model="createSopForm.department" placeholder="如 医学支持部" />
        </div>
      </div>
      <div class="form-row two-col">
        <div>
          <label>版本号</label>
          <el-input v-model="createSopForm.version" placeholder="v1.0" />
        </div>
        <div>
          <label>状态</label>
          <el-select v-model="createSopForm.status" style="width:100%">
            <el-option label="直接发布" value="active" />
            <el-option label="草稿" value="draft" />
          </el-select>
        </div>
      </div>
      <div class="form-row">
        <label>标签（逗号分隔）</label>
        <el-input v-model="createSopForm.tags" placeholder="如 报警,设备异常,患者安全" />
      </div>
      <div class="form-row">
        <label>文档内容</label>
        <el-input v-model="createSopForm.content" type="textarea" :rows="8" placeholder="粘贴 SOP 全文内容..." />
      </div>
    </div>
    <div class="drawer-footer">
      <button class="secondary-btn" @click="createSopOpen = false">取消</button>
      <button class="primary-btn" :disabled="createSopLoading" @click="submitCreateSop">
        {{ createSopLoading ? '保存中...' : '创建 SOP' }}
      </button>
    </div>
  </el-drawer>

  <!-- ======================================================= 发布新版本抽屉 -->
  <el-drawer v-model="newVersionOpen" size="460px" title="发布新版本" destroy-on-close>
    <div v-if="newVersionTarget" class="version-banner">
      <span>当前：{{ newVersionTarget.code }} · {{ newVersionTarget.version }}</span>
    </div>
    <div class="form-body">
      <div class="form-row">
        <label>新版本号 <em>*</em></label>
        <el-input v-model="newVersionForm.version" placeholder="如 v2.0" />
      </div>
      <div class="form-row">
        <label>变更说明</label>
        <el-input v-model="newVersionForm.change_summary" placeholder="简述本次版本的主要变更..." />
      </div>
      <div class="form-row">
        <label>新版本内容</label>
        <el-input v-model="newVersionForm.content" type="textarea" :rows="10" placeholder="保持不变则留空..." />
      </div>
    </div>
    <div class="drawer-footer">
      <button class="secondary-btn" @click="newVersionOpen = false">取消</button>
      <button class="primary-btn" :disabled="newVersionLoading" @click="submitNewVersion">
        {{ newVersionLoading ? '发布中...' : '发布新版本' }}
      </button>
    </div>
  </el-drawer>

  <!-- ======================================================= Gap 处理抽屉 -->
  <el-drawer v-model="gapDetailOpen" size="490px" destroy-on-close>
    <template v-if="selectedGap" #header>
      <div class="drawer-title">
        <h3>知识空缺处理</h3>
        <p>KG-{{ String(selectedGap.id).padStart(8, '0') }} · 由 RAG Agent 自动创建</p>
      </div>
    </template>
    <div v-if="gapDetailLoading"><el-skeleton :rows="4" animated /></div>
    <template v-else-if="selectedGap">
      <div class="gap-banner">
        <span>检索置信度</span>
        <strong>{{ selectedGap.confidence != null ? Math.round(selectedGap.confidence * 100) + '%' : '—' }}</strong>
        <small>{{ selectedGap.confidence != null && selectedGap.confidence < 0.55 ? '低于知识空缺阈值 55%' : '置信度不足，需补充' }}</small>
      </div>
      <div class="detail-section">
        <h4>原始问题</h4>
        <div class="note-box">{{ selectedGap.original_question }}</div>
      </div>
      <div class="detail-section">
        <h4>任务信息</h4>
        <div class="info-grid">
          <div class="info-item"><span>来源任务</span><strong>{{ selectedGap.source_task_id ? '#' + selectedGap.source_task_id : '直接提问' }}</strong></div>
          <div class="info-item"><span>责任人</span><strong>{{ selectedGap.assignee_name || `uid:${selectedGap.assignee_id}` }}</strong></div>
          <div class="info-item"><span>当前状态</span><strong>{{ gapStatusLabel(selectedGap.status) }}</strong></div>
          <div class="info-item"><span>创建时间</span><strong>{{ formatDateTime(selectedGap.created_at) }}</strong></div>
        </div>
      </div>
      <div v-if="selectedGap.rag_hits_snapshot?.length" class="detail-section">
        <h4>检索命中快照</h4>
        <div v-for="hit in selectedGap.rag_hits_snapshot.slice(0, 3)" :key="hit.doc_id" class="hit-snapshot">
          <span>{{ hit.title || hit.doc_id }}</span>
          <b>{{ Math.round((hit.score || 0) * 100) }}%</b>
        </div>
      </div>
      <div class="detail-section">
        <h4>补充内容</h4>
        <el-input
          v-model="gapResolutionNote"
          type="textarea"
          :rows="7"
          :disabled="selectedGap.status === 'closed'"
          placeholder="填写建议补充的知识内容、适用范围与引用依据..."
        />
      </div>
      <div v-if="selectedGap.status !== 'closed'" class="drawer-footer">
        <button class="secondary-btn" :disabled="gapSubmitting" @click="submitGapProcess('save_draft')">保存草稿</button>
        <template v-if="selectedGap.status === 'resolved'">
          <button class="secondary-btn" :disabled="gapSubmitting" @click="submitGapReview('reject')">驳回</button>
          <button class="primary-btn" :disabled="gapSubmitting" @click="submitGapReview('approve')">审核通过</button>
        </template>
        <button v-else class="primary-btn" :disabled="gapSubmitting" @click="submitGapProcess('submit_review')">
          {{ gapSubmitting ? '提交中...' : '提交审核' }}
        </button>
      </div>
      <div v-else class="closed-tip">该任务已归档关闭</div>
    </template>
  </el-drawer>
</template>

<style scoped>
/* 横幅 */
.knowledge-banner { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; padding: 18px 22px; overflow: hidden; border-radius: 13px; color: white; background: linear-gradient(105deg, #214b9c, #3277e3); box-shadow: 0 8px 17px rgba(37, 92, 187, 0.17); }
.knowledge-banner span { font-size: 9px; font-weight: 700; letter-spacing: 1.5px; opacity: 0.65; }
.knowledge-banner h3 { margin-top: 7px; font-size: 17px; }
.knowledge-banner p { margin-top: 8px; color: rgba(255,255,255,.68); font-size: 11px; }
.quality-score { display: grid; width: 86px; height: 86px; flex: none; place-content: center; border: 5px solid rgba(255,255,255,.27); border-radius: 50%; text-align: center; }
.quality-score strong { font-size: 22px; }
.quality-score span { margin-top: 2px; font-size: 8px; letter-spacing: 0; }
/* 工具栏 */
.kb-update { display: inline-flex; align-items: center; gap: 6px; color: #8c98a7; font-size: 10px; }
.kb-update i { width: 6px; height: 6px; border-radius: 50%; background: #2ab07c; flex-shrink: 0; }
/* 问答面板 */
.query-panel { margin-bottom: 14px; padding: 14px; }
.query-inputs { display: grid; grid-template-columns: 1fr 180px; gap: 12px; }
.query-inputs > div { display: grid; align-content: start; gap: 10px; }
.query-inputs .primary-btn { width: 100%; justify-content: center; }
.knowledge-result { margin-top: 13px; padding: 12px; border: 1px solid #e6ecf4; border-radius: 8px; background: #fbfdff; }
.result-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.result-head strong { color: #415066; font-size: 12px; }
.result-head span { padding: 4px 8px; border-radius: 12px; color: #278768; font-size: 10px; background: #eaf8f3; }
.result-head span.gap { color: #c06335; background: #fff1e7; }
.knowledge-result > p { margin-top: 10px; color: #5b687a; font-size: 12px; line-height: 1.8; }
.step-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.step-list span { padding: 5px 8px; border-radius: 6px; color: #4f6e98; font-size: 10px; background: #f1f6ff; }
.reference-line, .gap-reason { margin-top: 9px; color: #8b96a6; font-size: 10px; }
.hit-list { display: grid; gap: 7px; margin-top: 10px; }
.hit-list div { padding: 8px; border-radius: 7px; background: white; }
.hit-list strong, .hit-list span { display: block; }
.hit-list strong { color: #4e5d72; font-size: 11px; }
.hit-list span { margin-top: 4px; color: #9aa5b2; font-size: 9px; }
.hit-list p { margin-top: 5px; color: #7f8a9a; font-size: 10px; line-height: 1.6; }
/* 表格 */
.action-cell { display: flex; gap: 6px; white-space: nowrap; }
.empty-row { text-align: center; color: #b0b8c4; font-size: 12px; padding: 28px; }
.hit { color: #24976f; font-size: 11px; font-weight: 600; }
.confidence { display: inline-flex; padding: 3px 7px; border-radius: 10px; font-size: 10px; }
.confidence.low { color: #cd5555; background: #fff0f0; }
.confidence.mid { color: #b87d25; background: #fff6e7; }
.confidence.high { color: #2a8f5e; background: #eaf8f0; }
.resolution-cell { max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #5a6680; font-size: 11px; }
/* 状态标签 */
.sop-status { font-size: 10px; padding: 2px 8px; border-radius: 4px; }
.sop-status.active { color: #2a8f5e; background: #eaf8f0; }
.sop-status.draft { color: #9a7a2c; background: #fffbe6; }
.sop-status.archived { color: #8c98a8; background: #f0f3f6; }
.gap-status { font-size: 10px; padding: 2px 8px; border-radius: 4px; }
.gap-status.waiting { color: #c06335; background: #fff1e7; }
.gap-status.processing { color: #3372df; background: #eaf1ff; }
.gap-status.review { color: #7c3aed; background: #f3f0ff; }
.gap-status.done { color: #2a8f5e; background: #eaf8f0; }
.ghost-btn.danger { color: #c0392b; }
/* 抽屉通用 */
.drawer-title h3 { margin: 0; color: #394f6a; font-size: 15px; }
.drawer-title p { margin: 4px 0 0; color: #8c98a8; font-size: 11px; }
.detail-section { margin-top: 18px; }
.detail-section h4 { margin: 0 0 10px; color: #4a5569; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
.info-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.info-item { padding: 8px 12px; border-radius: 7px; background: #f5f8fc; }
.info-item span { display: block; color: #8c98a8; font-size: 10px; }
.info-item strong { display: block; margin-top: 3px; color: #445267; font-size: 13px; }
.chip-row { display: flex; flex-wrap: wrap; gap: 7px; }
/* SOP 内容框 */
.content-box { padding: 12px; border-radius: 8px; background: #f7f9fc; color: #5a6680; font-size: 11px; line-height: 1.8; white-space: pre-wrap; max-height: 350px; overflow-y: auto; }
.version-banner { margin-bottom: 16px; padding: 10px 14px; border-radius: 8px; background: #f0f5ff; color: #3968c8; font-size: 11px; }
/* Gap 抽屉 */
.gap-banner { padding: 12px 14px; border-radius: 8px; background: #fff6ed; }
.gap-banner span, .gap-banner small { display: block; color: #b9834d; font-size: 10px; }
.gap-banner strong { display: block; margin: 6px 0 3px; color: #db7a26; font-size: 23px; }
.note-box { padding: 10px 12px; border-radius: 8px; background: #f7f9fc; color: #5a6680; font-size: 12px; line-height: 1.7; }
.hit-snapshot { display: flex; align-items: center; justify-content: space-between; padding: 6px 10px; margin-bottom: 5px; border-radius: 6px; background: #f5f8fc; font-size: 11px; color: #5a6680; }
.hit-snapshot b { color: #3372df; }
.closed-tip { margin-top: 16px; padding: 10px; border-radius: 8px; background: #f0f3f6; color: #8c98a8; font-size: 12px; text-align: center; }
/* 表单 */
.form-body { padding: 0 0 80px; }
.form-row { margin-bottom: 16px; }
.form-row label { display: block; margin-bottom: 6px; color: #5a6680; font-size: 11px; font-weight: 500; }
.form-row label em { color: #e05c5c; font-style: normal; }
.form-row.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.drawer-footer { display: flex; gap: 10px; justify-content: flex-end; padding-top: 16px; border-top: 1px solid #edf0f4; margin-top: 16px; }
.danger-btn { padding: 7px 16px; border: 1px solid #e05c5c; border-radius: 7px; color: #e05c5c; font-size: 12px; background: white; cursor: pointer; }
.pagination-row { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; font-size: 11px; color: #8c95a3; }
</style>
