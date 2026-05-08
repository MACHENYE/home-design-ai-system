<template>
  <section class="auth-shell">
    <div class="auth-card">
      <div class="brand auth-brand">
        <div class="brand-mark">AI</div>
        <div>
          <h1>家装设计图生成</h1>
          <p>登录后管理你的历史记录和收藏方案</p>
        </div>
      </div>

      <el-tabs :model-value="authMode" stretch @update:model-value="$emit('update:authMode', $event)">
        <el-tab-pane label="登录" name="login"></el-tab-pane>
        <el-tab-pane label="注册" name="register"></el-tab-pane>
      </el-tabs>

      <el-form label-position="top" class="compact-form" @submit.prevent>
        <el-form-item label="账号">
          <el-input v-model="authForm.username" maxlength="32" clearable autocomplete="username"></el-input>
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="authForm.password"
            type="password"
            maxlength="128"
            show-password
            autocomplete="current-password"
            @keyup.enter="$emit('submit-auth')"
          ></el-input>
        </el-form-item>
        <el-button
          class="generate-button auth-button"
          type="primary"
          size="large"
          :loading="authLoading"
          @click="$emit('submit-auth')"
        >
          {{ authMode === "login" ? "登录" : "注册并登录" }}
        </el-button>
      </el-form>
    </div>
  </section>
</template>

<script>
export default {
  name: "AuthPanel",
  props: {
    authMode: {
      type: String,
      required: true,
    },
    authForm: {
      type: Object,
      required: true,
    },
    authLoading: {
      type: Boolean,
      default: false,
    },
  },
  emits: ["update:authMode", "submit-auth"],
};
</script>
