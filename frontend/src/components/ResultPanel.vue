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
          <div class="result-action-grid">
            <el-button type="primary" plain :disabled="!displayResultImage" @click="$emit('save-current-scheme')">
              收藏当前方案
            </el-button>
            <el-button plain :disabled="!displayResultImage" @click="$emit('continue-edit')">继续修改</el-button>
            <el-button plain :disabled="!displayResultImage" @click="$emit('download-result-image')">下载图片</el-button>
            <el-button plain :disabled="!selectedRecord" @click="$emit('save-pdf-report')">保存PDF</el-button>
            <el-button
              class="cancel-generation-button"
              :class="{ reserved: !isGenerating }"
              type="danger"
              plain
              :disabled="!isGenerating || !currentTaskId"
              @click="$emit('cancel-current-task')"
            >
              终止生成
            </el-button>
          </div>
          <el-tag class="result-task-tag" effect="plain">{{ currentTaskId ? shortTaskId(currentTaskId) : "未开始" }}</el-tag>
        </div>

        <div class="feedback-card">
          <div class="small-title">
            <strong>方案评分与反馈</strong>
          </div>
          <div class="feedback-grid">
            <label>
              <span>采光</span>
              <el-rate v-model="feedbackForm.lighting_score" :max="5" />
            </label>
            <label>
              <span>风格匹配</span>
              <el-rate v-model="feedbackForm.style_match_score" :max="5" />
            </label>
            <label>
              <span>空间利用</span>
              <el-rate v-model="feedbackForm.space_utilization_score" :max="5" />
            </label>
            <label>
              <span>满意度</span>
              <el-rate v-model="feedbackForm.satisfaction_score" :max="5" />
            </label>
          </div>
          <el-input
            v-model="feedbackForm.feedback_text"
            type="textarea"
            :rows="2"
            maxlength="500"
            show-word-limit
            placeholder="可补充说明喜欢或不满意的地方"
          ></el-input>
          <div class="feedback-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="!feedbackTaskId || !displayResultImage"
              :loading="feedbackSubmitting"
              @click="submitFeedback"
            >
              保存评分
            </el-button>
          </div>
        </div>

        <div class="preview-grid">
          <div class="preview-card">
            <label>底稿</label>
            <div v-if="displayDraftPreview" class="preview-thumb-row">
              <el-image :src="displayDraftPreview" fit="cover"></el-image>
              <span>已上传</span>
            </div>
            <span v-else>未上传</span>
          </div>
        </div>
      </div>

      <div class="result-detail-column">
        <div class="record-detail compact-record-detail">
          <div class="small-title">
            <strong>方案详情</strong>
            <div class="inline-actions">
              <el-button size="small" plain :disabled="!canCompareRecord()" @click="$emit('compare-record-images')">对比查看</el-button>
              <el-button size="small" type="danger" plain :disabled="!selectedHistoryTaskId && !currentTaskId" @click="$emit('delete-current-record')">
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
                <label>版本轮次</label>
                <span>第 {{ selectedRecord.iteration_no || 1 }} 版</span>
              </div>
              <div>
                <label>来源任务</label>
                <span>{{ selectedRecord.source_task_id ? shortTaskId(selectedRecord.source_task_id) : "首轮生成" }}</span>
              </div>
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
            <div class="detail-row" v-if="recordNotes.length">
              <label>掩码标签</label>
              <p v-for="note in recordNotes" :key="note.no">{{ note.no }}. {{ note.text }}</p>
            </div>
            <div class="detail-row" v-if="selectedRecord.error_message">
              <label>任务状态</label>
              <p>{{ selectedRecord.error_message }}</p>
            </div>
            <div class="url-list">
              <div v-if="selectedRecord.draft_image_url">
                <label>底稿图片</label>
                <button type="button" @click="$emit('preview-image', selectedRecord.draft_image_url, '底稿')">查看</button>
              </div>
              <div v-if="selectedRecord.result_image_url">
                <label>生成结果</label>
                <button type="button" @click="$emit('preview-image', selectedRecord.result_image_url, '结果图')">查看</button>
              </div>
            </div>
          </div>
          <el-empty v-else description="点击收藏方案或最近任务查看完整记录" :image-size="64"></el-empty>
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
            v-for="item in historyTreeItems"
            :key="item.taskId"
            type="button"
            class="history-item"
            :class="{ active: item.taskId === (selectedHistoryTaskId || currentTaskId), child: item.level > 0 }"
            :style="{ '--tree-level': item.level }"
            @click="$emit('open-history', item.taskId)"
          >
            <span class="history-tree-line" aria-hidden="true"></span>
            <span class="history-main">
              <strong>{{ shortTaskId(item.taskId) }}</strong>
              <small>{{ item.displayIterationNo > 1 ? `第 ${item.displayIterationNo} 版` : "首版" }}</small>
            </span>
            <span class="history-status">{{ item.status }}</span>
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
    feedbackSubmitting: {
      type: Boolean,
      default: false,
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
    "save-pdf-report",
    "compare-record-images",
    "delete-current-record",
    "preview-image",
    "load-favorites",
    "select-saved-scheme",
    "remove-favorite",
    "save-feedback",
    "update:recordStyleFilter",
    "load-design-records",
    "open-history",
    "continue-edit",
    "cancel-current-task",
  ],
  // Initialize component state.
  data() {
    return {
      feedbackForm: this.feedbackFromRecord(this.selectedRecord),
    };
  },
  computed: {
    // Return the feedback task id.
    feedbackTaskId() {
      return this.selectedRecord?.task_id || this.currentTaskId || "";
    },
    // Parse design notes stored with the record.
    recordNotes() {
      if (!this.selectedRecord?.interaction_notes_json) return [];
      try {
        const notes = JSON.parse(this.selectedRecord.interaction_notes_json);
        return Array.isArray(notes) ? notes : [];
      } catch (err) {
        return [];
      }
    },
    // Build a flattened version tree for history records.
    historyTreeItems() {
      const nodes = new Map();
      for (const item of this.history) {
        nodes.set(item.taskId, { ...item, children: [] });
      }
      const resultToTaskId = new Map();
      for (const node of nodes.values()) {
        if (node.resultImageUrl) resultToTaskId.set(node.resultImageUrl, node.taskId);
      }
      for (const node of nodes.values()) {
        if (!node.sourceTaskId && node.draftImageUrl) {
          const inferredParentId = resultToTaskId.get(node.draftImageUrl);
          if (inferredParentId && inferredParentId !== node.taskId) {
            node.sourceTaskId = inferredParentId;
          }
        }
      }
      const rootOf = (taskId) => {
        let current = taskId;
        const seen = new Set();
        while (current && nodes.has(current) && !seen.has(current)) {
          seen.add(current);
          const parentId = nodes.get(current)?.sourceTaskId;
          if (!parentId || !nodes.has(parentId)) return current;
          current = parentId;
        }
        return current || taskId;
      };
      for (const node of nodes.values()) {
        if (node.sourceTaskId) {
          const rootId = rootOf(node.sourceTaskId);
          if (rootId && rootId !== node.taskId) {
            node.sourceTaskId = rootId;
          }
        }
      }
      const roots = [];
      for (const node of nodes.values()) {
        const parentId = node.sourceTaskId;
        const parent = parentId ? nodes.get(parentId) : null;
        if (parent) {
          parent.children.push(node);
        } else {
          roots.push(node);
        }
      }
      const sortRoots = (a, b) => Number(b.createdAt || 0) - Number(a.createdAt || 0);
      const sortChildren = (a, b) =>
        Number(a.iterationNo || 1) - Number(b.iterationNo || 1) ||
        Number(a.createdAt || 0) - Number(b.createdAt || 0);
      const flat = [];
      const visit = (node, level) => {
        flat.push({ ...node, level });
        node.children.sort(sortChildren).forEach((child) => visit(child, level + 1));
      };
      roots.sort(sortRoots).forEach((root) => {
        const start = flat.length;
        visit(root, 0);
        flat
          .slice(start)
          .sort((a, b) => Number(a.createdAt || 0) - Number(b.createdAt || 0))
          .forEach((item, index) => {
            item.displayIterationNo = index + 1;
          });
      });
      return flat;
    },
  },
  watch: {
    selectedRecord: {
      // Handle handler logic.
      handler(record) {
        this.feedbackForm = this.feedbackFromRecord(record);
      },
      immediate: true,
    },
    // Return the current task id.
    currentTaskId() {
      if (!this.selectedRecord) {
        this.feedbackForm = this.feedbackFromRecord(null);
      }
    },
  },
  methods: {
    // Fill feedback from a record.
    feedbackFromRecord(record) {
      return {
        lighting_score: record?.lighting_score || 0,
        style_match_score: record?.style_match_score || 0,
        space_utilization_score: record?.space_utilization_score || 0,
        satisfaction_score: record?.satisfaction_score || 0,
        feedback_text: record?.feedback_text || "",
      };
    },
    // Submit feedback values.
    submitFeedback() {
      this.$emit("save-feedback", {
        taskId: this.feedbackTaskId,
        ...this.feedbackForm,
      });
    },
  },
};
</script>
