<template>
  <div>
    <div class="page-toolbar">
      <el-button type="primary" @click="openQr">扫码登录</el-button>
      <el-button @click="cookieDlg = true">Cookie 粘贴</el-button>
      <el-button @click="headedLogin">有头浏览器登录</el-button>
      <span class="spacer"></span>
      <el-button @click="accountStore.refresh()">刷新</el-button>
    </div>

    <el-table :data="accountStore.accounts" v-loading="accountStore.loading" border>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="label" label="标签" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'valid' ? 'success' : row.status === 'invalid' ? 'danger' : 'info'" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="私信凭证" width="100">
        <template #default="{ row }">
          <el-tag :type="row.has_pm_credential ? 'success' : 'info'" size="small">{{ row.has_pm_credential ? '有' : '无' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column label="操作" width="280">
        <template #default="{ row }">
          <el-button size="small" @click="accountStore.setActive(row.id)">设为活跃</el-button>
          <el-button size="small" @click="validate(row.id)">校验</el-button>
          <el-popconfirm title="确认删除?" @confirm="accountStore.remove(row.id)">
            <template #reference><el-button size="small" type="danger">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- QR 登录弹窗 -->
    <el-dialog v-model="qrDlg" title="扫码登录" width="420px" align-center @close="stopQrPoll">
      <div class="qr-box">
        <div class="qr-frame">
          <img v-if="qrImage" :src="qrImage" class="qr-img" />
          <div v-else class="qr-placeholder" v-loading="true"></div>
          <transition name="qr-fade">
            <div v-if="qrImage && qrStatus === 'scanned'" class="qr-overlay">
              <el-icon><CircleCheckFilled /></el-icon>
              <span>已扫码,请在手机上确认</span>
            </div>
          </transition>
        </div>
        <div class="qr-status">
          <span class="qr-dot" :class="'dot-' + qrStatusType"></span>
          <span>{{ qrStatusText }}</span>
        </div>
        <div class="muted qr-hint">打开抖音 App · 右上角扫一扫</div>
      </div>
    </el-dialog>

    <!-- Cookie 粘贴弹窗 -->
    <el-dialog v-model="cookieDlg" title="Cookie 粘贴登录" width="560px">
      <el-form label-width="120px">
        <el-form-item label="标签">
          <el-input v-model="cookieForm.label" />
        </el-form-item>
        <el-form-item label="Cookie">
          <el-input v-model="cookieForm.cookies" type="textarea" :rows="6" placeholder="粘贴浏览器 F12 复制的 cookie" />
        </el-form-item>
        <el-form-item label="提取私信凭证">
          <el-switch v-model="cookieForm.extract" /> <span class="muted">需安装 Playwright,headless 提取签名凭证</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cookieDlg = false">取消</el-button>
        <el-button type="primary" :loading="cookieLoading" @click="doCookieLogin">登录</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useAccountStore } from '@/stores/account'
import { accountsApi } from '@/api'

const accountStore = useAccountStore()

// QR
const qrDlg = ref(false)
const qrImage = ref('')
const qrTempId = ref('')
const qrStatus = ref('new')
let qrTimer: number | null = null
const qrStatusText = ref('等待扫码')
const qrStatusType = ref<'info' | 'success' | 'warning' | 'danger'>('info')

async function openQr() {
  qrImage.value = ''
  qrStatus.value = 'new'
  qrStatusText.value = '生成中…'
  qrDlg.value = true
  try {
    const r = await accountsApi.qrStart()
    qrTempId.value = r.temp_id
    qrImage.value = r.qr_image
    qrStatusText.value = '等待扫码'
    startQrPoll()
  } catch (e: any) {
    ElMessage.error('生成二维码失败:' + e.message)
    qrDlg.value = false
  }
}

function startQrPoll() {
  stopQrPoll()
  qrTimer = window.setInterval(async () => {
    try {
      const r = await accountsApi.qrPoll(qrTempId.value)
      qrStatus.value = r.status
      if (r.status === 'new') { qrStatusText.value = '等待扫码'; qrStatusType.value = 'info' }
      else if (r.status === 'scanned') { qrStatusText.value = '已扫码,请在手机确认'; qrStatusType.value = 'warning' }
      else if (r.status === 'confirmed') {
        qrStatusText.value = '登录成功'; qrStatusType.value = 'success'
        ElMessage.success('登录成功')
        stopQrPoll()
        qrDlg.value = false
        await accountStore.refresh()
        if (r.account_id) await accountStore.setActive(r.account_id)
      } else if (r.status === 'expired') {
        qrStatusText.value = '已过期,请重新生成'; qrStatusType.value = 'danger'
        stopQrPoll()
      } else if (r.status === 'error') {
        qrStatusText.value = r.detail || '错误'; qrStatusType.value = 'danger'
        stopQrPoll()
      }
    } catch (e: any) { /* ignore poll errors */ }
  }, 2000)
}

function stopQrPoll() {
  if (qrTimer) { clearInterval(qrTimer); qrTimer = null }
}

onUnmounted(stopQrPoll)

// Cookie
const cookieDlg = ref(false)
const cookieLoading = ref(false)
const cookieForm = ref({ label: '手动粘贴', cookies: '', extract: true })
async function doCookieLogin() {
  if (!cookieForm.value.cookies.trim()) { ElMessage.warning('请粘贴 cookie'); return }
  cookieLoading.value = true
  try {
    const r = await accountsApi.cookieLogin(cookieForm.value.cookies, cookieForm.value.label, cookieForm.value.extract)
    ElMessage.success('登录成功')
    cookieDlg.value = false
    await accountStore.refresh()
    if (r.account_id) await accountStore.setActive(r.account_id)
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    cookieLoading.value = false
  }
}

// 有头
async function headedLogin() {
  ElMessage.info('已在服务端打开浏览器,请在弹出的窗口扫码(180s)')
  try {
    const r = await accountsApi.headedLogin(180)
    ElMessage.success('登录成功')
    await accountStore.refresh()
    if (r.account_id) await accountStore.setActive(r.account_id)
  } catch (e: any) {
    ElMessage.error(e.message)
  }
}

async function validate(id: number) {
  try {
    const a = await accountStore.validate(id)
    ElMessage.success('校验完成:' + a.status)
  } catch (e: any) {
    ElMessage.error(e.message)
  }
}
</script>

<style scoped>
.qr-box { display: flex; flex-direction: column; align-items: center; padding: 6px 4px 4px; }

.qr-frame {
  position: relative;
  width: 248px; height: 248px;
  border-radius: 18px;
  padding: 10px;
  background: var(--dy-surface-2);
  border: 1px solid var(--dy-border);
  box-shadow: 0 0 0 1px rgba(254, 44, 85, 0.08), 0 12px 36px rgba(0, 0, 0, 0.45);
}
.qr-frame::before {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: 19px;
  padding: 1px;
  background: var(--dy-grad);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  opacity: 0.55;
  pointer-events: none;
}
.qr-img { width: 228px; height: 228px; border-radius: 10px; display: block; }
.qr-placeholder { width: 228px; height: 228px; border-radius: 10px; }

.qr-overlay {
  position: absolute;
  inset: 10px;
  border-radius: 10px;
  background: rgba(11, 11, 18, 0.82);
  backdrop-filter: blur(2px);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 10px;
  color: #fff;
  font-size: 13px;
}
.qr-overlay .el-icon { font-size: 40px; color: #25f4ee; }

.qr-status {
  margin-top: 18px;
  display: flex; align-items: center; gap: 8px;
  font-size: 14px; color: var(--dy-text);
}
.qr-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--dy-muted);
  box-shadow: 0 0 0 0 rgba(0,0,0,0);
}
.qr-dot.dot-info { background: #5ab8ff; animation: qr-pulse 1.6s infinite; }
.qr-dot.dot-success { background: #5fe3a0; }
.qr-dot.dot-warning { background: #ffb84d; animation: qr-pulse 1.2s infinite; }
.qr-dot.dot-danger { background: #ff6b8b; }
@keyframes qr-pulse {
  0% { box-shadow: 0 0 0 0 rgba(90, 184, 255, 0.5); }
  70% { box-shadow: 0 0 0 8px rgba(90, 184, 255, 0); }
  100% { box-shadow: 0 0 0 0 rgba(90, 184, 255, 0); }
}

.qr-hint { margin-top: 8px; font-size: 12.5px; }

.qr-fade-enter-active, .qr-fade-leave-active { transition: opacity 0.25s ease; }
.qr-fade-enter-from, .qr-fade-leave-to { opacity: 0; }
</style>
