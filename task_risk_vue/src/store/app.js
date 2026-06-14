import { computed, reactive } from "vue";

const TOKEN_KEY = "medflow-token";
const USER_KEY = "medflow-user";
const ROLE_KEY = "medflow-role";

export const roles = {
  employee: { label: "一线员工", name: "张客服", dept: "客户服务部", initials: "张", userId: 2 },
  manager: { label: "部门主管", name: "孙主管", dept: "客户服务部", initials: "孙", userId: 7 },
  operator: { label: "知识运营", name: "王产品", dept: "产品运营部", initials: "王", userId: 4 },
  admin: { label: "系统管理员", name: "管理员", dept: "数字化中心", initials: "管", userId: 1 },
};

export const roleKeys = Object.keys(roles);

function readJson(key) {
  try {
    return JSON.parse(localStorage.getItem(key) || "null");
  } catch {
    localStorage.removeItem(key);
    return null;
  }
}

function normalizeUser(user, options = {}) {
  const hasSession = options.hasSession !== false;
  const role = roleKeys.includes(user?.role) ? user.role : "employee";
  const fallback = roles[role];
  const name = user?.name || (hasSession ? fallback.name : "");
  const resolvedId = user?.id ?? (hasSession ? fallback.userId : null);
  return {
    ...fallback,
    ...user,
    role,
    label: user?.role_label || fallback.label,
    dept: user?.department || fallback.dept,
    initials: name?.slice(0, 1) || fallback.initials,
    id: resolvedId,
    userId: resolvedId,
    name: name || fallback.name,
  };
}

const storedToken = localStorage.getItem(TOKEN_KEY) || "";
const storedUser = storedToken ? readJson(USER_KEY) : null;
if (!storedToken) {
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(ROLE_KEY);
}
const initialUser = storedUser
  ? normalizeUser(storedUser, { hasSession: true })
  : normalizeUser({ role: "employee" }, { hasSession: false });

export const appState = reactive({
  token: storedToken,
  role: initialUser.role,
  user: initialUser,
  notifications: [],
  unreadTotal: 0,
});

export const currentUser = computed(() => appState.user || normalizeUser({ role: appState.role }, { hasSession: Boolean(appState.token) }));
export const currentUserId = computed(() => currentUser.value?.userId || currentUser.value?.id || null);
export const unreadCount = computed(() =>
  appState.unreadTotal > 0
    ? appState.unreadTotal
    : appState.notifications.filter((item) => !item.is_read).length
);
export const isAuthenticated = computed(() => Boolean(appState.token && appState.user?.id));

export function getAuthToken() {
  return appState.token || localStorage.getItem(TOKEN_KEY) || "";
}

export function getStoredRole() {
  const user = readJson(USER_KEY);
  if (roleKeys.includes(user?.role)) return user.role;
  const role = localStorage.getItem(ROLE_KEY);
  if (roleKeys.includes(role)) return role;
  localStorage.removeItem(ROLE_KEY);
  return null;
}

export function setSession(session) {
  const token = session?.access_token || "";
  const user = normalizeUser(session?.user || {}, { hasSession: Boolean(token) });
  appState.token = token;
  appState.user = user;
  appState.role = user.role;
  appState.notifications = [];
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(session?.user || {}));
    localStorage.setItem(ROLE_KEY, user.role);
  }
}

export function setRole(role) {
  if (!roleKeys.includes(role)) return;
  appState.role = role;
  if (!appState.token) {
    appState.user = normalizeUser({ role }, { hasSession: false });
  }
  localStorage.setItem(ROLE_KEY, role);
}

export function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(ROLE_KEY);
  appState.token = "";
  appState.role = "employee";
  appState.user = normalizeUser({ role: "employee" }, { hasSession: false });
  appState.notifications = [];
  appState.unreadTotal = 0;
}
