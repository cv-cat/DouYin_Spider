<template>
  <div>
    <el-form :inline="true">
      <el-form-item label="接收">
        <el-button :type="recvRunning ? 'danger' : 'primary'" @click="toggleRecv">{{ recvRunning ? '停止接收' : '开始接收' }}</el-button>
        <el-tag :type="recvRunning ? 'success' : 'info'" size="small" style="margin-left:8px">{{ recvRunning ? '接收中' : '未接收' }}</el-tag>
      </el-form-item>
    </el-form>

    <el-row :gutter="16" style="margin-top:12px">
      <el-col :span="14">
        <el-card shadow="never">
          <template #header><div style="display:flex;justify-content:space-between"><span>入站消息</span><el-button size="small" @click="events = []">清屏</el-button></div></template>
          <div class="event-stream" style="height:520px;overflow:auto">
            <div v-for="(e, i) in events" :key="i">
              <span class="muted">[{{ e.type }}]</span> {{ format(e) }}
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="never">
          <template #header><span>发送私信</span></template>
          <el-form label-width="100px">
            <el-form-item label="对方 UID">
              <el-input v-model="sendForm.toUserId" placeholder="可选" />
            </el-form-item>
            <el-form-item label="对方主页">
              <el-input v-model="sendForm.userUrl" placeholder="或粘贴用户主页链接" />
            </el-form-item>
            <el-form-item label="内容">
              <el-input v-model="sendForm.content" type="textarea" :rows="4" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="send" :loading="sending">发送</el-button>
            </el-form-item>
          </el-form>
          <ResultBox :data="sendResult" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { msgApi } from '@/api'
import ResultBox from '@/components/ResultBox.vue'

const recvRunning = ref(false)
const events = ref<any[]>([])
const sending = ref(false)
const sendResult = ref<any>(null)
const sendForm = reactive({ toUserId: '', userUrl: '', content: '' })
let ws: WebSocket | null = null

async function refreshStatus() {
  try { recvRunning.value = (await msgApi.recvStatus()).running } catch (e: any) { /* ignore */ }
}

async function toggleRecv() {
  try {
    if (recvRunning.value) {
      await msgApi.recvStop()
      recvRunning.value = false
      if (ws) { ws.close(); ws = null }
    } else {
      await msgApi.recvStart()
      recvRunning.value = true
      connectWs()
    }
  } catch (e: any) { ElMessage.error(e.message) }
}

function connectWs() {
  if (ws) ws.close()
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/api/messages/ws`)
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.type === 'msg.status' && msg.data?.state === 'open') recvRunning.value = true
      events.value.push(msg)
      if (events.value.length > 1000) events.value.splice(0, 500)
    } catch (e) { /* ignore */ }
  }
  ws.onclose = () => { /* keep recvRunning as-is; backend may still be running */ }
}

async function send() {
  if (!sendForm.content.trim()) { ElMessage.warning('请输入内容'); return }
  if (!sendForm.toUserId && !sendForm.userUrl) { ElMessage.warning('请填 UID 或主页链接'); return }
  sending.value = true
  sendResult.value = null
  try {
    const body: any = { content: sendForm.content }
    if (sendForm.toUserId) body.to_user_id = Number(sendForm.toUserId)
    if (sendForm.userUrl) body.user_url = sendForm.userUrl
    sendResult.value = await msgApi.send(body)
    if (sendResult.value.success) ElMessage.success('发送成功')
    else ElMessage.error('发送失败')
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    sending.value = false
  }
}

function format(e: any) {
  const d = e.data || {}
  switch (e.type) {
    case 'msg.text': return `【#${d.index}】${d.sender}: ${d.text}`
    case 'msg.emoji': return `【#${d.index}】${d.sender} 表情包: ${d.url}`
    case 'msg.voice': return `【#${d.index}】${d.sender} 语音: ${d.url}`
    case 'msg.image': return `【#${d.index}】${d.sender} 图片: ${d.url}`
    case 'msg.video': return `【#${d.index}】${d.sender} 分享视频: ${d.item_id}`
    case 'msg.read': return `对方已读 #${d.read_index}`
    case 'msg.status': return `状态: ${d.state} ${d.detail || ''}`
    default: return JSON.stringify(d)
  }
}

onMounted(refreshStatus)
onUnmounted(() => { if (ws) ws.close() })
</script>
