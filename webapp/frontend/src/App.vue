<template>
  <div class="layout">
    <el-aside class="sidebar" :class="{ collapsed: sidebarCollapsed }" @mouseenter="sidebarCollapsed = false" @mouseleave="sidebarCollapsed = true">
      <div class="logo">
        <div class="logo-mark">🎶</div>
        <div class="logo-text" v-show="!sidebarCollapsed">抖音 <span class="grad-text">Spider</span></div>
      </div>
      <el-menu :default-active="route.path" :router="true" :collapse="sidebarCollapsed">
        <el-menu-item index="/dashboard"><el-icon><DataBoard /></el-icon><span>仪表盘</span></el-menu-item>
        <el-menu-item index="/accounts"><el-icon><User /></el-icon><span>账号</span></el-menu-item>
        <el-menu-item index="/crawl"><el-icon><Download /></el-icon><span>采集</span></el-menu-item>
        <el-menu-item index="/search"><el-icon><Search /></el-icon><span>搜索</span></el-menu-item>
        <el-menu-item index="/analysis"><el-icon><TrendCharts /></el-icon><span>分析</span></el-menu-item>
        <el-menu-item index="/live"><el-icon><VideoCamera /></el-icon><span>直播间</span></el-menu-item>
        <el-menu-item index="/messages"><el-icon><ChatDotRound /></el-icon><span>私信</span></el-menu-item>
        <el-menu-item index="/interactions"><el-icon><Star /></el-icon><span>互动</span></el-menu-item>
        <el-menu-item index="/tasks"><el-icon><List /></el-icon><span>任务</span></el-menu-item>
        <el-menu-item index="/downloads"><el-icon><FolderOpened /></el-icon><span>下载</span></el-menu-item>
      </el-menu>
      <div class="sidebar-foot muted" v-show="!sidebarCollapsed">
        <div class="foot-row">v1.1 · 本地控制台</div>
        <div class="foot-row" style="font-size:11px">Powered by Douyin Spider</div>
      </div>
    </el-aside>
    <div class="main">
      <header class="topbar">
        <div class="topbar-gradient"></div>
        <div class="title">{{ route.meta.title || '抖音 Spider 控制台' }}</div>
        <div class="right">
          <template v-if="accountStore.active">
            <el-tag :type="accountStore.active.status === 'valid' ? 'success' : 'warning'" size="small" effect="dark">
              {{ accountStore.active.label }}
            </el-tag>
            <el-tag :type="accountStore.active.has_pm_credential ? 'success' : 'info'" size="small" effect="dark">
              {{ accountStore.active.has_pm_credential ? '私信可用' : '私信不可用' }}
            </el-tag>
          </template>
          <el-tag v-else type="danger" size="small" effect="dark">未登录</el-tag>
          <el-select
            v-if="accountStore.accounts.length"
            :model-value="accountStore.activeId"
            @change="accountStore.setActive"
            size="small"
            style="width:150px"
          >
            <el-option v-for="a in accountStore.accounts" :key="a.id" :label="a.label" :value="a.id" />
          </el-select>
        </div>
      </header>
      <div class="content">
        <router-view v-slot="{ Component }">
          <transition name="page-fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAccountStore } from '@/stores/account'
import { useTaskStore } from '@/stores/tasks'

const route = useRoute()
const accountStore = useAccountStore()
const taskStore = useTaskStore()
const sidebarCollapsed = ref(false)

onMounted(() => {
  accountStore.refresh()
  taskStore.refresh()
  taskStore.subscribe()
})
</script>
