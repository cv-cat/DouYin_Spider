<template>
  <el-card v-if="data !== null" style="margin-top:16px" shadow="never">
    <template #header>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span>结果</span>
        <el-button size="small" @click="copy">复制 JSON</el-button>
      </div>
    </template>
    <pre style="max-height:500px;overflow:auto;margin:0">{{ text }}</pre>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{ data: any }>()
const text = computed(() => {
  try { return JSON.stringify(props.data, null, 2) } catch { return String(props.data) }
})
function copy() {
  navigator.clipboard.writeText(text.value).then(() => ElMessage.success('已复制')).catch(() => ElMessage.error('复制失败'))
}
</script>
