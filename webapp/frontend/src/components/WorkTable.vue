<template>
  <el-table :data="works" border max-height="600">
    <el-table-column label="类型" width="70">
      <template #default="{ row }"><el-tag size="small">{{ row.work_type }}</el-tag></template>
    </el-table-column>
    <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
    <el-table-column prop="nickname" label="作者" width="140" show-overflow-tooltip />
    <el-table-column prop="digg_count" label="点赞" width="80" />
    <el-table-column prop="comment_count" label="评论" width="80" />
    <el-table-column prop="collect_count" label="收藏" width="80" />
    <el-table-column prop="share_count" label="分享" width="80" />
    <el-table-column label="操作" width="220" fixed="right">
      <template #default="{ row }">
        <el-button size="small" @click="digg(row)">点赞</el-button>
        <el-button size="small" @click="openComment(row)">评论</el-button>
        <el-button size="small" @click="collect(row)">收藏</el-button>
        <el-link :href="row.work_url" target="_blank" type="primary" style="margin-left:8px">打开</el-link>
      </template>
    </el-table-column>
  </el-table>

  <el-dialog v-model="commentDlg" title="发表评论" width="460px">
    <el-input v-model="commentText" type="textarea" :rows="4" placeholder="评论内容" />
    <template #footer>
      <el-button @click="commentDlg = false">取消</el-button>
      <el-button type="primary" @click="sendComment">发送</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { interactApi } from '@/api'

defineProps<{ works: any[] }>()

const commentDlg = ref(false)
const commentText = ref('')
const commentTarget = ref('')

function digg(row: any) {
  interactApi.digg(row.work_id).then(() => ElMessage.success('已点赞')).catch((e) => ElMessage.error(e.message))
}
function openComment(row: any) {
  commentTarget.value = row.work_id
  commentText.value = ''
  commentDlg.value = true
}
function sendComment() {
  if (!commentText.value.trim()) return
  interactApi.comment(commentTarget.value, commentText.value).then(() => {
    ElMessage.success('评论已发送')
    commentDlg.value = false
  }).catch((e) => ElMessage.error(e.message))
}
function collect(row: any) {
  interactApi.collect(row.work_id).then(() => ElMessage.success('已收藏')).catch((e) => ElMessage.error(e.message))
}
</script>
