<template>
  <section class="panel control-panel">
    <div class="panel-head">
      <div>
        <span class="eyebrow">1. 输入素材</span>
        <h2>上传底稿</h2>
      </div>
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
        <div class="canvas-stack">
          <canvas ref="draftCanvasRef" width="960" height="540"></canvas>
          <canvas ref="maskCanvasRef" width="960" height="540"></canvas>
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
  },
  emits: [
    "handle-file",
    "apply-quick-preset",
    "append-prompt",
    "refresh-style-templates",
    "optimize-prompt",
    "submit-design",
    "update:brushSize",
    "update:maskDirty",
    "update:maskState",
  ],
  mounted() {
    this.setupCanvas();
    if (this.draftPreview) this.drawDraftToCanvas(this.draftPreview);
  },
  methods: {
    setupCanvas() {
      const canvas = this.$refs.maskCanvasRef;
      if (!canvas) return;
      if (canvas.dataset.bound === "true") return;
      canvas.dataset.bound = "true";
      const ctx = canvas.getContext("2d");
      ctx.lineCap = "round";
      ctx.lineJoin = "round";

      canvas.addEventListener("pointerdown", (event) => {
        canvas.setPointerCapture(event.pointerId);
        const p = this.canvasPoint(event);
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
      });

      canvas.addEventListener("pointermove", (event) => {
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

    canvasPoint(event) {
      const canvas = this.$refs.maskCanvasRef;
      const rect = canvas.getBoundingClientRect();
      return {
        x: ((event.clientX - rect.left) / rect.width) * canvas.width,
        y: ((event.clientY - rect.top) / rect.height) * canvas.height,
      };
    },

    drawDraftToCanvas(url) {
      const canvas = this.$refs.draftCanvasRef;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      const img = new Image();
      img.crossOrigin = "anonymous";
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

    clearMask() {
      const canvas = this.$refs.maskCanvasRef;
      if (!canvas) return;
      canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
      this.$emit("update:maskDirty", false);
      this.$emit("update:maskState", "未绘制");
    },

    canvasToBlob() {
      const canvas = this.$refs.maskCanvasRef;
      return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    },
  },
};
</script>
