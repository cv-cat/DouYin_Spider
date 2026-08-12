<template>
  <div v-if="taskId" style="margin-top:12px">
    <el-alert type="success" :closable="false">
      已提交任务 <el-link type="primary" @click="go">查看进度 →</el-link>
      <span style="margin-left:12px">ID: {{ taskId }}</span>
      <span v-if="task" style="margin-left:12px">{{ task.status }} · {{ Math.round(task.progress * 100) }}%</span>
    </el-alert>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useTaskStore } from '@/stores/tasks'

const props = defineProps<{ taskId: string }>()
const router = useRouter()
const taskStore = useTaskStore()
const task = computed(() => taskStore.get(props.taskId))

watch(() => props.taskId, () => taskStore.refresh(), { immediate: false })

function go() { router.push('/tasks') }
</script>
