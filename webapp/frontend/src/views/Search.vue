<template>
  <el-tabs v-model="tab">
    <el-tab-pane label="搜索作品" name="work">
      <el-form :inline="true" label-width="80px">
        <el-form-item label="关键词"><el-input v-model="f.query" style="width:180px" /></el-form-item>
        <el-form-item label="数量"><el-input-number v-model="f.num" :min="1" :max="500" /></el-form-item>
        <el-form-item label="排序">
          <el-select v-model="f.sortType" style="width:120px">
            <el-option label="综合" value="0" /><el-option label="最多点赞" value="1" /><el-option label="最新发布" value="2" />
          </el-select>
        </el-form-item>
        <el-form-item label="发布时间">
          <el-select v-model="f.publishTime" style="width:120px">
            <el-option label="不限" value="0" /><el-option label="一天内" value="1" /><el-option label="一周内" value="7" /><el-option label="半年内" value="180" />
          </el-select>
        </el-form-item>
        <el-form-item label="时长">
          <el-select v-model="f.filterDuration" style="width:120px">
            <el-option label="不限" value="" /><el-option label="1分钟内" value="0-1" /><el-option label="1-5分钟" value="1-5" /><el-option label="5分钟以上" value="5-10000" />
          </el-select>
        </el-form-item>
        <el-form-item label="范围">
          <el-select v-model="f.searchRange" style="width:120px">
            <el-option label="不限" value="0" /><el-option label="最近看过" value="1" /><el-option label="还未看过" value="2" /><el-option label="关注的人" value="3" />
          </el-select>
        </el-form-item>
        <el-form-item label="内容">
          <el-select v-model="f.contentType" style="width:100px">
            <el-option label="不限" value="0" /><el-option label="视频" value="1" /><el-option label="图文" value="2" />
          </el-select>
        </el-form-item>
        <el-form-item label="保存">
          <el-select v-model="f.saveChoice" style="width:120px">
            <el-option label="不保存" value="" /><el-option label="全部" value="all" /><el-option label="仅媒体" value="media" /><el-option label="仅Excel" value="excel" />
          </el-select>
        </el-form-item>
        <el-form-item><el-button type="primary" @click="searchWork">搜索</el-button></el-form-item>
      </el-form>
      <TaskHint :task-id="taskId" />
      <div v-if="works.length" style="margin-top:12px">
        <WorkTable :works="works" />
      </div>
    </el-tab-pane>

    <el-tab-pane label="搜索用户" name="user">
      <el-input v-model="f.query" placeholder="关键词" style="width:200px" />
      <el-input-number v-model="f.num" :min="1" :max="200" style="margin:0 8px" />
      <el-button type="primary" @click="searchUser" :loading="loading">搜索</el-button>
      <ResultBox :data="result" />
    </el-tab-pane>

    <el-tab-pane label="搜索直播" name="live">
      <el-input v-model="f.query" placeholder="关键词" style="width:200px" />
      <el-input-number v-model="f.num" :min="1" :max="200" style="margin:0 8px" />
      <el-button type="primary" @click="searchLive" :loading="loading">搜索</el-button>
      <ResultBox :data="result" />
    </el-tab-pane>
  </el-tabs>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { searchApi } from '@/api'
import { useTaskStore } from '@/stores/tasks'
import WorkTable from '@/components/WorkTable.vue'
import ResultBox from '@/components/ResultBox.vue'
import TaskHint from '@/components/TaskHint.vue'

const tab = ref('work')
const loading = ref(false)
const result = ref<any>(null)
const taskId = ref('')
const works = ref<any[]>([])
const taskStore = useTaskStore()
const f = reactive({
  query: '', num: 20, sortType: '0', publishTime: '0',
  filterDuration: '', searchRange: '0', contentType: '0', saveChoice: '',
})

async function searchWork() {
  if (!f.query.trim()) { ElMessage.warning('请输入关键词'); return }
  works.value = []
  taskId.value = ''
  try {
    const r = await searchApi.work({
      query: f.query, num: f.num, sort_type: f.sortType, publish_time: f.publishTime,
      filter_duration: f.filterDuration, search_range: f.searchRange,
      content_type: f.contentType, save_choice: f.saveChoice,
    })
    taskId.value = r.task_id
    ElMessage.success('已提交搜索任务')
  } catch (e: any) { ElMessage.error(e.message) }
}

// 任务完成时把结果填到 works
watch(() => taskStore.get(taskId.value)?.status, (st) => {
  if (st === 'done') {
    const t = taskStore.get(taskId.value)
    works.value = Array.isArray(t?.result) ? t.result : []
  }
})

async function searchUser() {
  loading.value = true; result.value = null
  try { result.value = await searchApi.user(f.query, f.num) } catch (e: any) { ElMessage.error(e.message) } finally { loading.value = false }
}
async function searchLive() {
  loading.value = true; result.value = null
  try { result.value = await searchApi.live(f.query, f.num) } catch (e: any) { ElMessage.error(e.message) } finally { loading.value = false }
}
</script>
