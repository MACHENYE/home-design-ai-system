<template>
  <aside class="panel result-panel">
    <div class="panel-head">
      <div>
        <span class="eyebrow">3. 生成结果</span>
        <h2>查看和保存方案</h2>
      </div>
    </div>

    <div class="result-layout">
      <div class="result-main-column">
        <div class="result-box">
          <el-image v-if="displayResultImage" :src="displayResultImage" fit="contain" class="result-image"></el-image>
          <div v-else-if="isGenerating" class="generating-state">
            <div class="generating-loader"></div>
            <strong>正在生成设计图</strong>
            <p>{{ taskStateText }}</p>
          </div>
          <el-empty v-else description="生成后的设计图会显示在这里"></el-empty>
        </div>
        <el-alert
          v-if="isGenerating && displayResultImage"
          class="generating-inline-alert"
          type="info"
          :closable="false"
          show-icon
          :title="`新方案仍在生成中：${taskStateText}`"
        ></el-alert>

        <div class="result-actions">
          <div class="inline-actions">
            <el-button type="primary" plain :disabled="!displayResultImage" @click="$emit('save-current-scheme')">
              收藏当前方案
            </el-button>
            <el-button plain :disabled="!displayResultImage" @click="$emit('download-result-image')">下载图片</el-button>
          </div>
          <el-tag effect="plain">{{ currentTaskId ? shortTaskId(currentTaskId) : "未开始" }}</el-tag>
        </div>

        <div class="preview-grid">
          <div class="preview-card">
            <label>底稿</label>
            <el-image v-if="displayDraftPreview" :src="displayDraftPreview" fit="cover"></el-image>
            <span v-else>未上传</span>
          </div>
          <div class="preview-card">
            <label>参考</label>
            <el-image v-if="displayRefPreview" :src="displayRefPreview" fit="cover"></el-image>
            <span v-else>可选</span>
          </div>
        </div>
      </div>

      <div class="result-detail-column">
        <div class="record-detail compact-record-detail">
          <div class="small-title">
            <strong>历史方案详情</strong>
            <div class="inline-actions">
              <el-button size="small" plain :disabled="!canCompareRecord()" @click="$emit('compare-record-images')">对比查看</el-button>
              <el-button size="small" type="danger" plain :disabled="!selectedRecord" @click="$emit('delete-current-record')">
                删除记录
              </el-button>
            </div>
          </div>
          <div v-if="selectedRecord" class="detail-content">
            <div class="detail-row">
              <label>任务编号</label>
              <span>{{ shortTaskId(selectedRecord.task_id) }}</span>
            </div>
            <div class="detail-grid">
              <div>
                <label>空间</label>
                <span>{{ selectedRecord.room_type || "-" }}</span>
              </div>
              <div>
                <label>风格</label>
                <span>{{ selectedRecord.design_style || "-" }}</span>
              </div>
              <div>
                <label>色彩</label>
                <span>{{ selectedRecord.color_preference || "-" }}</span>
              </div>
              <div>
                <label>材质</label>
                <span>{{ selectedRecord.material_preference || "-" }}</span>
              </div>
            </div>
            <div class="detail-row">
              <label>提示词/设计需求</label>
              <p>{{ selectedRecord.prompt }}</p>
            </div>
            <div class="detail-row" v-if="selectedRecord.negative_prompt">
              <label>排除项</label>
              <p>{{ selectedRecord.negative_prompt }}</p>
            </div>
            <div class="url-list">
              <div v-if="selectedRecord.draft_image_url">
                <label>底稿图片</label>
                <button type="button" @click="$emit('preview-image', selectedRecord.draft_image_url, '底稿')">查看</button>
              </div>
              <div v-if="selectedRecord.reference_image_url">
                <label>参考图地址</label>
                <button type="button" @click="$emit('preview-image', selectedRecord.reference_image_url, '参考图')">查看</button>
              </div>
              <div v-if="selectedRecord.result_image_url">
                <label>生成结果</label>
                <button type="button" @click="$emit('preview-image', selectedRecord.result_image_url, '结果图')">查看</button>
              </div>
            </div>
          </div>
          <el-empty v-else description="点击最近任务查看完整记录" :image-size="64"></el-empty>
        </div>
      </div>
    </div>

    <div class="result-secondary-grid">
      <div class="favorite-block">
        <div class="small-title">
          <strong>收藏方案</strong>
          <div class="inline-actions">
            <span>{{ savedSchemes.length }} 个</span>
            <el-button size="small" @click="$emit('load-favorites')">同步</el-button>
          </div>
        </div>
        <div v-if="savedSchemes.length" class="favorite-list">
          <button
            v-for="scheme in savedSchemes"
            :key="scheme.id"
            type="button"
            class="favorite-item"
            :class="{ active: scheme.id === selectedSavedSchemeId }"
            @click="$emit('select-saved-scheme', scheme)"
          >
            <el-image :src="scheme.image" fit="cover"></el-image>
            <div>
              <strong>{{ scheme.title }}</strong>
              <span>{{ scheme.style || "未填写风格" }}</span>
            </div>
            <el-button size="small" text type="danger" @click.stop="$emit('remove-favorite', scheme)">删除</el-button>
          </button>
        </div>
        <el-empty v-else description="暂无收藏方案" :image-size="64"></el-empty>
      </div>

      <div class="history-block">
        <div class="small-title">
          <strong>最近任务</strong>
          <span>{{ history.length }} 条</span>
        </div>
        <div class="history-toolbar">
          <el-select
            :model-value="recordStyleFilter"
            size="small"
            clearable
            placeholder="按风格筛选"
            @update:model-value="$emit('update:recordStyleFilter', $event)"
            @change="$emit('load-design-records')"
          >
            <el-option v-for="item in presets.styles" :key="item" :label="item" :value="item"></el-option>
          </el-select>
          <el-button size="small" @click="$emit('load-design-records')">同步</el-button>
        </div>
        <div v-if="history.length" class="history-list">
          <button
            v-for="item in history"
            :key="item.taskId"
            type="button"
            class="history-item"
            :class="{ active: item.taskId === (selectedHistoryTaskId || currentTaskId) }"
            @click="$emit('open-history', item.taskId)"
          >
            <strong>{{ shortTaskId(item.taskId) }}</strong>
            <span>{{ item.status }}</span>
          </button>
        </div>
        <el-empty v-else description="暂无任务" :image-size="64"></el-empty>
      </div>
    </div>
  </aside>
</template>

<script>
export default {
  name: "ResultPanel",
  props: {
    displayResultImage: {
      type: String,
      default: "",
    },
    displayDraftPreview: {
      type: String,
      default: "",
    },
    displayRefPreview: {
      type: String,
      default: "",
    },
    isGenerating: {
      type: Boolean,
      default: false,
    },
    taskStateText: {
      type: String,
      required: true,
    },
    currentTaskId: {
      type: String,
      default: "",
    },
    selectedRecord: {
      type: Object,
      default: null,
    },
    savedSchemes: {
      type: Array,
      required: true,
    },
    selectedSavedSchemeId: {
      type: [String, Number],
      default: "",
    },
    history: {
      type: Array,
      required: true,
    },
    selectedHistoryTaskId: {
      type: String,
      default: "",
    },
    presets: {
      type: Object,
      required: true,
    },
    recordStyleFilter: {
      type: String,
      default: "",
    },
    shortTaskId: {
      type: Function,
      required: true,
    },
    canCompareRecord: {
      type: Function,
      required: true,
    },
  },
  emits: [
    "save-current-scheme",
    "download-result-image",
    "compare-record-images",
    "delete-current-record",
    "preview-image",
    "load-favorites",
    "select-saved-scheme",
    "remove-favorite",
    "update:recordStyleFilter",
    "load-design-records",
    "open-history",
  ],
};
</script>
