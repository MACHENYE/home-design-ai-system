<template>
  <section class="panel control-panel">
    <div class="panel-head upload-head">
      <div>
        <span class="eyebrow">1. 输入素材</span>
        <h2>上传底稿</h2>
      </div>
      <el-button class="clear-draft-button" size="small" plain @click="$emit('clear-draft')">清空</el-button>
    </div>

    <div class="upload-grid">
      <el-upload
        class="upload-box"
        :class="{ 'has-image': Boolean(draftPreview) }"
        drag
        :show-file-list="false"
        :auto-upload="false"
        accept="image/*"
        :on-change="(file) => $emit('handle-file', file, 'draft')"
      >
        <div v-if="draftPreview" class="upload-preview-content">
          <img :src="draftPreview" alt="draft" />
          <div>
            <strong>设计底稿</strong>
            <span>{{ draftState }}</span>
          </div>
        </div>
        <template v-else>
          <strong>设计底稿</strong>
          <span>{{ draftState }}</span>
        </template>
      </el-upload>
    </div>

    <div class="section-divider"></div>

    <div class="panel-head tight design-demand-head">
      <div>
        <span class="eyebrow">2. 设计需求</span>
        <h2>选择风格并描述想要的效果</h2>
      </div>
      <el-button
        size="small"
        :class="{ 'smart-recommend-active': recommendationActive }"
        :loading="recommendationLoading"
        @click="$emit('refresh-style-templates')"
      >
        智能推荐
      </el-button>
    </div>
    <p class="template-hint">{{ recommendationHint }}</p>

    <div class="preset-row">
      <button
        v-for="preset in quickPresets"
        :key="preset.name"
        type="button"
        class="preset-chip"
        :class="{ active: isPresetActive(preset) }"
        @click="$emit('apply-quick-preset', preset)"
      >
        <strong>{{ preset.name }}</strong>
        <span>{{ preset.desc }}</span>
        <small v-if="preset.reason">{{ preset.reason }}</small>
      </button>
    </div>

    <el-form label-position="top" class="compact-form">
      <div class="form-grid">
        <el-form-item label="空间">
          <el-select v-model="form.room_type" filterable>
            <el-option v-for="item in presets.roomTypes" :key="item" :label="item" :value="item"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="风格">
          <el-select v-model="form.design_style" filterable>
            <el-option v-for="item in presets.styles" :key="item" :label="item" :value="item"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="色彩">
          <el-select v-model="form.color_preference" filterable>
            <el-option v-for="item in presets.colors" :key="item" :label="item" :value="item"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="材质">
          <el-select v-model="form.material_preference" filterable>
            <el-option v-for="item in presets.materials" :key="item" :label="item" :value="item"></el-option>
          </el-select>
        </el-form-item>
      </div>

      <el-form-item label="需求描述">
        <div class="prompt-header-action">
          <span></span>
          <el-button size="small" :loading="promptOptimizing" @click="$emit('optimize-prompt')">提示词优化</el-button>
        </div>
        <el-input v-model="form.prompt" type="textarea" :rows="5" resize="vertical"></el-input>
      </el-form-item>

      <el-form-item label="图片比例">
        <div class="ratio-row">
          <button
            v-for="ratio in aspectRatios"
            :key="ratio.value"
            type="button"
            class="ratio-chip"
            :class="{ active: form.aspect_ratio === ratio.value }"
            @click="form.aspect_ratio = ratio.value"
          >
            <span>{{ ratio.label }}</span>
          </button>
        </div>
      </el-form-item>

      <div class="prompt-chip-group">
        <el-tag
          v-for="chip in promptChips"
          :key="chip"
          class="prompt-chip"
          effect="plain"
          @click="$emit('append-prompt', chip)"
        >
          {{ chip }}
        </el-tag>
      </div>

      <details class="minor-options">
        <summary>高级设置</summary>
        <el-form-item label="排除项">
          <el-input v-model="form.negative_prompt" clearable></el-input>
        </el-form-item>
        <el-form-item label="保持原有结构">
          <el-switch v-model="form.keep_structure" inline-prompt active-text="开" inactive-text="关"></el-switch>
        </el-form-item>
        <el-form-item label="局部重绘笔刷">
          <el-slider :model-value="brushSize" :min="8" :max="72" @update:model-value="$emit('update:brushSize', $event)"></el-slider>
        </el-form-item>
        <div class="note-toolbar">
          <el-button size="small" :type="noteMode ? 'primary' : 'default'" plain :disabled="!maskDirty" @click="toggleNoteMode">
            掩码标签
          </el-button>
          <el-button size="small" plain :disabled="!designNotes.length" @click="$emit('clear-design-notes')">清空标签</el-button>
          <span>{{ maskNoteHint }}</span>
        </div>
        <div class="canvas-stack">
          <img v-if="draftPreview" class="canvas-draft-image" :src="draftPreview" alt="设计底稿预览" />
          <span v-else class="canvas-empty-hint">上传底稿后可进行局部重绘和便签标注</span>
          <canvas ref="draftCanvasRef" class="draft-canvas" width="960" height="540"></canvas>
          <canvas ref="maskCanvasRef" width="960" height="540"></canvas>
          <div
            v-if="pendingNote"
            class="design-note-editor"
            :class="noteEditorClass"
            :style="noteEditorStyle"
            @pointerdown.stop
            @click.stop
          >
            <el-input
              ref="noteInputRef"
              v-model="pendingNoteText"
              size="small"
              maxlength="80"
              placeholder="说明这片掩码要改成什么"
              @keyup.enter="confirmPendingNote"
            ></el-input>
            <div class="design-note-editor-actions">
              <el-button size="small" type="primary" @click="confirmPendingNote">确定</el-button>
              <el-button size="small" plain @click="cancelPendingNote">取消</el-button>
            </div>
          </div>
          <button
            v-for="note in designNotes"
            :key="note.no"
            type="button"
            class="design-note-marker"
            :style="{ left: `${note.x * 100}%`, top: `${note.y * 100}%` }"
            :title="`掩码区域：${note.text}`"
            @click.stop="$emit('remove-design-note', note.no)"
          >
            {{ note.no }}
          </button>
        </div>
        <div v-if="designNotes.length" class="design-note-list">
          <div v-for="note in designNotes" :key="note.no" class="design-note-item">
            <strong>{{ note.no }}</strong>
            <span>{{ note.text }}</span>
            <el-button size="small" text type="danger" @click="$emit('remove-design-note', note.no)">删除</el-button>
          </div>
        </div>
        <div class="mask-actions">
          <el-tag size="small" :type="maskDirty ? 'success' : 'info'">{{ maskState }}</el-tag>
          <el-button size="small" @click="clearMask">清空掩码</el-button>
        </div>
      </details>
    </el-form>

    <div class="submit-bar">
      <el-button class="generate-button" type="primary" size="large" :loading="submitting" @click="$emit('submit-design')">
        开始生成设计图
      </el-button>
      <span>{{ taskStateText }}</span>
    </div>
  </section>
</template>

<script>
export default {
  name: "ControlPanel",
  props: {
    draftPreview: {
      type: String,
      default: "",
    },
    draftState: {
      type: String,
      required: true,
    },
    aspectRatios: {
      type: Array,
      required: true,
    },
    promptOptimizing: {
      type: Boolean,
      default: false,
    },
    quickPresets: {
      type: Array,
      required: true,
    },
    presets: {
      type: Object,
      required: true,
    },
    promptChips: {
      type: Array,
      required: true,
    },
    form: {
      type: Object,
      required: true,
    },
    brushSize: {
      type: Number,
      required: true,
    },
    maskDirty: {
      type: Boolean,
      required: true,
    },
    maskState: {
      type: String,
      required: true,
    },
    submitting: {
      type: Boolean,
      default: false,
    },
    taskStateText: {
      type: String,
      required: true,
    },
    isPresetActive: {
      type: Function,
      required: true,
    },
    recommendationLoading: {
      type: Boolean,
      default: false,
    },
    recommendationHint: {
      type: String,
      default: "上传底稿后，可由大模型识别图片并生成4个提示词模板",
    },
    recommendationActive: {
      type: Boolean,
      default: false,
    },
    designNotes: {
      type: Array,
      default: () => [],
    },
  },
  emits: [
    "handle-file",
    "apply-quick-preset",
    "append-prompt",
    "refresh-style-templates",
    "optimize-prompt",
    "clear-draft",
    "submit-design",
    "add-design-note",
    "remove-design-note",
    "clear-design-notes",
    "update:brushSize",
    "update:maskDirty",
    "update:maskState",
  ],
  data() {
    return {
      noteMode: false,
      pendingNote: null,
      pendingNoteText: "",
    };
  },
  computed: {
    // Keep the inline note editor inside the image bounds.
    noteEditorClass() {
      if (!this.pendingNote) return {};
      return {
        "align-left": this.pendingNote.x < 0.24,
        "align-right": this.pendingNote.x > 0.76,
      };
    },

    // Position the inline note editor near the clicked point.
    noteEditorStyle() {
      if (!this.pendingNote) return {};
      const top = `${this.pendingNote.y * 100}%`;
      if (this.pendingNote.x < 0.24) {
        return { left: "12px", top };
      }
      if (this.pendingNote.x > 0.76) {
        return { right: "12px", top };
      }
      return { left: `${this.pendingNote.x * 100}%`, top };
    },
    // Return the mask note toolbar hint.
    maskNoteHint() {
      if (!this.maskDirty) return "先涂黑需要修改的区域，再添加标签";
      return this.noteMode ? "点击掩码区域，说明这片区域要改成什么" : "标签只描述掩码区域，修改范围仍以黑色掩码为准";
    },
  },
  // Run component startup work.
  mounted() {
    this.setupCanvas();
    if (this.draftPreview) this.drawDraftToCanvas(this.draftPreview);
  },
  watch: {
    draftPreview(url) {
      if (url) {
        this.$nextTick(() => this.drawDraftToCanvas(url));
      } else {
        this.clearDraftCanvas();
      }
    },
  },
  methods: {
    // Initialize the mask canvas.
    setupCanvas() {
      const canvas = this.$refs.maskCanvasRef;
      if (!canvas) return;
      if (canvas.dataset.bound === "true") return;
      canvas.dataset.bound = "true";
      const ctx = canvas.getContext("2d");
      ctx.lineCap = "round";
      ctx.lineJoin = "round";

      // Handle pointer down drawing.
      canvas.addEventListener("pointerdown", (event) => {
        if (this.noteMode) {
          this.addNoteFromPointer(event);
          return;
        }
        canvas.setPointerCapture(event.pointerId);
        const p = this.canvasPoint(event);
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
      });

      // Handle pointer move drawing.
      canvas.addEventListener("pointermove", (event) => {
        if (this.noteMode) return;
        if (event.buttons !== 1) return;
        const p = this.canvasPoint(event);
        ctx.strokeStyle = "rgba(0, 0, 0, 0.72)";
        ctx.lineWidth = Number(this.brushSize);
        ctx.lineTo(p.x, p.y);
        ctx.stroke();
        this.$emit("update:maskDirty", true);
        this.$emit("update:maskState", "已绘制");
      });
    },

    // Add a mask note at the clicked image position.
    addNoteFromPointer(event) {
      const canvas = this.$refs.maskCanvasRef;
      const p = this.canvasPoint(event);
      this.pendingNote = {
        x: Math.max(0.04, Math.min(0.96, p.x / canvas.width)),
        y: Math.max(0.08, Math.min(0.92, p.y / canvas.height)),
      };
      this.pendingNoteText = "";
      this.$nextTick(() => this.$refs.noteInputRef?.focus?.());
    },

    // Toggle note mode and clear unfinished note input when leaving.
    toggleNoteMode() {
      this.noteMode = !this.noteMode;
      if (!this.noteMode) this.cancelPendingNote();
    },

    // Save the pending mask note.
    confirmPendingNote() {
      const text = this.pendingNoteText.trim();
      if (!this.pendingNote || !text) return;
      this.$emit("add-design-note", {
        x: this.pendingNote.x,
        y: this.pendingNote.y,
        text,
      });
      this.cancelPendingNote();
    },

    // Cancel unfinished note input.
    cancelPendingNote() {
      this.pendingNote = null;
      this.pendingNoteText = "";
    },

    // Calculate pointer coordinates on canvas.
    canvasPoint(event) {
      const canvas = this.$refs.maskCanvasRef;
      const rect = canvas.getBoundingClientRect();
      return {
        x: ((event.clientX - rect.left) / rect.width) * canvas.width,
        y: ((event.clientY - rect.top) / rect.height) * canvas.height,
      };
    },

    // Draw the draft image on canvas.
    drawDraftToCanvas(url) {
      const canvas = this.$refs.draftCanvasRef;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      const img = new Image();
      img.crossOrigin = "anonymous";
      // Draw the image after it loads.
      img.onload = () => {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = "#f7f4ed";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        const scale = Math.min(canvas.width / img.width, canvas.height / img.height);
        const w = img.width * scale;
        const h = img.height * scale;
        const x = (canvas.width - w) / 2;
        const y = (canvas.height - h) / 2;
        ctx.globalAlpha = 0.78;
        ctx.drawImage(img, x, y, w, h);
        ctx.globalAlpha = 1;
      };
      img.src = url;
    },

    // Clear the hidden draft canvas.
    clearDraftCanvas() {
      const canvas = this.$refs.draftCanvasRef;
      if (!canvas) return;
      canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
    },

    // Clear the mask canvas.
    clearMask() {
      const canvas = this.$refs.maskCanvasRef;
      if (!canvas) return;
      canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
      this.cancelPendingNote();
      this.noteMode = false;
      this.$emit("clear-design-notes");
      this.$emit("update:maskDirty", false);
      this.$emit("update:maskState", "未绘制");
    },

    // Convert the mask canvas to a blob.
    canvasToBlob() {
      const canvas = this.$refs.maskCanvasRef;
      return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    },
  },
};
</script>
