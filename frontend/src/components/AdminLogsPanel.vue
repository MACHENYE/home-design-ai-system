<template>
  <section class="panel admin-page">
    <div class="admin-toolbar">
      <div>
        <span class="eyebrow">管理后台</span>
        <h2>系统运行日志</h2>
      </div>
      <div class="admin-toolbar-actions">
        <el-select v-model="filters.level" clearable placeholder="日志级别" size="small" @change="refreshLogs">
          <el-option label="info" value="info"></el-option>
          <el-option label="warning" value="warning"></el-option>
          <el-option label="error" value="error"></el-option>
        </el-select>
        <el-input v-model="filters.username" clearable placeholder="用户" size="small" @keyup.enter="refreshLogs"></el-input>
        <el-button size="small" :loading="loading" @click="refreshLogs">刷新日志</el-button>
      </div>
    </div>

    <div class="admin-kpis">
      <div class="admin-kpi">
        <span>日志数量</span>
        <strong>{{ logs.length }}</strong>
      </div>
      <div class="admin-kpi">
        <span>错误日志</span>
        <strong>{{ countByLevel("error") }}</strong>
      </div>
      <div class="admin-kpi">
        <span>警告日志</span>
        <strong>{{ countByLevel("warning") }}</strong>
      </div>
      <div class="admin-kpi">
        <span>信息日志</span>
        <strong>{{ countByLevel("info") }}</strong>
      </div>
    </div>

    <section class="admin-log-panel">
      <div class="small-title">
        <strong>最近运行记录</strong>
        <span>记录用户操作、生成任务、异常和接口耗时</span>
      </div>
      <el-table :data="logs" height="620" size="small" v-loading="loading">
        <el-table-column label="级别" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="logLevelType(row.level)">{{ row.level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="action" label="操作类型" width="190"></el-table-column>
        <el-table-column prop="username" label="用户" width="120">
          <template #default="{ row }">{{ row.username || "-" }}</template>
        </el-table-column>
        <el-table-column label="关联对象" width="190">
          <template #default="{ row }">
            <span>{{ row.target_type || "-" }}</span>
            <strong v-if="row.target_id" class="log-target">{{ shortText(row.target_id, 14) }}</strong>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="说明" min-width="260">
          <template #default="{ row }">{{ row.message || "-" }}</template>
        </el-table-column>
        <el-table-column prop="request_path" label="接口路径" min-width="210">
          <template #default="{ row }">{{ row.request_path || "-" }}</template>
        </el-table-column>
        <el-table-column label="耗时" width="90">
          <template #default="{ row }">{{ row.duration_ms ? `${row.duration_ms}ms` : "-" }}</template>
        </el-table-column>
        <el-table-column label="时间" width="175">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </section>
  </section>
</template>

<script>
export default {
  name: "AdminLogsPanel",
  props: {
    logs: {
      type: Array,
      default: () => [],
    },
    loading: {
      type: Boolean,
      default: false,
    },
  },
  emits: ["refresh-logs"],
  data() {
    return {
      filters: {
        level: "",
        username: "",
      },
    };
  },
  methods: {
    refreshLogs() {
      const payload = { limit: 120 };
      if (this.filters.level) payload.level = this.filters.level;
      if (this.filters.username.trim()) payload.username = this.filters.username.trim();
      this.$emit("refresh-logs", payload);
    },
    countByLevel(level) {
      return this.logs.filter((item) => item.level === level).length;
    },
    formatTime(value) {
      const timestamp = Number(value);
      if (!timestamp) return "-";
      return new Date(timestamp * 1000).toLocaleString();
    },
    shortText(value, size = 16) {
      if (!value) return "";
      return value.length > size ? `${value.slice(0, size)}...` : value;
    },
    logLevelType(level) {
      return { error: "danger", warning: "warning", info: "success" }[level] || "info";
    },
  },
};
</script>
