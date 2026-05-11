<template>
  <div v-cloak>
    <auth-panel
      v-if="!isAuthenticated"
      v-model:auth-mode="authMode"
      :auth-form="authForm"
      :auth-loading="authLoading"
      @submit-auth="submitAuth"
    />
    <template v-else>
      <app-header :current-user="currentUser" @open-admin="openAdminPanel" @logout="logout" />
      <main class="workspace">
        <control-panel
          ref="controlPanelRef"
          :draft-preview="draftPreview"
          :draft-state="draftState"
          :quick-presets="quickPresets"
          :presets="presets"
          :aspect-ratios="aspectRatios"
          :prompt-chips="promptChips"
          :form="form"
          :brush-size="brushSize"
          :mask-dirty="maskDirty"
          :mask-state="maskState"
          :submitting="submitting"
          :task-state-text="taskStateText"
          :is-preset-active="isPresetActive"
          :recommendation-loading="recommendationLoading"
          :recommendation-hint="recommendationHint"
          :recommendation-active="recommendationActive"
          :prompt-optimizing="promptOptimizing"
          @handle-file="handleFile"
          @apply-quick-preset="applyQuickPreset"
          @append-prompt="appendPrompt"
          @refresh-style-templates="refreshStyleTemplates"
          @optimize-prompt="optimizePrompt"
          @submit-design="submitDesign"
          @update:brush-size="brushSize = $event"
          @update:mask-dirty="maskDirty = $event"
          @update:mask-state="maskState = $event"
        />
        <result-panel
          :display-result-image="displayResultImage"
          :display-draft-preview="displayDraftPreview"
          :display-ref-preview="displayRefPreview"
          :is-generating="isGenerating"
          :task-state-text="taskStateText"
          :current-task-id="currentTaskId"
          :selected-record="selectedRecord"
          :saved-schemes="savedSchemes"
          :selected-saved-scheme-id="selectedSavedSchemeId"
          :history="history"
          :selected-history-task-id="selectedHistoryTaskId"
          :presets="presets"
          :record-style-filter="recordStyleFilter"
          :feedback-submitting="feedbackSubmitting"
          :short-task-id="shortTaskId"
          :can-compare-record="canCompareRecord"
          @save-current-scheme="saveCurrentScheme"
          @download-result-image="downloadResultImage"
          @save-pdf-report="savePdfReport"
          @compare-record-images="compareRecordImages"
          @delete-current-record="deleteCurrentRecord"
          @preview-image="previewImage"
          @load-favorites="loadFavorites"
          @select-saved-scheme="selectSavedScheme"
          @remove-favorite="removeFavorite"
          @save-feedback="saveDesignFeedback"
          @update:record-style-filter="recordStyleFilter = $event"
          @load-design-records="loadDesignRecords"
          @open-history="openHistory"
        />
      </main>
      <image-dialogs v-model:image-preview="imagePreview" v-model:compare-preview="comparePreview" />
      <admin-panel v-model="adminVisible" :dashboard="adminDashboard" :loading="adminLoading" @refresh-admin="loadAdminDashboard" />
    </template>
  </div>
</template>
<script>
import { nextTick } from "vue";
import { ElMessage } from "element-plus";
import AppHeader from "./components/AppHeader.vue";
import AdminPanel from "./components/AdminPanel.vue";
import AuthPanel from "./components/AuthPanel.vue";
import ControlPanel from "./components/ControlPanel.vue";
import ImageDialogs from "./components/ImageDialogs.vue";
import ResultPanel from "./components/ResultPanel.vue";

const statusText = {
  1: "已创建",
  2: "处理中",
  3: "已完成",
  4: "失败",
};

const defaultPresets = {
  roomTypes: ["客厅", "卧室", "厨房", "餐厅", "书房", "儿童房", "玄关", "卫生间"],
  styles: ["现代简约", "新中式", "北欧", "中古风", "奶油风", "侘寂风", "工业风", "轻奢"],
  colors: ["暖白+原木", "黑白灰", "米色+胡桃木", "低饱和莫兰迪", "奶油色+浅咖", "深色沉稳"],
  materials: ["原木", "微水泥", "大理石", "藤编", "金属线条", "布艺", "皮革", "玻璃"],
};

const quickPresets = [
  {
    name: "现代奶油客厅",
    style: "奶油风",
    room: "客厅",
    color: "奶油色+浅咖",
    material: "布艺",
    prompt:
      "保留客厅结构，提升空间通透感，加入柔和奶油色墙面、圆角家具和温暖灯带，整体干净舒适。",
    desc: "柔和、明亮、适合年轻家庭",
  },
  {
    name: "新中式会客区",
    style: "新中式",
    room: "客厅",
    color: "米色+胡桃木",
    material: "原木",
    prompt:
      "保留空间边界，生成克制雅致的新中式会客区，强调木质格栅、留白与东方秩序感。",
    desc: "稳重、雅致、结构清晰",
  },
  {
    name: "北欧卧室",
    style: "北欧",
    room: "卧室",
    color: "暖白+原木",
    material: "原木",
    prompt:
      "保留卧室结构，呈现自然松弛的北欧卧室，光线柔和，床品简洁，适度加入收纳。",
    desc: "轻盈、自然、居住感强",
  },
  {
    name: "侘寂书房",
    style: "侘寂风",
    room: "书房",
    color: "深色沉稳",
    material: "微水泥",
    prompt:
      "保留书房结构，生成克制安静的侘寂空间，突出材质肌理、灰调光影和低干扰工作氛围。",
    desc: "安静、克制、材质感强",
  },
];

const initialQuickPresets = quickPresets.map((item) => ({ ...item }));

const promptChips = [
  "增强自然采光",
  "保留电视墙位置",
  "提升收纳能力",
  "加入柔和灯带",
  "减少空间压迫感",
  "突出木质肌理",
  "加强餐厨一体感",
  "保留通行动线",
];

const aspectRatios = [
  { label: "1:1", value: "1:1" },
  { label: "16:9", value: "16:9" },
  { label: "9:16", value: "9:16" },
  { label: "4:3", value: "4:3" },
  { label: "3:4", value: "3:4" },
  { label: "自由", value: "" },
];

export default {
  components: {
    AdminPanel,
    AppHeader,
    AuthPanel,
    ControlPanel,
    ImageDialogs,
    ResultPanel,
  },

  data() {
    return {
      apiBaseInput: window.location.protocol === "file:" ? "http://127.0.0.1:8001" : "",
      authMode: "login",
      authLoading: false,
      authToken: localStorage.getItem("home-design-token") || "",
      currentUser: null,
      authForm: {
        username: "",
        password: "",
      },
      provider: "checking",
      activeTab: "studio",
      projectDrawer: false,
      compareMode: "draft-result",
      compareSlider: 52,
      presets: { ...defaultPresets },
      quickPresets,
      promptChips,
      aspectRatios,
      draftAsset: null,
      refAsset: null,
      draftPreview: "",
      refPreview: "",
      draftState: "未上传",
      refState: "未上传",
      maskState: "未绘制",
      maskDirty: false,
      brushSize: 28,
      submitting: false,
      currentTaskId: "",
      generatingTaskId: "",
      taskStateText: "等待提交",
      resultImage: "",
      pollTimer: null,
      pollingTaskId: "",
      pollTickCount: 0,
      selectedSavedSchemeId: "",
      savedSchemes: [],
      adminVisible: false,
      adminLoading: false,
      adminDashboard: {},
      promptOptimizing: false,
      feedbackSubmitting: false,
      recommendationLoading: false,
      recommendationHint: "上传底稿后，可由大模型识别图片并生成4个提示词模板",
      recommendationActive: false,
      activePresetName: "",
      styleTemplateSeed: 0,
      history: JSON.parse(localStorage.getItem("home-design-history") || "[]"),
      recordCache: {},
      selectedRecord: null,
      selectedHistoryTaskId: "",
      imagePreview: {
        visible: false,
        title: "",
        url: "",
      },
      comparePreview: {
        visible: false,
        draftUrl: "",
        resultUrl: "",
      },
      recordStyleFilter: "",
      project: {
        name: "青禾里 120㎡ 家装改造",
        stage: "方案生成",
        clientType: "年轻家庭",
        notes: "重点关注客厅采光、动线顺畅和儿童活动区域安全感。",
      },
      form: {
        mode: "basic",
        prompt: "保留原户型结构，生成一个明亮、真实、适合年轻家庭居住的客厅方案。",
        image_urls: [],
        room_type: "客厅",
        design_style: "现代简约",
        color_preference: "暖白+原木",
        material_preference: "原木",
        keep_structure: true,
        mask_url: null,
        negative_prompt: "不要改变门窗位置，不要生成不合理家具比例",
        resolution: "1K",
        aspect_ratio: "16:9",
        output_format: "png",
      },
    };
  },

  computed: {
    isAuthenticated() {
      return Boolean(this.authToken && this.currentUser);
    },

    providerText() {
      if (this.provider === "mock") return "演示模式";
      if (this.provider === "nanobanana") return "API 模式";
      if (this.provider === "error") return "未连接";
      return "连接中";
    },

    providerTagType() {
      if (this.provider === "mock") return "warning";
      if (this.provider === "nanobanana") return "success";
      if (this.provider === "error") return "danger";
      return "info";
    },

    activeStep() {
      if (this.savedSchemes.length) return 5;
      if (this.maskDirty) return 4;
      if (this.currentTaskId) return 3;
      if (this.form.prompt.trim() && (this.form.room_type || this.form.design_style)) return 2;
      if (this.draftAsset || this.refAsset) return 1;
      return 0;
    },

    structureScore() {
      let score = this.form.keep_structure ? 84 : 62;
      if (this.draftAsset) score += 8;
      if (this.maskDirty) score += 4;
      return Math.min(score, 98);
    },

    styleScore() {
      let score = 72;
      if (this.refAsset) score += 10;
      if (this.form.design_style) score += 8;
      return Math.min(score, 96);
    },

    materialScore() {
      let score = 66;
      if (this.form.material_preference) score += 10;
      if (this.form.color_preference) score += 6;
      return Math.min(score, 94);
    },

    compareBaseImage() {
      if (this.compareMode === "result-saved") {
        return this.resultImage || "";
      }
      return this.draftPreview || this.resultImage || "";
    },

    compareTargetImage() {
      if (this.compareMode === "result-saved") {
        return this.selectedSavedScheme?.image || this.resultImage || "";
      }
      return this.resultImage || this.selectedSavedScheme?.image || "";
    },

    selectedSavedScheme() {
      return this.savedSchemes.find((item) => item.id === this.selectedSavedSchemeId) || null;
    },

    displayDraftPreview() {
      if (this.selectedHistoryTaskId) {
        return this.selectedRecord?.task_id === this.selectedHistoryTaskId
          ? this.selectedRecord.draft_image_url || ""
          : "";
      }
      return this.draftPreview;
    },

    displayRefPreview() {
      if (this.selectedHistoryTaskId) {
        return this.selectedRecord?.task_id === this.selectedHistoryTaskId
          ? this.selectedRecord.reference_image_url || ""
          : "";
      }
      return this.refPreview;
    },

    displayResultImage() {
      if (this.selectedHistoryTaskId) {
        return this.selectedRecord?.task_id === this.selectedHistoryTaskId
          ? this.selectedRecord.result_image_url || ""
          : "";
      }
      return this.resultImage;
    },

    isGenerating() {
      return this.submitting || (Boolean(this.generatingTaskId) && !this.taskStateText.includes("失败"));
    },

    currentInsights() {
      return [
        {
          title: "结构建议",
          text: this.form.keep_structure
            ? "当前已启用结构保持，适合做户型不变的软硬装方案生成。"
            : "如果你要严格保留门窗与墙体位置，建议把结构保持打开。",
        },
        {
          title: "风格建议",
          text: `${this.form.design_style || "当前风格"} + ${this.form.color_preference || "当前色彩"} 的组合更适合用于首轮定调。`,
        },
        {
          title: "生成建议",
          text:
            this.refAsset
              ? "已经具备风格参考图，当前更适合做高保真风格迁移。"
              : "还没有参考图时，建议在需求描述里多写灯光、材质和氛围关键词。",
        },
      ];
    },
  },

  mounted() {
    this.history = this.normalizeHistory(this.history);
    this.saveHistory();
    this.loadPresets();
    this.loadHealth();
    if (this.authToken) {
      this.loadMe();
    }
  },

  beforeUnmount() {
    window.clearTimeout(this.pollTimer);
  },

  methods: {
    apiBase() {
      const raw = this.apiBaseInput.trim();
      if (raw) return raw.replace(/\/$/, "");
      if (window.location.protocol === "file:") return "http://127.0.0.1:8001";
      return "";
    },

    apiPath(path) {
      return `${this.apiBase()}${path}`;
    },

    assetPreviewUrl(url) {
      if (!url || !url.startsWith("/")) return url;
      return this.apiPath(url);
    },

    async request(path, options = {}) {
      const headers = new Headers(options.headers || {});
      if (this.authToken && !headers.has("Authorization")) {
        headers.set("Authorization", `Bearer ${this.authToken}`);
      }
      const res = await fetch(this.apiPath(path), { ...options, headers });
      const text = await res.text();
      const data = text ? JSON.parse(text) : null;
      if (!res.ok) {
        if (res.status === 401 && !path.includes("/api/v1/auth/")) {
          this.clearAuth();
        }
        const error = new Error(data?.detail || `HTTP ${res.status}`);
        error.status = res.status;
        throw error;
      }
      return data;
    },

    async submitAuth() {
      if (!this.authForm.username.trim() || !this.authForm.password) {
        ElMessage.warning("请输入账号和密码");
        return;
      }
      this.authLoading = true;
      try {
        const auth = await this.request(`/api/v1/auth/${this.authMode}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            username: this.authForm.username.trim(),
            password: this.authForm.password,
          }),
        });
        this.applyAuth(auth);
        ElMessage.success(this.authMode === "login" ? "登录成功" : "注册成功");
      } catch (err) {
        ElMessage.error(err.message);
      } finally {
        this.authLoading = false;
      }
    },

    applyAuth(auth) {
      this.authToken = auth.token;
      this.currentUser = auth.user;
      localStorage.setItem("home-design-token", auth.token);
      this.authForm.password = "";
      this.history = [];
      this.savedSchemes = [];
      this.recordCache = {};
      this.selectedRecord = null;
      this.selectedHistoryTaskId = "";
      nextTick(() => this.setupCanvas());
      this.loadDesignRecords(false);
      this.loadFavorites(false);
    },

    async loadMe() {
      try {
        const user = await this.request("/api/v1/auth/me");
        this.currentUser = user;
        nextTick(() => this.setupCanvas());
        this.loadDesignRecords(false);
        this.loadFavorites(false);
      } catch (err) {
        this.clearAuth();
      }
    },

    clearAuth() {
      this.authToken = "";
      this.currentUser = null;
      this.currentTaskId = "";
      this.generatingTaskId = "";
      this.taskStateText = "等待提交";
      this.resultImage = "";
      this.history = [];
      this.savedSchemes = [];
      this.recordCache = {};
      this.selectedRecord = null;
      this.selectedHistoryTaskId = "";
      localStorage.removeItem("home-design-token");
    },

    async logout() {
      try {
        await this.request("/api/v1/auth/logout", { method: "POST" });
      } catch (err) {
        // Local logout is still valid if the server session was already gone.
      }
      this.clearAuth();
      ElMessage.success("已退出登录");
    },

    reloadBackend() {
      this.loadHealth();
      this.loadPresets();
    },

    async openAdminPanel() {
      this.adminVisible = true;
      await this.loadAdminDashboard();
    },

    async loadAdminDashboard() {
      if (!this.isAuthenticated) return;
      this.adminLoading = true;
      try {
        this.adminDashboard = await this.request("/api/v1/admin/dashboard");
      } catch (err) {
        ElMessage.error(err.message);
      } finally {
        this.adminLoading = false;
      }
    },

    previewImage(url, title = "图片预览") {
      if (!url) return;
      this.imagePreview = {
        visible: true,
        title,
        url,
      };
    },

    canCompareRecord(record = this.selectedRecord) {
      return Boolean(record?.draft_image_url && record?.result_image_url);
    },

    compareRecordImages(record = this.selectedRecord) {
      if (!this.canCompareRecord(record)) {
        ElMessage.warning("当前记录缺少底稿或结果图，无法对比");
        return;
      }
      this.comparePreview = {
        visible: true,
        draftUrl: record.draft_image_url,
        resultUrl: record.result_image_url,
      };
    },

    async loadHealth() {
      try {
        const health = await this.request("/healthz");
        this.provider = health.provider || "nanobanana";
      } catch (err) {
        this.provider = "error";
      }
    },

    async loadPresets() {
      try {
        const presets = await this.request("/api/v1/design/presets");
        this.presets = { ...defaultPresets, ...presets };
        this.applyPresetDefaults();
      } catch (err) {
        this.presets = { ...defaultPresets };
      }
    },

    applyPresetDefaults() {
      const defaults = [
        ["room_type", this.presets.roomTypes],
        ["design_style", this.presets.styles],
        ["color_preference", this.presets.colors],
        ["material_preference", this.presets.materials],
      ];
      for (const [key, list] of defaults) {
        if (!this.form[key] && list?.length) this.form[key] = list[0];
      }
    },

    async handleFile(file, type) {
      const raw = file?.raw || file;
      if (!raw) return;
      const label = type === "draft" ? "底稿" : "参考图";
      try {
        ElMessage.info(`正在上传${label}...`);
        const asset = await this.uploadBlob(raw, raw.name, raw.type);
        this.setAsset(type, asset.url, this.assetPreviewUrl(asset.local_url));
        if (asset.warning) {
          ElMessage.warning(asset.warning);
        } else {
          ElMessage.success(`${label}上传完成`);
        }
      } catch (err) {
        ElMessage.error(err.message);
      }
    },

    setAsset(type, url, previewUrl) {
      const asset = { url, previewUrl };
      this.prepareNewDesignView();
      this.quickPresets = initialQuickPresets.map((item) => ({ ...item }));
      this.recommendationActive = false;
      this.activePresetName = "";
      this.recommendationHint = "已更新上传图片，点击智能推荐生成新的提示词模板";
      if (type === "draft") {
        this.draftAsset = asset;
        this.draftPreview = previewUrl;
        this.draftState = "已就绪";
        nextTick(() => this.drawDraftToCanvas(previewUrl));
      } else {
        this.refAsset = asset;
        this.refPreview = previewUrl;
        this.refState = "已就绪";
      }
    },

    prepareNewDesignView() {
      window.clearTimeout(this.pollTimer);
      this.pollingTaskId = "";
      this.pollTickCount = 0;
      this.generatingTaskId = "";
      this.currentTaskId = "";
      this.selectedHistoryTaskId = "";
      this.selectedRecord = null;
      this.selectedSavedSchemeId = "";
      this.resultImage = "";
      this.taskStateText = "等待提交";
      this.activeTab = "studio";
      this.project.stage = "方案准备";
    },

    async uploadBlob(blob, filename, contentType = "image/png") {
      return this.request(`/api/v1/assets/upload?filename=${encodeURIComponent(filename || "upload.png")}`, {
        method: "POST",
        headers: { "Content-Type": contentType || "image/png" },
        body: blob,
      });
    },

    setupCanvas() {
      this.$refs.controlPanelRef?.setupCanvas?.();
    },

    drawDraftToCanvas(url) {
      this.$refs.controlPanelRef?.drawDraftToCanvas?.(url);
    },

    clearMask() {
      if (this.$refs.controlPanelRef?.clearMask) {
        this.$refs.controlPanelRef.clearMask();
      } else {
        this.maskDirty = false;
        this.maskState = "未绘制";
      }
    },

    canvasToBlob() {
      return this.$refs.controlPanelRef?.canvasToBlob?.();
    },

    appendPrompt(text) {
      const trimmed = this.form.prompt.trim();
      this.form.prompt = trimmed ? `${trimmed}，${text}` : text;
    },

    async optimizePrompt() {
      if (!this.form.prompt.trim()) {
        ElMessage.warning("请先填写需求描述");
        return;
      }
      this.promptOptimizing = true;
      try {
        const response = await this.request("/api/v1/prompts/optimize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompt: this.form.prompt,
            room_type: this.form.room_type,
            design_style: this.form.design_style,
            color_preference: this.form.color_preference,
            material_preference: this.form.material_preference,
            aspect_ratio: this.form.aspect_ratio,
          }),
        });
        this.form.prompt = response.prompt || this.form.prompt;
        ElMessage.success(response.summary || "提示词已优化");
      } catch (err) {
        if (err.status === 404) {
          ElMessage.error("后端未加载提示词优化接口，请重启 start_fullstack.bat 后再试");
        } else {
          ElMessage.error(err.message);
        }
      } finally {
        this.promptOptimizing = false;
      }
    },

    isPresetActive(preset) {
      return Boolean(this.activePresetName && this.activePresetName === preset.name);
    },

    applyQuickPreset(preset) {
      this.activePresetName = preset.name;
      this.recommendationActive = false;
      this.form.room_type = preset.room;
      this.form.design_style = preset.style;
      this.form.color_preference = preset.color;
      this.form.material_preference = preset.material;
      this.form.prompt = preset.prompt;
      ElMessage.success(`已套用「${preset.name}」模板`);
    },

    recommendationImageUrls() {
      const imageUrls = [];
      if (this.draftAsset?.url) imageUrls.push(this.draftAsset.url);
      if (this.refAsset?.url) imageUrls.push(this.refAsset.url);
      return imageUrls;
    },

    async refreshStyleTemplates(showMessage = true) {
      if (!this.isAuthenticated) return;
      const imageUrls = this.recommendationImageUrls();
      if (!imageUrls.length) {
        if (showMessage) ElMessage.warning("请先上传底稿或风格参考图");
        return;
      }
      this.recommendationLoading = true;
      this.styleTemplateSeed += 1;
      try {
        const response = await this.request("/api/v1/recommendations/style-templates", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            room_type: this.form.room_type,
            design_style: this.form.design_style,
            color_preference: this.form.color_preference,
            material_preference: this.form.material_preference,
            prompt: this.form.prompt,
            image_urls: imageUrls,
            refresh_seed: this.styleTemplateSeed,
          }),
        });
        if (response?.templates?.length) {
          this.quickPresets = response.templates;
          this.recommendationHint = response.summary || "已生成图片智能推荐模板";
          this.activePresetName = "";
          this.recommendationActive = response?.source === "vision";
        }
        if (showMessage) {
          if (response?.source === "vision") {
            ElMessage.success("图片智能推荐已生成");
          } else {
            ElMessage.warning(response?.summary || "智能推荐暂不可用，已保留初始模板");
          }
        }
      } catch (err) {
        if (showMessage) ElMessage.error(err.message);
      } finally {
        this.recommendationLoading = false;
      }
    },

    async submitDesign() {
      if (!this.form.prompt.trim()) {
        ElMessage.warning("请填写需求描述");
        return;
      }

      this.submitting = true;
      this.taskStateText = "提交中";
      this.project.stage = "方案生成";
      this.currentTaskId = "";
      this.generatingTaskId = "";
      this.resultImage = "";
      this.selectedRecord = null;
      this.selectedHistoryTaskId = "";
      this.selectedSavedSchemeId = "";
      this.imagePreview = { visible: false, title: "", url: "" };
      this.comparePreview = { visible: false, draftUrl: "", resultUrl: "" };

      try {
        const imageUrls = [];
        if (this.draftAsset?.url) imageUrls.push(this.draftAsset.url);
        if (this.refAsset?.url) imageUrls.push(this.refAsset.url);

        let maskUrl = null;
        if (this.maskDirty) {
          const maskBlob = await this.canvasToBlob();
          const maskAsset = await this.uploadBlob(maskBlob, "mask.png", "image/png");
          maskUrl = maskAsset.url;
        }

        const body = {
          ...this.form,
          image_urls: imageUrls,
          mask_url: maskUrl,
          prompt: this.form.prompt.trim(),
          negative_prompt: this.form.negative_prompt.trim(),
        };

        const submitted = await this.request("/api/v1/design/submit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });

        this.currentTaskId = submitted.task_id;
        this.generatingTaskId = submitted.task_id;
        this.taskStateText = `处理中 · ${this.shortTaskId(submitted.task_id)}`;
        this.addHistory(submitted.task_id, "处理中", Date.now());
        this.startPolling(submitted.task_id, true);
      } catch (err) {
        this.taskStateText = "提交失败";
        ElMessage.error(err.message);
      } finally {
        this.submitting = false;
      }
    },

    startPolling(taskId, immediate = false) {
      window.clearTimeout(this.pollTimer);
      this.pollingTaskId = taskId;
      this.pollTickCount = 0;

      const tick = async () => {
        if (this.pollingTaskId !== taskId) return;
        await this.refreshTask(taskId, false);
        if (this.pollingTaskId !== taskId || this.generatingTaskId !== taskId) return;

        this.pollTickCount += 1;
        const delay = this.pollTickCount < 30 ? 1000 : 2200;
        this.pollTimer = window.setTimeout(tick, delay);
      };

      this.pollTimer = window.setTimeout(tick, immediate ? 0 : 800);
    },

    refreshCurrentTask() {
      const taskId = this.generatingTaskId || this.currentTaskId;
      if (taskId) this.refreshTask(taskId, true);
    },

    async refreshTask(taskId, manual) {
      if (!taskId) return;
      try {
        let task = await this.request(`/api/v1/tasks/${encodeURIComponent(taskId)}`);
        if (![3, 4].includes(Number(task.status))) {
          try {
            task = await this.request(`/api/v1/tasks/${encodeURIComponent(taskId)}/refresh`, { method: "POST" });
          } catch (err) {
            if (manual) throw err;
          }
        }
        this.renderTask(task);
      } catch (err) {
        ElMessage.error(err.message);
      }
    },

    renderTask(task) {
      const status = Number(task.status);
      const isPrimaryTask = !this.generatingTaskId || task.task_id === this.generatingTaskId;
      if (isPrimaryTask) {
        this.currentTaskId = task.task_id;
        this.taskStateText = `${statusText[status] || "未知"} · ${this.shortTaskId(task.task_id)}`;
      }
      this.addHistory(task.task_id, statusText[status] || "未知", task.created_at);

      if (isPrimaryTask && task.result_image_url) {
        this.resultImage = task.result_image_url;
        this.activeTab = "studio";
      }
      if (task.result_image_url || [3, 4].includes(status)) {
        this.loadDesignRecord(task.task_id, false);
      }
      if (task.error_message) {
        ElMessage.error(task.error_message);
      }
      if ([3, 4].includes(status)) {
        if (task.task_id === this.generatingTaskId) {
          this.generatingTaskId = "";
        }
        if (task.task_id === this.pollingTaskId) {
          this.pollingTaskId = "";
        }
        window.clearTimeout(this.pollTimer);
      }
    },

    applyRecordAssets(record) {
      if (!record) return;
      this.selectedRecord = record;
    },

    clearInputAssets() {
      this.draftAsset = null;
      this.refAsset = null;
      this.draftPreview = "";
      this.refPreview = "";
      this.draftState = "未上传";
      this.refState = "未上传";
      this.clearMask();
    },

    resultFilename() {
      const sourceTaskId = this.selectedHistoryTaskId || this.currentTaskId;
      const taskPart = sourceTaskId ? this.shortTaskId(sourceTaskId).replace(/\W+/g, "-") : Date.now();
      return `home-design-${taskPart}.png`;
    },

    async downloadResultImage() {
      const imageUrl = this.displayResultImage;
      if (!imageUrl) {
        ElMessage.warning("当前还没有可下载的结果图");
        return;
      }

      try {
        const res = await fetch(imageUrl, { mode: "cors" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        const blobUrl = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = blobUrl;
        link.download = this.resultFilename();
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(blobUrl);
        ElMessage.success("图片已开始下载");
      } catch (err) {
        const link = document.createElement("a");
        link.href = imageUrl;
        link.target = "_blank";
        link.rel = "noopener";
        document.body.appendChild(link);
        link.click();
        link.remove();
        ElMessage.warning("浏览器无法直接下载，已打开原图链接");
      }
    },

    savePdfReport() {
      const record = this.selectedRecord;
      if (!record) {
        ElMessage.warning("请先选择一个已生成的方案");
        return;
      }
      const escapeHtml = (value) =>
        String(value ?? "")
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;");
      const time = record.created_at
        ? new Date(this.toTimestampMs(record.created_at)).toLocaleString()
        : "-";
      const score = (value) => (value ? `${value} / 5` : "-");
      const imageHtml = (title, url) =>
        url
          ? `<section><h2>${title}</h2><img src="${escapeHtml(url)}" alt="${title}" /></section>`
          : `<section><h2>${title}</h2><p>未提供</p></section>`;

      const html = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>家装智能设计方案报告</title>
  <style>
    body { font-family: "Microsoft YaHei", Arial, sans-serif; margin: 32px; color: #172126; }
    h1 { margin: 0 0 8px; font-size: 26px; }
    h2 { margin: 24px 0 10px; font-size: 18px; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    td { border: 1px solid #d8e0e3; padding: 8px 10px; vertical-align: top; }
    td:first-child { width: 140px; color: #66777f; background: #f6f8f9; }
    img { max-width: 100%; max-height: 520px; display: block; margin-top: 8px; border: 1px solid #d8e0e3; }
    p { line-height: 1.7; white-space: pre-wrap; }
    .save-action { margin-bottom: 20px; padding: 8px 18px; border: 1px solid #1b8f7b; color: #0f6f60; background: #fff; border-radius: 4px; cursor: pointer; }
    .hint { color: #66777f; font-size: 13px; }
    @media print { body { margin: 18mm; } button { display: none; } }
  </style>
</head>
<body>
  <button class="save-action" onclick="window.print()">保存为 PDF</button>
  <p class="hint">在弹出的系统窗口中选择“另存为 PDF”即可保存到本地。</p>
  <h1>家装智能设计方案报告</h1>
  <p>任务编号：${escapeHtml(record.task_id)}</p>
  <p>生成时间：${escapeHtml(time)}</p>
  <h2>方案信息</h2>
  <table>
    <tr><td>空间</td><td>${escapeHtml(record.room_type || "-")}</td></tr>
    <tr><td>风格</td><td>${escapeHtml(record.design_style || "-")}</td></tr>
    <tr><td>色彩</td><td>${escapeHtml(record.color_preference || "-")}</td></tr>
    <tr><td>材质</td><td>${escapeHtml(record.material_preference || "-")}</td></tr>
    <tr><td>保持原有结构</td><td>${record.keep_structure ? "是" : "否"}</td></tr>
  </table>
  <h2>设计需求与提示词</h2>
  <p>${escapeHtml(record.prompt || "-")}</p>
  ${record.negative_prompt ? `<p>排除项：${escapeHtml(record.negative_prompt)}</p>` : ""}
  ${imageHtml("设计底稿", record.draft_image_url)}
  ${imageHtml("生成结果", record.result_image_url)}
  <h2>方案评分与反馈</h2>
  <table>
    <tr><td>采光</td><td>${score(record.lighting_score)}</td></tr>
    <tr><td>风格匹配</td><td>${score(record.style_match_score)}</td></tr>
    <tr><td>空间利用</td><td>${score(record.space_utilization_score)}</td></tr>
    <tr><td>满意度</td><td>${score(record.satisfaction_score)}</td></tr>
    <tr><td>文字反馈</td><td>${escapeHtml(record.feedback_text || "-")}</td></tr>
  </table>
</body>
</html>`;
      const reportWindow = window.open("", "_blank");
      if (!reportWindow) {
        ElMessage.warning("浏览器阻止了弹窗，请允许弹窗后重试");
        return;
      }
      reportWindow.document.open();
      reportWindow.document.write(html);
      reportWindow.document.close();
    },

    async saveCurrentScheme() {
      const imageUrl = this.displayResultImage;
      if (!imageUrl) {
        ElMessage.warning("当前还没有可收藏的结果图");
        return;
      }

      const scheme = {
        id: this.currentTaskId || `local-${Date.now()}`,
        taskId: this.currentTaskId || null,
        title: `${this.form.room_type} · ${this.form.design_style}`,
        style: `${this.form.color_preference} / ${this.form.material_preference}`,
        image: imageUrl,
        time: new Date().toLocaleString(),
      };

      try {
        const saved = await this.request("/api/v1/favorites", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            task_id: scheme.taskId,
            title: scheme.title,
            style: scheme.style,
            image: scheme.image,
          }),
        });
        const normalized = this.favoriteToScheme(saved);
        this.savedSchemes = [normalized, ...this.savedSchemes.filter((item) => item.id !== normalized.id)].slice(0, 20);
        await this.selectSavedScheme(normalized);
        this.project.stage = "方案比对";
        ElMessage.success("已收藏当前方案");
      } catch (err) {
        ElMessage.error(err.message);
      }
    },

    async selectSavedScheme(scheme) {
      this.selectedSavedSchemeId = scheme.id;
      this.currentTaskId = scheme.taskId || "";
      this.selectedRecord = null;
      this.selectedHistoryTaskId = "";
      this.compareMode = "result-saved";
      this.activeTab = "compare";
      this.resultImage = scheme.image;

      if (!scheme.taskId) return;

      this.selectedHistoryTaskId = scheme.taskId;
      const cached = this.recordCache[scheme.taskId];
      if (cached) {
        this.selectedRecord = cached;
        this.applyRecordAssets(cached);
        this.resultImage = cached.result_image_url || scheme.image;
      }
      await this.loadDesignRecord(scheme.taskId, false);
    },

    favoriteToScheme(favorite) {
      const createdAt = this.toTimestampMs(favorite.created_at) || Date.now();
      return {
        id: favorite.id,
        taskId: favorite.task_id,
        title: favorite.title,
        style: favorite.style,
        image: favorite.image,
        time: new Date(createdAt).toLocaleString(),
        createdAt,
      };
    },

    async loadFavorites(showMessage = true) {
      try {
        const favorites = await this.request("/api/v1/favorites?limit=30");
        this.savedSchemes = favorites.map((item) => this.favoriteToScheme(item));
        if (showMessage) ElMessage.success("收藏已同步");
      } catch (err) {
        if (showMessage) ElMessage.error(err.message);
      }
    },

    async removeFavorite(scheme) {
      if (!scheme?.id) return;
      try {
        await this.request(`/api/v1/favorites/${encodeURIComponent(scheme.id)}`, { method: "DELETE" });
        this.savedSchemes = this.savedSchemes.filter((item) => item.id !== scheme.id);
        if (this.selectedSavedSchemeId === scheme.id) this.selectedSavedSchemeId = "";
        ElMessage.success("已取消收藏");
      } catch (err) {
        ElMessage.error(err.message);
      }
    },

    async saveDesignFeedback(payload) {
      const taskId = payload?.taskId || this.selectedHistoryTaskId || this.currentTaskId;
      if (!taskId) {
        ElMessage.warning("请先选择一个生成方案");
        return;
      }
      this.feedbackSubmitting = true;
      try {
        const record = await this.request(`/api/v1/design/records/${encodeURIComponent(taskId)}/feedback`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            lighting_score: payload.lighting_score || null,
            style_match_score: payload.style_match_score || null,
            space_utilization_score: payload.space_utilization_score || null,
            satisfaction_score: payload.satisfaction_score || null,
            feedback_text: payload.feedback_text || null,
          }),
        });
        this.cacheRecord(record);
        if (taskId === this.selectedHistoryTaskId || taskId === this.currentTaskId) {
          this.selectedRecord = record;
        }
        await this.loadDesignRecords(false);
        ElMessage.success("评分反馈已保存");
      } catch (err) {
        ElMessage.error(err.message);
      } finally {
        this.feedbackSubmitting = false;
      }
    },

    shortTaskId(taskId) {
      if (!taskId || taskId.length <= 18) return taskId || "";
      return `${taskId.slice(0, 10)}...${taskId.slice(-4)}`;
    },

    normalizeHistory(items) {
      const fallbackBase = Date.now();
      return (Array.isArray(items) ? items : [])
        .filter((item) => item?.taskId)
        .map((item, index) => {
          const createdAt = this.toTimestampMs(item.createdAt) || this.parseHistoryTime(item.time) || fallbackBase - index;
          return {
            ...item,
            createdAt,
            time: item.time || new Date(createdAt).toLocaleString(),
          };
        })
        .sort((a, b) => b.createdAt - a.createdAt)
        .slice(0, 30);
    },

    toTimestampMs(value) {
      const timestamp = Number(value);
      if (!Number.isFinite(timestamp) || timestamp <= 0) return 0;
      return timestamp < 1000000000000 ? timestamp * 1000 : timestamp;
    },

    parseHistoryTime(value) {
      if (!value) return 0;
      const parsed = Date.parse(value);
      return Number.isFinite(parsed) ? parsed : 0;
    },

    saveHistory() {
      localStorage.setItem("home-design-history", JSON.stringify(this.history));
    },

    addHistory(taskId, status, createdAtValue) {
      const existing = this.history.find((item) => item.taskId === taskId);
      const createdAt = existing?.createdAt || this.toTimestampMs(createdAtValue) || Date.now();
      const time = existing?.time || new Date(createdAt).toLocaleString();
      const nextItem = { taskId, status, time, createdAt };

      this.history = [nextItem, ...this.history.filter((item) => item.taskId !== taskId)]
        .sort((a, b) => b.createdAt - a.createdAt)
        .slice(0, 30);
      this.saveHistory();
    },

    recordToHistoryItem(record) {
      return {
        taskId: record.task_id,
        status: statusText[Number(record.status)] || "未知",
        time: new Date(this.toTimestampMs(record.created_at) || Date.now()).toLocaleString(),
        createdAt: this.toTimestampMs(record.created_at) || Date.now(),
      };
    },

    cacheRecord(record) {
      if (!record?.task_id) return;
      this.recordCache = { ...this.recordCache, [record.task_id]: record };
      const shouldSelect =
        record.task_id === this.selectedHistoryTaskId ||
        (!this.selectedHistoryTaskId && record.task_id === this.currentTaskId);
      if (shouldSelect) {
        this.selectedRecord = record;
        this.applyRecordAssets(record);
      }
    },

    async loadDesignRecords(showMessage = true) {
      try {
        const params = new URLSearchParams({ limit: "30" });
        if (this.recordStyleFilter) params.set("design_style", this.recordStyleFilter);
        const records = await this.request(`/api/v1/design/records?${params.toString()}`);
        for (const record of records) this.cacheRecord(record);
        this.history = records.map((record) => this.recordToHistoryItem(record));
        this.saveHistory();
        if (showMessage) ElMessage.success("记录已同步");
      } catch (err) {
        await this.loadServerHistory(false);
        if (showMessage) ElMessage.error(err.message);
      }
    },

    async loadDesignRecord(taskId, showMessage = true) {
      if (!taskId) return;
      try {
        const record = await this.request(`/api/v1/design/records/${encodeURIComponent(taskId)}`);
        this.cacheRecord(record);
        if (taskId === this.selectedHistoryTaskId) {
          this.selectedRecord = record;
          this.applyRecordAssets(record);
        }
        if (!this.generatingTaskId && record.result_image_url) this.resultImage = record.result_image_url;
        if (showMessage) ElMessage.success("记录详情已加载");
      } catch (err) {
        if (taskId === this.selectedHistoryTaskId) {
          this.selectedRecord = this.recordCache[taskId] || null;
        }
        if (showMessage) ElMessage.error(err.message);
      }
    },

    async deleteCurrentRecord() {
      if (!this.currentTaskId) return;
      const ok = window.confirm("确定删除这条设计记录吗？删除后最近任务和详情中将不再显示它。");
      if (!ok) return;
      try {
        await this.request(`/api/v1/design/records/${encodeURIComponent(this.currentTaskId)}`, { method: "DELETE" });
        const nextCache = { ...this.recordCache };
        delete nextCache[this.currentTaskId];
        this.recordCache = nextCache;
        this.history = this.history.filter((item) => item.taskId !== this.currentTaskId);
        this.saveHistory();
        this.selectedRecord = null;
        this.selectedHistoryTaskId = "";
        this.currentTaskId = "";
        this.taskStateText = "等待提交";
        this.resultImage = "";
        ElMessage.success("记录已删除");
      } catch (err) {
        ElMessage.error(err.message);
      }
    },

    async loadServerHistory(showMessage = true) {
      try {
        const tasks = await this.request("/api/v1/tasks?limit=20");
        for (const task of tasks) {
          this.addHistory(task.task_id, statusText[Number(task.status)] || "未知", task.created_at);
        }
        if (showMessage) ElMessage.success("记录已同步");
      } catch (err) {
        if (showMessage) ElMessage.error(err.message);
      }
    },

    openHistory(taskId) {
      this.selectedSavedSchemeId = "";
      this.selectedHistoryTaskId = taskId;
      this.activeTab = "archive";
      this.selectedRecord = this.recordCache[taskId] || null;
      if (!this.generatingTaskId) {
        this.currentTaskId = taskId;
      }
      const cached = this.recordCache[taskId];
      if (cached) {
        this.selectedRecord = cached;
        this.applyRecordAssets(cached);
        if (!this.generatingTaskId && cached.result_image_url) this.resultImage = cached.result_image_url;
      }
      if (!this.generatingTaskId) {
        this.refreshTask(taskId, true);
      }
      this.loadDesignRecord(taskId, true);
    },
  },
}
</script>



