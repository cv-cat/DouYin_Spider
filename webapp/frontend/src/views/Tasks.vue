<template>
  <div>
    <div style="margin-bottom:12px">
      <el-button @click="taskStore.refresh()">刷新</el-button>
    </div>
    <el-table :data="taskStore.tasks" border>
      <el-table-column prop="id" label="ID" width="130" />
      <el-table-column prop="kind" label="类型" width="160" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="进度" width="200">
        <template #default="{ row }">
          <el-progress :percentage="Math.round(row.progress * 100)" :status="row.status === 'failed' ? 'exception' : row.status === 'done' ? 'success' : undefined" />
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建" width="180" />
      <el-table-column prop="finished_at" label="完成" width="180" />
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button size="small" @click="view(row)">查看</el-button>
          <el-button size="small" @click="taskStore.cancel(row.id)" v-if="row.status === 'running' || row.status === 'pending'">取消</el-button>
          <el-button size="small" @click="taskStore.remove(row.id)" v-else>删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dlg" title="任务结果" width="700px">
      <ResultBox :data="current" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useTaskStore } from '@/stores/tasks'
import ResultBox from '@/components/ResultBox.vue'

const taskStore = useTaskStore()
const dlg = ref(false)
const current = ref<any>(null)

function statusType(s: string) {
  return s === 'done' ? 'success' : s === 'failed' ? 'danger' : s === 'cancelled' ? 'info' : 'warning'
}
function view(row: any) {
  current.value = row
  dlg.value = true
}
</script>
