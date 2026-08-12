<template>
  <div>
    <el-form :inline="true">
      <el-form-item label="直播间号">
        <el-input v-model="roomId" placeholder="如 432433667143" style="width:220px" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="start" :loading="starting">开始监听</el-button>
        <el-button @click="stop">停止</el-button>
        <el-tag :type="connected ? 'success' : 'info'" size="small" style="margin-left:8px">{{ connected ? '已连接' : '未连接' }}</el-tag>
      </el-form-item>
    </el-form>

    <el-card style="margin-top:12px" shadow="never">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span>实时事件</span>
          <div>
            <el-input v-model="danmaku" placeholder="发弹幕" style="width:240px" @keyup.enter="send" />
            <el-button size="small" @click="send" style="margin-left:4px">发送</el-button>
            <el-button size="small" @click="like">点赞</el-button>
            <el-button size="small" @click="events = []">清屏</el-button>
          </div>
        </div>
      </template>
      <div class="event-stream" style="height:520px;overflow:auto">
        <div v-for="(e, i) in events" :key="i" :class="lineClass(e.type)">
          [{{ e.type }}] {{ format(e) }}
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { liveApi } from '@/api'

const roomId = ref('')
const starting = ref(false)
const connected = ref(false)
const events = ref<any[]>([])
const danmaku = ref('')
let ws: WebSocket | null = null

async function start() {
  if (!roomId.value.trim()) { ElMessage.warning('请输入直播间号'); return }
  starting.value = true
  try {
    await liveApi.start(roomId.value)
    connectWs()
    ElMessage.success('已开始监听')
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    starting.value = false
  }
}

function connectWs() {
  if (ws) ws.close()
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/api/live/ws/${roomId.value}`)
  ws.onopen = () => { connected.value = true }
  ws.onclose = () => { connected.value = false }
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      events.value.push(msg)
      if (events.value.length > 1000) events.value.splice(0, 500)
    } catch (e) { /* ignore */ }
  }
}

async function stop() {
  if (ws) { ws.close(); ws = null }
  connected.value = false
  if (roomId.value) {
    try { await liveApi.stop(roomId.value) } catch (e: any) { ElMessage.error(e.message) }
  }
}

async function send() {
  if (!danmaku.value.trim()) return
  try { await liveApi.send(roomId.value, danmaku.value); danmaku.value = '' } catch (e: any) { ElMessage.error(e.message) }
}
async function like() {
  try { await liveApi.digg(roomId.value, '1') } catch (e: any) { ElMessage.error(e.message) }
}

function lineClass(type: string) {
  if (type.includes('gift')) return 'tag-gift'
  if (type.includes('chat')) return 'tag-chat'
  if (type.includes('like')) return 'tag-like'
  if (type.includes('member')) return 'tag-member'
  if (type.includes('social')) return 'tag-social'
  return ''
}

function format(e: any) {
  const d = e.data || {}
  switch (e.type) {
    case 'live.gift': return `${d.nickname} 送给 ${d.to_nickname} ${d.gift_name} x${d.combo_count}`
    case 'live.chat': return `${d.nickname}: ${d.content}`
    case 'live.member': return `${d.nickname} 进入直播间`
    case 'live.like': return `${d.nickname} 点赞 ${d.count} 次 (总 ${d.total})`
    case 'live.social': return `${d.nickname} ${d.action === 1 ? '关注主播' : '取消关注'}`
    case 'live.room_stats': return `房间: ${d.display_long}`
    case 'live.status': return `状态: ${d.state} ${d.detail || ''}`
    default: return JSON.stringify(d)
  }
}

onUnmounted(() => { if (ws) ws.close() })
</script>
