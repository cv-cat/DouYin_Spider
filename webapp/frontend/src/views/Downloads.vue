<template>
  <div>
    <div style="margin-bottom:12px"><el-button @click="load" :loading="loading">刷新</el-button></div>
    <el-card shadow="never">
      <template #header><span>采集产物(datas/)</span></template>
      <el-tree :data="treeData" :props="treeProps" node-key="path" default-expand-all>
        <template #default="{ data: node }">
          <span>
            <el-icon v-if="node.is_dir"><Folder /></el-icon>
            <el-icon v-else><Document /></el-icon>
            <span style="margin-left:4px">{{ node.name }}</span>
            <span v-if="!node.is_dir" class="muted" style="margin-left:8px;font-size:12px">{{ formatSize(node.size) }}</span>
            <el-link v-if="!node.is_dir" type="primary" :href="fileUrl(node.path)" target="_blank" style="margin-left:12px" :download="node.name">下载</el-link>
          </span>
        </template>
      </el-tree>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { downloadsApi } from '@/api'

const loading = ref(false)
const treeData = ref<any[]>([])
const treeProps = { label: 'name', children: 'children' }

async function load() {
  loading.value = true
  try { treeData.value = [await downloadsApi.tree()] } catch (e) { /* ignore */ } finally { loading.value = false }
}
function fileUrl(path: string) { return downloadsApi.fileUrl(path) }
function formatSize(n: number) {
  if (!n) return ''
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1024 / 1024).toFixed(1) + ' MB'
}
onMounted(load)
</script>
