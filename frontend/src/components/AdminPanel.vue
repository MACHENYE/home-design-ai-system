<template>
  <el-dialog :model-value="modelValue" title="管理后台" width="1180px" @close="$emit('update:modelValue', false)">
    <div class="admin-toolbar">
      <span>平台数据概览</span>
      <el-button size="small" :loading="loading" @click="$emit('refresh-admin')">刷新数据</el-button>
    </div>

    <div class="admin-kpis">
      <div class="admin-kpi">
        <span>用户数</span>
        <strong>{{ summary.users || 0 }}</strong>
      </div>
      <div class="admin-kpi">
        <span>生成记录</span>
        <strong>{{ summary.records || 0 }}</strong>
      </div>
      <div class="admin-kpi">
        <span>收藏方案</span>
        <strong>{{ summary.favorites || 0 }}</strong>
      </div>
      <div class="admin-kpi">
        <span>成功 / 失败</span>
        <strong>{{ summary.successes || 0 }} / {{ summary.failures || 0 }}</strong>
      </div>
    </div>

    <div class="admin-charts">
      <section>
        <div class="small-title">
          <strong>近 7 日任务</strong>
          <span>按创建日期统计</span>
        </div>
        <div class="bar-chart">
          <div v-for="item in dailyStats" :key="item.day" class="bar-row">
            <span>{{ item.day }}</span>
            <div><i :style="{ width: barWidth(item.value, maxDaily) }"></i></div>
            <em>{{ item.value }}</em>
          </div>
        </div>
      </section>
      <section>
        <div class="small-title">
          <strong>热门风格</strong>
          <span>按生成记录统计</span>
        </div>
        <div class="bar-chart">
          <div v-for="item in styleStats" :key="item.name" class="bar-row">
            <span>{{ item.name }}</span>
            <div><i :style="{ width: barWidth(item.value, maxStyle) }"></i></div>
            <em>{{ item.value }}</em>
          </div>
        </div>
      </section>
    </div>

    <div class="admin-tables">
      <section>
        <div class="small-title">
          <strong>用户使用记录</strong>
          <span>{{ users.length }} 位用户</span>
        </div>
        <el-table :data="users" height="260" size="small">
          <el-table-column prop="username" label="用户" min-width="120"></el-table-column>
          <el-table-column prop="total_records" label="任务数" width="90"></el-table-column>
          <el-table-column prop="success_records" label="成功" width="80"></el-table-column>
          <el-table-column prop="failed_records" label="失败" width="80"></el-table-column>
          <el-table-column label="最近使用" min-width="150">
            <template #default="{ row }">{{ formatTime(row.last_used_at || row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </section>
      <section>
        <div class="small-title">
          <strong>最近生成明细</strong>
          <span>{{ records.length }} 条</span>
        </div>
        <el-table :data="records" height="260" size="small">
          <el-table-column prop="username" label="用户" width="100"></el-table-column>
          <el-table-column prop="room_type" label="空间" width="80"></el-table-column>
          <el-table-column prop="design_style" label="风格" width="110"></el-table-column>
          <el-table-column prop="color_preference" label="色彩" min-width="120"></el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">{{ statusLabel(row.status) }}</template>
          </el-table-column>
          <el-table-column label="时间" min-width="150">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </section>
    </div>
  </el-dialog>
</template>

<script>
export default {
  name: "AdminPanel",
  props: {
    modelValue: {
      type: Boolean,
      default: false,
    },
    dashboard: {
      type: Object,
      default: () => ({}),
    },
    loading: {
      type: Boolean,
      default: false,
    },
  },
  emits: ["update:modelValue", "refresh-admin"],
  computed: {
    summary() {
      return this.dashboard.summary || {};
    },
    users() {
      return this.dashboard.users || [];
    },
    records() {
      return this.dashboard.records || [];
    },
    dailyStats() {
      return this.dashboard.dailyStats || [];
    },
    styleStats() {
      return this.dashboard.styleStats || [];
    },
    maxDaily() {
      return Math.max(1, ...this.dailyStats.map((item) => Number(item.value) || 0));
    },
    maxStyle() {
      return Math.max(1, ...this.styleStats.map((item) => Number(item.value) || 0));
    },
  },
  methods: {
    barWidth(value, max) {
      return `${Math.max(8, (Number(value || 0) / max) * 100)}%`;
    },
    formatTime(value) {
      const timestamp = Number(value);
      if (!timestamp) return "暂无";
      return new Date(timestamp * 1000).toLocaleString();
    },
    statusLabel(value) {
      return { 1: "已创建", 2: "处理中", 3: "已完成", 4: "失败" }[Number(value)] || "未知";
    },
  },
};
</script>
