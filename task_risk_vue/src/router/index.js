import { createRouter, createWebHistory } from "vue-router";
import LoginPage from "../pages/LoginPage.vue";
import AppLayout from "../layouts/AppLayout.vue";
import DashboardPage from "../pages/DashboardPage.vue";
import AssistantPage from "../pages/AssistantPage.vue";
import TasksPage from "../pages/TasksPage.vue";
import RiskPage from "../pages/RiskPage.vue";
import RecordsPage from "../pages/RecordsPage.vue";
import KnowledgePage from "../pages/KnowledgePage.vue";
import ReportsPage from "../pages/ReportsPage.vue";
import AdminPage from "../pages/AdminPage.vue";
import { getMe } from "../api/auth.js";
import { getAuthToken, getStoredRole, isAuthenticated, logout, setSession } from "../store/app";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: LoginPage },
    {
      path: "/",
      component: AppLayout,
      redirect: "/dashboard",
      children: [
        { path: "dashboard", component: DashboardPage, meta: { title: "总览工作台" } },
        { path: "assistant", component: AssistantPage, meta: { title: "智能协同" } },
        { path: "tasks", component: TasksPage, meta: { title: "任务中心" } },
        { path: "risk", component: RiskPage, meta: { title: "风险中心", roles: ["manager", "admin"] } },
        { path: "records", component: RecordsPage, meta: { title: "业务档案" } },
        { path: "knowledge", component: KnowledgePage, meta: { title: "知识中心" } },
        { path: "reports", component: ReportsPage, meta: { title: "统计报告" } },
        { path: "admin", component: AdminPage, meta: { title: "系统管理", roles: ["admin"] } },
      ],
    },
    { path: "/:pathMatch(.*)*", redirect: "/dashboard" },
  ],
});

let authBootstrapDone = false;

async function bootstrapAuth() {
  const token = getAuthToken();
  if (!token) {
    logout();
    return false;
  }
  try {
    const user = await getMe();
    setSession({ access_token: token, user });
    return true;
  } catch {
    logout();
    return false;
  }
}

router.beforeEach(async (to) => {
  if (!authBootstrapDone) {
    authBootstrapDone = true;
    await bootstrapAuth();
  }

  const authenticated = isAuthenticated.value;

  if (!authenticated && to.path !== "/login") {
    return { path: "/login", query: { redirect: to.fullPath } };
  }
  if (authenticated && to.path === "/login") {
    return "/dashboard";
  }

  const role = getStoredRole();
  if (to.meta.roles && !to.meta.roles.includes(role)) {
    return "/dashboard";
  }
});

export default router;
