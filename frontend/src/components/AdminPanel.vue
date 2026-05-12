<template>
  <section class="panel admin-page">
    <div class="admin-toolbar">
      <div>
        <span class="eyebrow">管理后台</span>
        <h2>平台数据概览</h2>
      </div>
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

    <section class="admin-stat-table">
      <div class="small-title">
        <strong>统计汇总</strong>
        <span>按不同维度查看完整排行</span>
      </div>
      <el-tabs v-model="activeStatTab" class="admin-stat-tabs">
        <el-tab-pane v-for="tab in statTabs" :key="tab.name" :label="tab.label" :name="tab.name">
          <el-table :data="tab.rows" height="280" size="small">
            <el-table-column type="index" label="排名" width="70"></el-table-column>
            <el-table-column prop="name" :label="tab.itemLabel" min-width="180"></el-table-column>
            <el-table-column label="数量" width="100">
              <template #default="{ row }">{{ row.value }}</template>
            </el-table-column>
            <el-table-column label="占比" min-width="260">
              <template #default="{ row }">
                <div class="stat-rank-cell">
                  <span class="stat-cell-track"><i :style="{ width: statPercent(row.value, tab.total) }"></i></span>
                  <em>{{ statPercentText(row.value, tab.total) }}</em>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </section>

    <div class="admin-tables">
      <section>
        <div class="small-title">
          <strong>用户使用记录</strong>
          <span>{{ users.length }} 位用户</span>
        </div>
        <el-table :data="users" height="310" size="small">
          <el-table-column prop="username" label="用户" min-width="120"></el-table-column>
          <el-table-column label="角色" width="80">
            <template #default="{ row }">{{ row.role === "admin" ? "管理员" : "普通用户" }}</template>
          </el-table-column>
          <el-table-column prop="total_records" label="任务数" width="90"></el-table-column>
          <el-table-column prop="success_records" label="成功" width="80"></el-table-column>
          <el-table-column prop="failed_records" label="失败" width="80"></el-table-column>
          <el-table-column label="满意度" width="90">
            <template #default="{ row }">{{ scoreText(row.avg_satisfaction) }}</template>
          </el-table-column>
          <el-table-column label="最近使用" min-width="150">
            <template #default="{ row }">{{ formatTime(row.last_used_at || row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </section>

      <section class="admin-records-section">
        <div class="small-title">
          <strong>最近生成明细</strong>
          <span>{{ filteredRecords.length }} / {{ records.length }} 条</span>
        </div>
        <div class="admin-filters">
          <el-select v-model="filters.username" clearable filterable placeholder="用户">
            <el-option v-for="item in options.username" :key="item" :label="item" :value="item"></el-option>
          </el-select>
          <el-select v-model="filters.room_type" clearable filterable placeholder="空间">
            <el-option v-for="item in options.room_type" :key="item" :label="item" :value="item"></el-option>
          </el-select>
          <el-select v-model="filters.design_style" clearable filterable placeholder="风格">
            <el-option v-for="item in options.design_style" :key="item" :label="item" :value="item"></el-option>
          </el-select>
          <el-select v-model="filters.color_preference" clearable filterable placeholder="色彩">
            <el-option v-for="item in options.color_preference" :key="item" :label="item" :value="item"></el-option>
          </el-select>
          <el-select v-model="filters.status" clearable placeholder="状态">
            <el-option v-for="item in options.status" :key="item" :label="statusLabel(item)" :value="item"></el-option>
          </el-select>
          <el-button plain @click="resetFilters">重置</el-button>
        </div>
        <el-table :data="filteredRecords" height="360" size="small">
          <el-table-column prop="username" label="用户" width="90"></el-table-column>
          <el-table-column prop="room_type" label="空间" width="80"></el-table-column>
          <el-table-column prop="design_style" label="风格" width="100"></el-table-column>
          <el-table-column prop="color_preference" label="色彩" min-width="120"></el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">{{ statusLabel(row.status) }}</template>
          </el-table-column>
          <el-table-column label="满意度" width="90">
            <template #default="{ row }">{{ scoreText(row.satisfaction_score) }}</template>
          </el-table-column>
          <el-table-column label="时间" min-width="145">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="135" fixed="right">
            <template #default="{ row }">
              <el-button size="small" link type="primary" @click="openRecord(row)">详情</el-button>
              <el-button size="small" link type="danger" @click="$emit('delete-record', row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>
    </div>

    <el-dialog v-model="detailVisible" title="生成方案详情" width="980px">
      <div v-if="activeRecord" class="admin-detail">
        <div class="admin-detail-grid">
          <div><span>任务编号</span><strong>{{ activeRecord.task_id }}</strong></div>
          <div><span>用户</span><strong>{{ activeRecord.username || "未知" }}</strong></div>
          <div><span>空间</span><strong>{{ activeRecord.room_type || "-" }}</strong></div>
          <div><span>风格</span><strong>{{ activeRecord.design_style || "-" }}</strong></div>
          <div><span>色彩</span><strong>{{ activeRecord.color_preference || "-" }}</strong></div>
          <div><span>材质</span><strong>{{ activeRecord.material_preference || "-" }}</strong></div>
          <div><span>状态</span><strong>{{ statusLabel(activeRecord.status) }}</strong></div>
          <div><span>生成时间</span><strong>{{ formatTime(activeRecord.created_at) }}</strong></div>
        </div>

        <div class="admin-detail-images">
          <section>
            <span>底稿图片</span>
            <el-image v-if="activeRecord.draft_image_url" :src="activeRecord.draft_image_url" fit="contain"></el-image>
            <el-empty v-else description="无底稿" :image-size="48"></el-empty>
          </section>
          <section>
            <span>生成结果</span>
            <el-image v-if="activeRecord.result_image_url" :src="activeRecord.result_image_url" fit="contain"></el-image>
            <el-empty v-else description="无结果" :image-size="48"></el-empty>
          </section>
        </div>

        <section class="admin-detail-block">
          <span>提示词</span>
          <p>{{ activeRecord.prompt || "-" }}</p>
        </section>
        <section class="admin-detail-block">
          <span>排除项</span>
          <p>{{ activeRecord.negative_prompt || "-" }}</p>
        </section>
        <section class="admin-detail-block">
          <span>评分反馈</span>
          <p>
            采光 {{ scoreText(activeRecord.lighting_score) }}；
            风格匹配 {{ scoreText(activeRecord.style_match_score) }}；
            空间利用 {{ scoreText(activeRecord.space_utilization_score) }}；
            满意度 {{ scoreText(activeRecord.satisfaction_score) }}
          </p>
          <p>{{ activeRecord.feedback_text || "暂无文字反馈" }}</p>
        </section>
        <section v-if="activeRecord.error_message" class="admin-detail-block">
          <span>错误信息</span>
          <p>{{ activeRecord.error_message }}</p>
        </section>
      </div>
    </el-dialog>
  </section>
</template>

<script>
export default {
  name: "AdminPanel",
  props: {
    dashboard: {
      type: Object,
      default: () => ({}),
    },
    loading: {
      type: Boolean,
      default: false,
    },
  },
  emits: ["refresh-admin", "delete-record"],
  data() {
    return {
      filters: {
        username: "",
        room_type: "",
        design_style: "",
        color_preference: "",
        status: "",
      },
      activeStatTab: "daily",
      detailVisible: false,
      activeRecord: null,
    };
  },
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
    roomStats() {
      return this.dashboard.roomStats || [];
    },
    colorStats() {
      return this.dashboard.colorStats || [];
    },
    materialStats() {
      return this.dashboard.materialStats || [];
    },
    statusStats() {
      return this.dashboard.statusStats || [];
    },
    options() {
      return {
        username: this.uniqueOptions("username"),
        room_type: this.uniqueOptions("room_type"),
        design_style: this.uniqueOptions("design_style"),
        color_preference: this.uniqueOptions("color_preference"),
        status: this.uniqueOptions("status"),
      };
    },
    filteredRecords() {
      return this.records.filter((record) =>
        Object.entries(this.filters).every(([key, value]) => !value || String(record[key] ?? "") === String(value)),
      );
    },
    statTabs() {
      return [
        this.statTab("daily", "近7日任务", "日期", this.dailyStats.map((item) => ({ ...item, name: item.day }))),
        this.statTab("room", "热门空间", "空间", this.roomStats),
        this.statTab("style", "热门风格", "风格", this.styleStats),
        this.statTab("color", "热门色彩", "色彩", this.colorStats),
        this.statTab("material", "热门材质", "材质", this.materialStats),
        this.statTab(
          "status",
          "任务状态",
          "状态",
          this.statusStats.map((item) => ({ ...item, name: this.statusLabel(item.name) })),
        ),
      ];
    },
  },
  methods: {
    statTab(name, label, itemLabel, rows) {
      return {
        name,
        label,
        itemLabel,
        rows,
        total: rows.reduce((sum, item) => sum + Number(item.value || 0), 0),
      };
    },
    statPercent(value, total) {
      if (!total) return "0%";
      return `${Math.max(4, (Number(value || 0) / total) * 100)}%`;
    },
    statPercentText(value, total) {
      if (!total) return "0%";
      return `${Math.round((Number(value || 0) / total) * 100)}%`;
    },
    uniqueOptions(field) {
      return [...new Set(this.records.map((record) => record[field]).filter((value) => value !== null && value !== undefined && value !== ""))];
    },
    resetFilters() {
      this.filters = {
        username: "",
        room_type: "",
        design_style: "",
        color_preference: "",
        status: "",
      };
    },
    openRecord(record) {
      this.activeRecord = record;
      this.detailVisible = true;
    },
    formatTime(value) {
      const timestamp = Number(value);
      if (!timestamp) return "暂无";
      return new Date(timestamp * 1000).toLocaleString();
    },
    scoreText(value) {
      return value === null || value === undefined || value === "" ? "-" : `${value}`;
    },
    statusLabel(value) {
      return { 1: "已创建", 2: "处理中", 3: "已完成", 4: "失败" }[Number(value)] || "未知";
    },
  },
};
</script>
