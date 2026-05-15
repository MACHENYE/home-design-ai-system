<template>
  <div>
    <el-dialog
      :model-value="imagePreview.visible"
      :title="imagePreview.title"
      width="82%"
      class="image-preview-dialog"
      @update:model-value="updateImageVisible"
    >
      <el-image :src="imagePreview.url" fit="contain" class="dialog-preview-image"></el-image>
    </el-dialog>
    <el-dialog
      :model-value="comparePreview.visible"
      title="底稿 / 生成结果对比"
      width="88%"
      class="compare-preview-dialog"
      @update:model-value="updateCompareVisible"
    >
      <div class="compare-preview-grid">
        <div>
          <label>底稿</label>
          <el-image :src="comparePreview.draftUrl" fit="contain" class="compare-preview-image"></el-image>
        </div>
        <div>
          <label>生成结果</label>
          <el-image :src="comparePreview.resultUrl" fit="contain" class="compare-preview-image"></el-image>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script>
export default {
  name: "ImageDialogs",
  props: {
    imagePreview: {
      type: Object,
      required: true,
    },
    comparePreview: {
      type: Object,
      required: true,
    },
  },
  emits: ["update:imagePreview", "update:comparePreview"],
  methods: {
    // Sync image dialog visibility.
    updateImageVisible(visible) {
      this.$emit("update:imagePreview", { ...this.imagePreview, visible });
    },
    // Sync compare dialog visibility.
    updateCompareVisible(visible) {
      this.$emit("update:comparePreview", { ...this.comparePreview, visible });
    },
  },
};
</script>
