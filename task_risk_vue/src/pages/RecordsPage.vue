<script setup>
import { computed, onMounted, ref, watch } from "vue";
import {
  Files,
  Location,
  OfficeBuilding,
  Search,
  TrendCharts,
} from "@element-plus/icons-vue";
import PageHeader from "../components/PageHeader.vue";
import RiskBadge from "../components/RiskBadge.vue";
import {
  getHospitalDetail,
  getHospitalOptions,
  getProductDetail,
  getProductOptions,
  getRecordStats,
  listHospitals,
  listProducts,
} from "../api/records.js";
import {
  formatDateTime,
  riskLabel,
  statusClass,
  statusLabel,
  typeLabel,
} from "../utils/mappers.js";

// ---------------------------------------------------------------------------
// 总览统计
// ---------------------------------------------------------------------------
const stats = ref({ hospital_count: 0, product_count: 0, risk_task_count: 0, high_risk_hospital_count: 0, open_task_count: 0 });

// ---------------------------------------------------------------------------
// Tab 切换
// ---------------------------------------------------------------------------
const activeTab = ref("hospital"); // "hospital" | "product"

// ---------------------------------------------------------------------------
// 医院相关状态
// ---------------------------------------------------------------------------
const hospitalSearch = ref("");
const hospitalLevelFilter = ref("");
const hospitalRegionFilter = ref("");
const hospitalPage = ref(1);
const hospitalPageSize = ref(18);
const hospitalLoading = ref(false);
const hospitals = ref([]);
const hospitalTotal = ref(0);
const hospitalLevelOptions = ref([]);
const hospitalRegionOptions = ref([]);

// ---------------------------------------------------------------------------
// 产品相关状态
// ---------------------------------------------------------------------------
const productSearch = ref("");
const productCategoryFilter = ref("");
const productUnitFilter = ref("");
const productPage = ref(1);
const productPageSize = ref(18);
const productLoading = ref(false);
const products = ref([]);
const productTotal = ref(0);
const productCategoryOptions = ref([]);
const productUnitOptions = ref([]);

// ---------------------------------------------------------------------------
// 详情抽屉
// ---------------------------------------------------------------------------
const detailOpen = ref(false);
const detailLoading = ref(false);
const selectedItem = ref(null);
const detailType = ref("hospital"); // "hospital" | "product"

// ---------------------------------------------------------------------------
// 风险分 → 风险等级映射（医院 risk_score 0-100）
// ---------------------------------------------------------------------------
function riskScoreToLevel(score) {
  if (score >= 60) return "critical";
  if (score >= 30) return "high";
  if (score >= 10) return "medium";
  return "low";
}

// ---------------------------------------------------------------------------
// 数据加载
// ---------------------------------------------------------------------------
async function loadStats() {
  try {
    stats.value = await getRecordStats();
  } catch {
    // 保持默认值
  }
}

async function loadHospitals() {
  hospitalLoading.value = true;
  try {
    const data = await listHospitals({
      page: hospitalPage.value,
      page_size: hospitalPageSize.value,
      search: hospitalSearch.value || undefined,
      level: hospitalLevelFilter.value || undefined,
      region: hospitalRegionFilter.value || undefined,
    });
    hospitals.value = data.items;
    hospitalTotal.value = data.total;
  } catch {
    hospitals.value = [];
    hospitalTotal.value = 0;
  } finally {
    hospitalLoading.value = false;
  }
}

async function loadProducts() {
  productLoading.value = true;
  try {
    const data = await listProducts({
      page: productPage.value,
      page_size: productPageSize.value,
      search: productSearch.value || undefined,
      category: productCategoryFilter.value || undefined,
      business_unit: productUnitFilter.value || undefined,
    });
    products.value = data.items;
    productTotal.value = data.total;
  } catch {
    products.value = [];
    productTotal.value = 0;
  } finally {
    productLoading.value = false;
  }
}

async function loadFilterOptions() {
  try {
    const [hoOpts, prOpts] = await Promise.all([
      getHospitalOptions(),
      getProductOptions(),
    ]);
    hospitalLevelOptions.value = hoOpts.levels || [];
    hospitalRegionOptions.value = hoOpts.regions || [];
    productCategoryOptions.value = prOpts.categories || [];
    productUnitOptions.value = prOpts.business_units || [];
  } catch {
    // 筛选框为空也不影响基础功能
  }
}

// ---------------------------------------------------------------------------
// 打开详情抽屉
// ---------------------------------------------------------------------------
async function openHospitalDetail(item) {
  detailType.value = "hospital";
  detailOpen.value = true;
  detailLoading.value = true;
  selectedItem.value = item; // 先显示列表行数据，等详情加载完再替换
  try {
    selectedItem.value = await getHospitalDetail(item.id);
  } catch {
    // 保持列表行数据
  } finally {
    detailLoading.value = false;
  }
}

async function openProductDetail(item) {
  detailType.value = "product";
  detailOpen.value = true;
  detailLoading.value = true;
  selectedItem.value = item;
  try {
    selectedItem.value = await getProductDetail(item.id);
  } catch {
    // 保持列表行数据
  } finally {
    detailLoading.value = false;
  }
}

// ---------------------------------------------------------------------------
// 搜索重置分页
// ---------------------------------------------------------------------------
function onHospitalSearch() {
  hospitalPage.value = 1;
  loadHospitals();
}

function onProductSearch() {
  productPage.value = 1;
  loadProducts();
}

// ---------------------------------------------------------------------------
// Tab 切换时加载对应数据
// ---------------------------------------------------------------------------
watch(activeTab, (tab) => {
  if (tab === "hospital") loadHospitals();
  else loadProducts();
});

// ---------------------------------------------------------------------------
// 格式化最近动态时间
// ---------------------------------------------------------------------------
function formatLatest(dt) {
  if (!dt) return "暂无动态";
  const d = new Date(dt);
  const now = new Date();
  const diffMs = now - d;
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffDays === 0) return `今天 ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
  if (diffDays === 1) return "昨天";
  if (diffDays < 7) return `${diffDays} 天前`;
  return `${(d.getMonth() + 1).toString().padStart(2, "0")}-${d.getDate().toString().padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// 初始化
// ---------------------------------------------------------------------------
onMounted(async () => {
  await Promise.all([loadStats(), loadHospitals(), loadFilterOptions()]);
});
</script>

<template>
  <PageHeader title="业务档案" desc="汇总医院、产品与历史风险记录，为 Agent 风险判断提供可解释的长期业务记忆。" eyebrow="BUSINESS MEMORY">
    <button class="secondary-btn" @click="activeTab = 'product'">
      <el-icon><Files /></el-icon>产品档案
    </button>
  </PageHeader>

  <!-- 总览统计 -->
  <section class="records-overview">
    <div>
      <strong>{{ stats.hospital_count }}</strong>
      <span>合作医院</span>
      <small>{{ stats.high_risk_hospital_count }} 家有历史风险</small>
    </div>
    <div>
      <strong>{{ stats.product_count }}</strong>
      <span>在用产品档案</span>
      <small>累计任务来源</small>
    </div>
    <div>
      <strong>{{ stats.risk_task_count }}</strong>
      <span>历史风险任务</span>
      <small>高风险 + 紧急风险</small>
    </div>
    <div>
      <strong>{{ stats.open_task_count }}</strong>
      <span>当前进行中任务</span>
      <small>待跟进处理</small>
    </div>
  </section>

  <section class="card">
    <!-- Tab 切换 -->
    <div class="tab-bar">
      <button
        class="tab-button"
        :class="{ active: activeTab === 'hospital' }"
        @click="activeTab = 'hospital'"
      >
        医院档案 <b>{{ hospitalTotal }}</b>
      </button>
      <button
        class="tab-button"
        :class="{ active: activeTab === 'product' }"
        @click="activeTab = 'product'"
      >
        产品档案 <b>{{ productTotal }}</b>
      </button>
    </div>

    <!-- =============================================================== 医院 Tab -->
    <template v-if="activeTab === 'hospital'">
      <div class="toolbar">
        <el-input
          v-model="hospitalSearch"
          :prefix-icon="Search"
          placeholder="搜索医院名称或地区"
          clearable
          style="width: 220px"
          @change="onHospitalSearch"
          @clear="onHospitalSearch"
        />
        <el-select
          v-model="hospitalLevelFilter"
          placeholder="医院等级"
          clearable
          style="width: 130px"
          @change="onHospitalSearch"
        >
          <el-option v-for="lv in hospitalLevelOptions" :key="lv" :label="lv" :value="lv" />
        </el-select>
        <el-select
          v-model="hospitalRegionFilter"
          placeholder="地区"
          clearable
          style="width: 130px"
          @change="onHospitalSearch"
        >
          <el-option v-for="rg in hospitalRegionOptions" :key="rg" :label="rg" :value="rg" />
        </el-select>
        <span class="toolbar-spacer" />
        <span class="memory-label"><el-icon><TrendCharts /></el-icon> 长期业务记忆已启用</span>
      </div>

      <div v-loading="hospitalLoading" class="record-grid">
        <article
          v-for="item in hospitals"
          :key="item.id"
          class="record-card"
          @click="openHospitalDetail(item)"
        >
          <div class="record-top">
            <div class="hospital-icon">H</div>
            <RiskBadge :level="riskScoreToLevel(item.risk_score)" compact />
          </div>
          <h3>{{ item.name }}</h3>
          <p>
            <el-icon><Location /></el-icon>
            {{ item.region || "—" }} · {{ item.level || "—" }}
          </p>
          <div class="record-stats">
            <span><b>{{ item.task_total }}</b>累计任务</span>
            <span><b>{{ item.task_open }}</b>进行中</span>
            <span><b>{{ item.task_high_risk }}</b>历史风险</span>
          </div>
          <footer>
            <span>最近动态：{{ formatLatest(item.latest_task_at) }}</span>
            <button><el-icon><Files /></el-icon>查看档案</button>
          </footer>
        </article>
        <div v-if="!hospitalLoading && hospitals.length === 0" class="empty-tip">
          暂无匹配的医院档案
        </div>
      </div>

      <div class="pagination-row">
        <span>共 {{ hospitalTotal }} 家医院</span>
        <el-pagination
          v-model:current-page="hospitalPage"
          small
          background
          layout="prev, pager, next"
          :total="hospitalTotal"
          :page-size="hospitalPageSize"
          @current-change="loadHospitals"
        />
      </div>
    </template>

    <!-- =============================================================== 产品 Tab -->
    <template v-if="activeTab === 'product'">
      <div class="toolbar">
        <el-input
          v-model="productSearch"
          :prefix-icon="Search"
          placeholder="搜索产品名称或类别"
          clearable
          style="width: 220px"
          @change="onProductSearch"
          @clear="onProductSearch"
        />
        <el-select
          v-model="productCategoryFilter"
          placeholder="产品类别"
          clearable
          style="width: 130px"
          @change="onProductSearch"
        >
          <el-option v-for="cat in productCategoryOptions" :key="cat" :label="cat" :value="cat" />
        </el-select>
        <el-select
          v-model="productUnitFilter"
          placeholder="事业部"
          clearable
          style="width: 130px"
          @change="onProductSearch"
        >
          <el-option v-for="unit in productUnitOptions" :key="unit" :label="unit" :value="unit" />
        </el-select>
        <span class="toolbar-spacer" />
        <span class="memory-label"><el-icon><TrendCharts /></el-icon> 长期业务记忆已启用</span>
      </div>

      <div v-loading="productLoading" class="record-grid">
        <article
          v-for="item in products"
          :key="item.id"
          class="record-card product-card"
          @click="openProductDetail(item)"
        >
          <div class="record-top">
            <div class="product-icon">P</div>
            <span class="category-tag">{{ item.category || "通用" }}</span>
          </div>
          <h3>{{ item.name }}</h3>
          <p>
            <el-icon><OfficeBuilding /></el-icon>
            {{ item.business_unit || "—" }}
          </p>
          <div class="record-stats">
            <span><b>{{ item.task_total }}</b>累计任务</span>
            <span><b>{{ item.task_open }}</b>进行中</span>
            <span><b>{{ item.task_high_risk }}</b>高风险</span>
          </div>
          <footer>
            <span>最近动态：{{ formatLatest(item.latest_task_at) }}</span>
            <button><el-icon><Files /></el-icon>查看档案</button>
          </footer>
        </article>
        <div v-if="!productLoading && products.length === 0" class="empty-tip">
          暂无匹配的产品档案
        </div>
      </div>

      <div class="pagination-row">
        <span>共 {{ productTotal }} 款产品</span>
        <el-pagination
          v-model:current-page="productPage"
          small
          background
          layout="prev, pager, next"
          :total="productTotal"
          :page-size="productPageSize"
          @current-change="loadProducts"
        />
      </div>
    </template>
  </section>

  <!-- ================================================================= 详情抽屉 -->
  <el-drawer v-model="detailOpen" size="500px" destroy-on-close>
    <template v-if="selectedItem" #header>
      <div class="drawer-title">
        <h3>{{ selectedItem.name }}</h3>
        <p v-if="detailType === 'hospital'">
          {{ selectedItem.region }} · {{ selectedItem.level }} ·
          联系人 {{ selectedItem.contact_name || "—" }}
        </p>
        <p v-else>
          {{ selectedItem.category || "—" }} · {{ selectedItem.business_unit || "—" }}
        </p>
      </div>
    </template>

    <div v-if="detailLoading" class="drawer-loading">
      <el-skeleton :rows="6" animated />
    </div>

    <template v-else-if="selectedItem">
      <!-- 档案概览横幅 -->
      <div class="profile-banner">
        <div :class="detailType === 'hospital' ? 'hospital-icon large' : 'product-icon large'">
          {{ detailType === "hospital" ? "H" : "P" }}
        </div>
        <div>
          <strong v-if="detailType === 'hospital'">
            风险分 {{ selectedItem.risk_score }} / 100
          </strong>
          <strong v-else>{{ selectedItem.category || "通用产品" }}</strong>
          <span>{{ selectedItem.code }}</span>
        </div>
        <RiskBadge
          v-if="detailType === 'hospital'"
          :level="riskScoreToLevel(selectedItem.risk_score)"
        />
      </div>

      <!-- 业务概况 -->
      <div class="detail-section">
        <h4>业务概况</h4>
        <div class="info-grid">
          <div class="info-item"><span>累计任务</span><strong>{{ selectedItem.task_total }} 项</strong></div>
          <div class="info-item"><span>进行中任务</span><strong>{{ selectedItem.task_open }} 项</strong></div>
          <div class="info-item"><span>历史风险</span><strong>{{ selectedItem.task_high_risk }} 项</strong></div>
          <div class="info-item">
            <span>{{ detailType === "hospital" ? "风险分" : "最近更新" }}</span>
            <strong>
              {{ detailType === "hospital"
                  ? selectedItem.risk_score
                  : formatDateTime(selectedItem.updated_at) }}
            </strong>
          </div>
        </div>
      </div>

      <!-- 联系信息（医院专属） -->
      <div v-if="detailType === 'hospital' && selectedItem.contact_phone" class="detail-section">
        <h4>联系信息</h4>
        <div class="info-grid">
          <div class="info-item"><span>联系人</span><strong>{{ selectedItem.contact_name }}</strong></div>
          <div class="info-item"><span>联系电话</span><strong>{{ selectedItem.contact_phone }}</strong></div>
        </div>
      </div>

      <!-- 描述（产品专属） -->
      <div v-if="detailType === 'product' && selectedItem.description" class="detail-section">
        <h4>产品描述</h4>
        <p class="desc-text">{{ selectedItem.description }}</p>
      </div>

      <!-- 关联医院/产品 -->
      <div class="detail-section">
        <h4>{{ detailType === "hospital" ? "关联产品" : "关联医院" }}</h4>
        <div v-if="(detailType === 'hospital' ? selectedItem.related_products : selectedItem.related_hospitals)?.length" class="chip-row">
          <span
            v-for="name in (detailType === 'hospital' ? selectedItem.related_products : selectedItem.related_hospitals)"
            :key="name"
            class="soft-chip blue"
          >{{ name }}</span>
        </div>
        <p v-else class="empty-hint">暂无关联</p>
      </div>

      <!-- 关联任务列表 -->
      <div class="detail-section">
        <h4>近期关联任务</h4>
        <template v-if="selectedItem.recent_tasks?.length">
          <div
            v-for="task in selectedItem.recent_tasks"
            :key="task.id"
            class="task-row"
          >
            <div class="task-row-main">
              <span class="task-title">{{ task.title }}</span>
              <span :class="['task-status-badge', statusClass(task.status)]">
                {{ statusLabel(task.status) }}
              </span>
            </div>
            <div class="task-row-meta">
              <span>{{ typeLabel(task.type) }}</span>
              <span>·</span>
              <span :class="'risk-text-' + task.risk_level">{{ riskLabel(task.risk_level) }}</span>
              <span>·</span>
              <span>{{ formatDateTime(task.created_at) }}</span>
            </div>
          </div>
        </template>
        <p v-else class="empty-hint">暂无关联任务</p>
      </div>
    </template>
  </el-drawer>
</template>

<style scoped>
/* 总览统计 */
.records-overview {
  display: grid;
  margin-bottom: 14px;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.records-overview div {
  padding: 14px 16px;
  border: 1px solid #ebeff4;
  border-radius: 10px;
  background: white;
  box-shadow: var(--shadow);
}
.records-overview strong,
.records-overview span,
.records-overview small {
  display: block;
}
.records-overview strong { color: #2e4059; font-size: 21px; }
.records-overview span { margin-top: 4px; color: #69778a; font-size: 11px; }
.records-overview small { margin-top: 7px; color: #a0a9b5; font-size: 10px; }

/* 工具栏 */
.memory-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #568a79;
  font-size: 10px;
}

/* 卡片网格 */
.record-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 14px;
  background: #f9fbfd;
  min-height: 120px;
}
.record-card {
  padding: 14px;
  border: 1px solid #e8ecf1;
  border-radius: 10px;
  background: white;
  cursor: pointer;
  transition: 0.2s;
}
.record-card:hover {
  border-color: #b6cdf8;
  box-shadow: 0 8px 18px rgba(45, 80, 130, 0.08);
  transform: translateY(-2px);
}
.record-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.hospital-icon,
.product-icon {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 9px;
  font-size: 12px;
  font-weight: 700;
}
.hospital-icon {
  color: #3977df;
  background: #eaf2ff;
}
.product-icon {
  color: #5a7d50;
  background: #e8f5e1;
}
.hospital-icon.large,
.product-icon.large {
  width: 42px;
  height: 42px;
  flex: none;
  font-size: 15px;
}
.category-tag {
  font-size: 10px;
  color: #5a7d50;
  background: #e8f5e1;
  border-radius: 4px;
  padding: 2px 7px;
  align-self: flex-start;
}
.record-card h3 {
  margin-top: 12px;
  color: #445267;
  font-size: 13px;
}
.record-card p {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  color: #98a2af;
  font-size: 10px;
}
.record-stats {
  display: grid;
  margin-top: 14px;
  padding: 10px 0;
  border-top: 1px solid #edf0f4;
  border-bottom: 1px solid #edf0f4;
  grid-template-columns: repeat(3, 1fr);
}
.record-stats span {
  border-right: 1px solid #edf0f4;
  color: #9ba5b2;
  font-size: 9px;
  text-align: center;
}
.record-stats span:last-child { border: 0; }
.record-stats b {
  display: block;
  margin-bottom: 4px;
  color: #5d6b7f;
  font-size: 14px;
}
.record-card footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 11px;
  color: #a2abb7;
  font-size: 9px;
}
.record-card footer button {
  display: inline-flex;
  gap: 3px;
  align-items: center;
  border: 0;
  color: #3372df;
  font-size: 10px;
  background: none;
  cursor: pointer;
}
.empty-tip {
  grid-column: 1 / -1;
  padding: 32px;
  text-align: center;
  color: #b0b8c4;
  font-size: 13px;
}
.pagination-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  font-size: 11px;
  color: #8c95a3;
}

/* 详情抽屉 */
.drawer-loading { padding: 20px; }
.drawer-title h3 { margin: 0; color: #394f6a; font-size: 15px; }
.drawer-title p { margin: 4px 0 0; color: #8c98a8; font-size: 11px; }
.profile-banner {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 12px;
  border-radius: 9px;
  background: #f7faff;
}
.profile-banner strong,
.profile-banner span { display: block; }
.profile-banner strong { color: #536176; font-size: 12px; }
.profile-banner span { margin-top: 4px; color: #9da7b4; font-size: 10px; }
.profile-banner .risk-badge { margin-left: auto; }
.detail-section { margin-top: 18px; }
.detail-section h4 {
  margin: 0 0 10px;
  color: #4a5569;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}
.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
.info-item {
  padding: 8px 12px;
  border-radius: 7px;
  background: #f5f8fc;
}
.info-item span {
  display: block;
  color: #8c98a8;
  font-size: 10px;
}
.info-item strong {
  display: block;
  margin-top: 3px;
  color: #445267;
  font-size: 13px;
}
.chip-row { display: flex; flex-wrap: wrap; gap: 7px; }
.empty-hint { color: #b0b8c4; font-size: 12px; margin: 0; }
.desc-text { color: #5a6680; font-size: 12px; line-height: 1.6; margin: 0; }

/* 关联任务列表 */
.task-row {
  padding: 9px 12px;
  border-radius: 8px;
  background: #f7f9fc;
  margin-bottom: 6px;
  border: 1px solid #e9edf3;
}
.task-row-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.task-title {
  color: #3c4e63;
  font-size: 12px;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.task-status-badge {
  flex-shrink: 0;
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 4px;
}
.task-status-badge.processing { background: #e8f0ff; color: #3770d9; }
.task-status-badge.done { background: #e8f5e1; color: #4a8a3c; }
.task-status-badge.waiting { background: #fff6e0; color: #b07b10; }
.task-status-badge.overdue { background: #fdecea; color: #c0392b; }
.task-row-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 4px;
  color: #9ba5b2;
  font-size: 10px;
}
.risk-text-critical { color: #c0392b; }
.risk-text-high { color: #d05a1a; }
.risk-text-medium { color: #b07b10; }
.risk-text-low { color: #4a8a3c; }
</style>
