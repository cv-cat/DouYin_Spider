<template>
  <div>
    <div class="page-toolbar">
      <span class="page-desc">对已下载的用户视频进行逐帧分析，生成可视化报告</span>
    </div>

    <!-- 用户目录选择 -->
    <el-card class="mb-4">
      <template #header><span> 选择用户</span></template>
      <div class="user-grid">
        <div
          v-for="u in users" :key="u.name"
          class="user-card"
          :class="{ selected: selectedUser === u.name }"
          @click="selectedUser = u.name"
        >
          <div class="user-avatar">{{ u.name.charAt(0) }}</div>
          <div class="user-name">{{ u.name.split('_')[0] }}</div>
          <div class="user-count">{{ u.video_count }} 视频</div>
        </div>
        <div v-if="users.length === 0" class="muted" style="padding:20px">暂无已下载的用户数据，请先在「采集」页爬取视频</div>
      </div>
    </el-card>

    <!-- 分析参数 -->
    <el-card class="mb-4" v-if="selectedUser">
      <template #header><span> 分析配置</span></template>
      <div class="config-row">
        <div class="config-item">
          <span class="muted">每视频最多帧数</span>
          <el-input-number v-model="maxFrames" :min="5" :max="100" :step="5" size="small" />
        </div>
        <el-button type="primary" :loading="running" @click="startAnalysis" :disabled="!selectedUser">
          {{ running ? '分析中...' : '开始分析' }}
        </el-button>
      </div>
      <!-- 进度 -->
      <div v-if="running" class="mt-3">
        <el-progress :percentage="Math.round(progress * 100)" :stroke-width="8" :color="'#fe2c55'" />
        <div class="muted mt-2" style="font-size:12px">{{ statusText }}</div>
      </div>
    </el-card>

    <!-- 报告列表 -->
    <el-card>
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span> 分析报告</span>
          <el-button size="small" @click="loadReports" :loading="loadingReports">刷新</el-button>
        </div>
      </template>
      <el-table :data="reports" v-loading="loadingReports" border empty-text="暂无报告">
        <el-table-column prop="filename" label="文件名" min-width="240" />
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ (row.size / 1024 / 1024).toFixed(1) }} MB</template>
        </el-table-column>
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ new Date(row.modified * 1000).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="操作" width="240">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="previewReport(row.filename)">预览</el-button>
            <el-button size="small" @click="downloadReport(row.filename)">下载</el-button>
            <el-button size="small" type="danger" @click="deleteReport(row.filename)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 报告预览弹窗 -->
    <el-dialog v-model="previewDlg" title="报告预览" width="90%" top="3vh" destroy-on-close>
      <div class="preview-frame">
        <iframe v-if="previewUrl" :src="previewUrl" class="report-iframe" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { analysisApi } from '@/api'

const users = ref<any[]>([])
const reports = ref<any[]>([])
const selectedUser = ref('')
const maxFrames = ref(20)
const running = ref(false)
const progress = ref(0)
const statusText = ref('')
const loadingReports = ref(false)
const previewDlg = ref(false)
const previewUrl = ref('')
let pollTimer: number | null = null

async function loadUsers() {
  try { users.value = await analysisApi.users() } catch (e: any) { ElMessage.error(e.message) }
}

async function loadReports() {
  loadingReports.value = true
  try { reports.value = await analysisApi.reports() } catch (e: any) { ElMessage.error(e.message) }
  finally { loadingReports.value = false }
}

async function startAnalysis() {
  if (!selectedUser.value) return
  running.value = true
  progress.value = 0
  statusText.value = '正在分析...'
  try {
    const { job_id } = await analysisApi.run(selectedUser.value, maxFrames.value)
    pollTimer = window.setInterval(async () => {
      try {
        const job = await analysisApi.status(job_id)
        progress.value = job.progress
        if (job.status === 'done') {
          clearInterval(pollTimer!)
          running.value = false
          statusText.value = `完成! ${job.result.video_count} 个视频, ${job.result.total_likes.toLocaleString()} 赞`
          ElMessage.success('分析完成')
          loadReports()
        } else if (job.status === 'failed') {
          clearInterval(pollTimer!)
          running.value = false
          statusText.value = job.error || '分析失败'
          ElMessage.error('分析失败: ' + (job.error || '未知错误'))
        } else {
          statusText.value = '分析中...'
        }
      } catch (e: any) { /* ignore */ }
    }, 2000)
  } catch (e: any) {
    running.value = false
    ElMessage.error(e.message)
  }
}

function previewReport(filename: string) {
  previewUrl.value = analysisApi.reportUrl(filename)
  previewDlg.value = true
}

function downloadReport(filename: string) {
  window.open(analysisApi.reportDownloadUrl(filename), '_blank')
}

function deleteReport(filename: string) {
  ElMessage.info('报告文件在服务器 datas/analysis_reports/ 目录，可手动删除')
}

onMounted(() => {
  loadUsers()
  loadReports()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.mb-4 { margin-bottom: 16px; }
.mt-2 { margin-top: 8px; }
.mt-3 { margin-top: 12px; }
.user-grid { display: flex; gap: 12px; flex-wrap: wrap; }
.user-card {
  width: 100px; padding: 14px 10px; border-radius: 12px;
  background: var(--dy-surface-2); border: 1px solid var(--dy-border);
  text-align: center; cursor: pointer; transition: all 0.2s;
}
.user-card:hover { border-color: var(--dy-pink); }
.user-card.selected { border-color: var(--dy-pink); background: rgba(254,44,85,0.1); }
.user-avatar {
  width: 40px; height: 40px; border-radius: 50%;
  background: var(--dy-grad); margin: 0 auto 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; font-weight: 700; color: #fff;
}
.user-name { font-size: 13px; font-weight: 600; color: var(--dy-text); }
.user-count { font-size: 11px; color: var(--dy-muted); margin-top: 4px; }
.config-row { display: flex; align-items: center; gap: 16px; }
.config-item { display: flex; align-items: center; gap: 8px; }
.preview-frame { height: 80vh; overflow: hidden; border-radius: 8px; border: 1px solid var(--dy-border); }
.report-iframe { width: 100%; height: 100%; border: none; }
</style>