<script setup>
import { ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Connection, Lock, Right, User } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { login as loginApi } from "../api/auth.js";
import { roles, setSession } from "../store/app";

const route = useRoute();
const router = useRouter();
const selectedRole = ref("employee");
const loading = ref(false);
const demoAccounts = {
  employee: "employee",
  manager: "manager",
  operator: "operator",
  admin: "admin",
};
const form = ref({ account: demoAccounts.employee, password: "123456" });

watch(selectedRole, (role) => {
  form.value.account = demoAccounts[role] || role;
});

async function login() {
  loading.value = true;
  try {
    const data = await loginApi({
      username: form.value.account,
      password: form.value.password,
      role: selectedRole.value,
    });
    setSession(data);
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/dashboard";
    await router.push(redirect);
  } catch (e) {
    ElMessage.error(e.message || "登录失败");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-brand-panel">
      <div class="login-brand"><div class="brand-mark light">M</div><strong>MedFlow</strong></div>
      <div class="login-copy">
        <span>AI-POWERED WORKSPACE</span>
        <h1>让每一个医疗任务<br /><em>被看见、被跟进</em></h1>
        <p>连接客户服务、医学支持、质控与合规团队，让风险事项从识别到闭环都有迹可循。</p>
      </div>
      <div class="login-feature">
        <div><el-icon><Connection /></el-icon></div>
        <p><strong>Supervisor + 多专家 Agent</strong><span>任务、风控、知识检索与通知协同运转</span></p>
      </div>
      <div class="login-orb orb-one"></div>
      <div class="login-orb orb-two"></div>
    </div>

    <div class="login-form-panel">
      <div class="login-form-wrap">
        <span class="eyebrow">WELCOME BACK</span>
        <h2>登录工作台</h2>
        <p class="login-hint">选择演示身份，体验不同角色的协同视角。</p>
        <div class="role-grid">
          <button v-for="(role, key) in roles" :key="key" type="button" :class="{ active: selectedRole === key }" @click="selectedRole = key">
            <span>{{ role.initials }}</span>
            <div><strong>{{ role.label }}</strong><small>{{ role.name }}</small></div>
          </button>
        </div>
        <el-form label-position="top" size="large">
          <el-form-item label="账号">
            <el-input v-model="form.account" :prefix-icon="User" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input v-model="form.password" :prefix-icon="Lock" type="password" show-password />
          </el-form-item>
        </el-form>
        <button class="login-submit" :disabled="loading" @click="login">
          {{ loading ? "登录中..." : "进入 MedFlow" }} <el-icon><Right /></el-icon>
        </button>
        <div class="login-foot">内部系统 · 已启用企业身份认证与审计追踪</div>
      </div>
    </div>
  </div>
</template>
