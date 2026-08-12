<template>
  <div>
    <div class="page-toolbar">
      <el-button @click="reload" :loading="loading">刷新</el-button>
      <span class="muted hint">点击文件夹展开 · 「下载文件夹」打包整个目录为 zip</span>
    </div>
    <el-card shadow="never">
      <template #header><span>采集产物(datas/)</span></template>
      <el-tree
        :key="treeKey"
        lazy
        :load="load"
        :props="treeProps"
        node-key="path"
      >
        <template #default="{ data: node }">
          <span class="tree-row">
            <el-icon v-if="node.is_dir" class="ic-folder"><Folder /></el-icon>
            <el-icon v-else class="ic-file"><Document /></el-icon>
            <span class="tree-name">{{ node.name }}</span>
            <span v-if="!node.is_dir" class="muted tree-size">{{ formatSize(node.size) }}</span>
            <el-link
              v-if="node.is_dir"
              type="primary"
              :href="dirUrl(node.path)"
              target="_blank"
              class="tree-dl"
            >下载文件夹</el-link>
            <el-link
              v-else
              type="primary"
              :href="fileUrl(node.path)"
              target="_blank"
              :download="node.name"
              class="tree-dl"
            >下载</el-link>
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
const treeKey = ref(0)
const treeProps = {
  label: 'name',
  isLeaf: (data: any) => !data.is_dir || !data.has_children,
}

async function load(node: any, resolve: (data: any[]) => void) {
  const path = node.level === 0 ? undefined : node.data?.path
  try {
    const children = await downloadsApi.children(path)
    resolve(children)
  } catch {
    resolve([])
  }
}

function reload() {
  loading.value = true
  treeKey.value++
  setTimeout(() => (loading.value = false), 300)
}

function fileUrl(path: string) { return downloadsApi.fileUrl(path) }
function dirUrl(path: string) { return downloadsApi.dirUrl(path) }

function formatSize(n: number) {
  if (!n) return ''
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1024 / 1024).toFixed(1) + ' MB'
}

onMounted(() => {})
</script>

<style scoped>
.hint { font-size: 12.5px; }
.tree-row { display: inline-flex; align-items: center; gap: 4px; }
.ic-folder { color: #ffb84d; }
.ic-file { color: var(--dy-text-2); }
.tree-name { margin-left: 2px; }
.tree-size { font-size: 12px; margin-left: 8px; }
.tree-dl { margin-left: 12px; }
</style>
