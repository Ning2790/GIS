<script setup lang="ts">
import { ApiError, changePassword } from '@qh/api-client';
import { ElMessage } from 'element-plus';
import { onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useAuthStore } from '../stores/auth';
import { useNotificationsStore } from '../stores/notifications';

const auth = useAuthStore();
const notifications = useNotificationsStore();
const route = useRoute();
const router = useRouter();

// 顶栏铃铛角标：进入控制台时拉一次未读数（失败静默）
onMounted(() => {
  void notifications.refresh();
});

async function handleLogout() {
  await auth.logout();
  notifications.clear();
  ElMessage.success('已退出登录');
  void router.push({ name: 'login' });
}

// 修改密码（商户 / 企业 / 管理员通用）；成功后其他设备退出，当前端自动续期
const passwordDialog = ref(false);
const savingPassword = ref(false);
const pwdForm = reactive({ oldPassword: '', newPassword: '', confirm: '' });

function openPasswordDialog() {
  pwdForm.oldPassword = '';
  pwdForm.newPassword = '';
  pwdForm.confirm = '';
  passwordDialog.value = true;
}

async function submitPassword() {
  if (pwdForm.newPassword.length < 6) {
    ElMessage.warning('新密码至少 6 位');
    return;
  }
  if (pwdForm.newPassword !== pwdForm.confirm) {
    ElMessage.warning('两次输入的新密码不一致');
    return;
  }
  savingPassword.value = true;
  try {
    await changePassword(pwdForm.oldPassword, pwdForm.newPassword);
    ElMessage.success('密码已修改，其他设备已退出登录');
    passwordDialog.value = false;
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '修改失败');
  } finally {
    savingPassword.value = false;
  }
}

const MENUS = [
  { path: '/', label: '概览', icon: '🏠', roles: ['merchant', 'enterprise', 'admin'] },
  { path: '/notifications', label: '消息通知', icon: '🔔', roles: ['merchant', 'enterprise', 'admin'] },
  { path: '/products', label: '商品管理', icon: '📦', roles: ['merchant', 'enterprise', 'admin'] },
  { path: '/orders', label: '订单管理', icon: '🧾', roles: ['merchant', 'enterprise', 'admin'] },
  { path: '/b2b', label: '供需管理', icon: '🤝', roles: ['merchant', 'enterprise', 'admin'] },
  { path: '/cs', label: '客服工作台', icon: '💬', roles: ['merchant', 'enterprise', 'admin'] },
  { path: '/after-sales', label: '售后管理', icon: '🛠️', roles: ['merchant', 'enterprise', 'admin'] },
  { path: '/devices', label: '登录设备', icon: '📱', roles: ['merchant', 'enterprise', 'admin'] },
  { path: '/admin/routes', label: '路线管理', icon: '🗺️', roles: ['admin'] },
  { path: '/admin/reviews', label: '资质审核', icon: '✅', roles: ['admin'] },
  { path: '/admin/users', label: '用户管理', icon: '👥', roles: ['admin'] },
  { path: '/admin/audit-logs', label: '审计日志', icon: '🗂️', roles: ['admin'] },
];

function visibleMenus() {
  const role = auth.user?.role ?? '';
  return MENUS.filter((item) => item.roles.includes(role));
}
</script>

<template>
  <el-container class="layout">
    <el-header class="layout__header">
      <div class="layout__brand">青海旅游 · 管理控制台</div>
      <div class="layout__account">
        <el-tag size="small" :type="auth.isAdmin ? 'danger' : 'primary'">
          {{ auth.isAdmin ? '管理员' : '商户' }}
        </el-tag>
        <span class="layout__name">{{ auth.displayName }}</span>
        <el-badge
          :value="notifications.unread"
          :hidden="notifications.unread === 0"
          :max="99"
          class="layout__bell"
        >
          <el-button link @click="router.push('/notifications')">消息</el-button>
        </el-badge>
        <el-button link @click="openPasswordDialog">修改密码</el-button>
        <el-button link @click="handleLogout">退出</el-button>
      </div>
    </el-header>
    <el-container>
      <el-aside width="200px" class="layout__aside">
        <el-menu :default-active="route.path" router class="layout__menu">
          <el-menu-item v-for="item in visibleMenus()" :key="item.path" :index="item.path">
            <span class="layout__icon">{{ item.icon }}</span>
            <span>{{ item.label }}</span>
          </el-menu-item>
        </el-menu>
      </el-aside>
      <el-main class="layout__main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>

  <el-dialog v-model="passwordDialog" title="修改密码" width="420px">
    <el-form label-width="90px">
      <el-form-item label="原密码">
        <el-input v-model="pwdForm.oldPassword" type="password" show-password />
      </el-form-item>
      <el-form-item label="新密码">
        <el-input
          v-model="pwdForm.newPassword"
          type="password"
          show-password
          placeholder="6–64 位"
        />
      </el-form-item>
      <el-form-item label="确认新密码">
        <el-input v-model="pwdForm.confirm" type="password" show-password />
      </el-form-item>
    </el-form>
    <template #footer>
      <span class="dialog-tip">修改后其他设备需重新登录</span>
      <el-button @click="passwordDialog = false">取消</el-button>
      <el-button type="primary" :loading="savingPassword" @click="submitPassword">确认修改</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.dialog-tip {
  float: left;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 32px;
}
.layout {
  height: 100vh;
}
.layout__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--qh-ink);
  color: #fff;
}
.layout__brand {
  font-weight: 700;
  letter-spacing: 0.02em;
}
.layout__account {
  display: flex;
  align-items: center;
  gap: 12px;
}
.layout__name {
  color: #cbd5e1;
  font-size: 13px;
}
.layout__bell :deep(.el-button) {
  color: #cbd5e1;
}
.layout__aside {
  border-right: 1px solid var(--el-border-color-light);
  background: #fff;
}
.layout__menu {
  border-right: none;
}
.layout__icon {
  margin-right: 6px;
}
.layout__main {
  background: var(--el-fill-color-light);
}
</style>
