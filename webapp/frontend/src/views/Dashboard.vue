<template>
  <div class="dashboard">
    <div class="welcome">
      <h2>抖音 Spider 控制台</h2>
      <p class="muted">专业的抖音数据采集、分析与自动化工具</p>
    </div>

    <!-- 状态卡片 -->
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-icon" style="background:rgba(254,44,85,0.15)">&#x1F464;</div>
        <div class="stat-body">
          <div class="stat-value">{{ accountStore.accounts.length }}</div>
          <div class="stat-label">账号总数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" :style="accountStore.active ? 'background:rgba(37,244,238,0.15)' : 'background:rgba(110,110,133,0.15)'">&#x1F7E2;</div>
        <div class="stat-body">
          <div class="stat-value">{{ accountStore.active ? accountStore.active.label : '未登录' }}</div>
          <div class="stat-label">活跃账号</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background:rgba(90,184,255,0.15)">&#x1F4CB;</div>
        <div class="stat-body">
          <div class="stat-value">{{ taskCount }}</div>
          <div class="stat-label">任务总数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background:rgba(95,227,160,0.15)">&#x1F4C1;</div>
        <div class="stat-body">
          <div class="stat-value">{{ userCount }}</div>
          <div class="stat-label">已下载用户</div>
        </div>
      </div>
    </div>

    <!-- 快捷入口 -->
    <h3 style="margin:24px 0 12px">快捷入口</h3>
    <div class="quick-grid">
      <div class="quick-card" @click="$router.push('/accounts')">
        <div class="quick-icon">&#x1F510;</div>
        <div class="quick-title">账号管理</div>
        <div class="quick-desc">登录、切换、校验抖音账号</div>
      </div>
      <div class="quick-card" @click="$router.push('/crawl')">
        <div class="quick-icon">&#x2B07;</div>
        <div class="quick-title">数据采集</div>
        <div class="quick-desc">爬取用户作品、评论、粉丝</div>
      </div>
      <div class="quick-card" @click="$router.push('/analysis')">
        <div class="quick-icon">&#x1F4CA;</div>
        <div class="quick-title">视频分析</div>
        <div class="quick-desc">逐帧分析、节奏检测、生成报告</div>
      </div>
      <div class="quick-card" @click="$router.push('/tasks')">
        <div class="quick-icon">&#x2699;</div>
        <div class="quick-title">任务管理</div>
        <div class="quick-desc">查看任务进度与结果</div>
      </div>
      <div class="quick-card" @click="$router.push('/downloads')">
        <div class="quick-icon">&#x1F4E5;</div>
        <div class="quick-title">下载管理</div>
        <div class="quick-desc">浏览和下载采集产物</div>
      </div>
      <div class="quick-card" @click="$router.push('/live')">
        <div class="quick-icon">&#x1F3A4;</div>
        <div class="quick-title">直播间</div>
        <div class="quick-desc">监听弹幕、礼物、互动</div>
      </div>
    </div>

    <!-- 最近任务 -->
    <h3 style="margin:24px 0 12px">最近任务</h3>
    <el-table :data="recentTasks" border empty-text="暂无任务" size="small">
      <el-table-column prop="id" label="ID" width="120" />
      <el-table-column prop="kind" label="类型" width="120" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'done' ? 'success' : row.status === 'failed' ? 'danger' : row.status === 'running' ? 'warning' : 'info'" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="进度" min-width="150">
        <template #default="{ row }">
          <el-progress :percentage="Math.round(row.progress * 100)" :stroke-width="6" :color="row.status === 'failed' ? '#ff6b8b' : '#fe2c55'" />
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180" />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAccountStore } from '@/stores/account'
import { useTaskStore } from '@/stores/tasks'
import { analysisApi } from '@/api'

const accountStore = useAccountStore()
const taskStore = useTaskStore()
const taskCount = ref(0)
const userCount = ref(0)
const recentTasks = ref<any[]>([])

onMounted(async () => {
  accountStore.refresh()
  taskStore.refresh()
  taskCount.value = taskStore.tasks.length
  recentTasks.value = taskStore.tasks.slice(0, 5)
  try {
    const users = await analysisApi.users()
    userCount.value = users.length
  } catch (e) { /* ignore */ }
})
</script>

<style scoped>
.dashboard { max-width: 1000px; }
.welcome h2 { font-size: 22px; margin-bottom: 6px; color: #fff; }
.welcome p { font-size: 14px; }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-top: 20px; }
.stat-card {
  background: var(--dy-surface); border: 1px solid var(--dy-border); border-radius: 14px;
  padding: 18px; display: flex; align-items: center; gap: 14px;
}
.stat-icon { width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 20px; }
.stat-value { font-size: 22px; font-weight: 700; color: #fff; }
.stat-label { font-size: 12px; color: var(--dy-muted); margin-top: 2px; }
.quick-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; }
.quick-card {
  background: var(--dy-surface); border: 1px solid var(--dy-border); border-radius: 14px;
  padding: 20px 16px; cursor: pointer; transition: all 0.2s;
}
.quick-card:hover { border-color: var(--dy-pink); transform: translateY(-2px); box-shadow: 0 8px 24px rgba(254,44,85,0.1); }
.quick-icon { font-size: 28px; margin-bottom: 8px; }
.quick-title { font-size: 14px; font-weight: 600; color: var(--dy-text); }
.quick-desc { font-size: 11px; color: var(--dy-muted); margin-top: 4px; }
</style>