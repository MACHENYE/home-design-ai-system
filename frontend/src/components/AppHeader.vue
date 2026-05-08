<template>
  <header class="topbar">
    <div class="brand">
      <div class="brand-mark">AI</div>
      <div>
        <h1>家装设计图生成</h1>
      </div>
    </div>
    <div class="user-box">
      <el-tag effect="plain">{{ currentUser.username }}</el-tag>
      <el-button size="small" @click="$emit('logout')">退出登录</el-button>
    </div>
  </header>
</template>

<script>
export default {
  name: "AppHeader",
  props: {
    currentUser: {
      type: Object,
      required: true,
    },
  },
  emits: ["logout"],
};
</script>
