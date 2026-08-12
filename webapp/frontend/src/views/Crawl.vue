<template>
  <el-tabs v-model="tab">
    <!-- 单作品 -->
    <el-tab-pane label="作品信息" name="work">
      <el-input v-model="f.workUrl" placeholder="作品链接 https://www.douyin.com/video/..." style="width:560px" />
      <el-button type="primary" @click="run('work')" :loading="loading">查询</el-button>
      <ResultBox :data="result" />
    </el-tab-pane>

    <!-- 用户全部作品 -->
    <el-tab-pane label="用户作品" name="userWorks">
      <el-input v-model="f.userUrl" placeholder="用户主页链接" style="width:560px" />
      <el-select v-model="f.saveChoice" style="width:140px;margin:0 8px">
        <el-option label="全部(all)" value="all" />
        <el-option label="仅媒体" value="media" />
        <el-option label="仅视频" value="media-video" />
        <el-option label="仅图片" value="media-image" />
        <el-option label="仅Excel" value="excel" />
      </el-select>
      <el-button type="primary" @click="run('userWorks')">提交任务</el-button>
      <TaskHint :task-id="taskId" />
    </el-tab-pane>

    <!-- 用户信息 -->
    <el-tab-pane label="用户信息" name="userInfo">
      <el-input v-model="f.userUrl" placeholder="用户主页链接" style="width:560px" />
      <el-button type="primary" @click="run('userInfo')" :loading="loading">查询</el-button>
      <ResultBox :data="result" />
    </el-tab-pane>

    <!-- 评论 -->
    <el-tab-pane label="评论" name="comments">
      <el-input v-model="f.workUrl" placeholder="作品链接" style="width:560px" />
      <el-button type="primary" @click="run('comments')">提交任务</el-button>
      <TaskHint :task-id="taskId" />
    </el-tab-pane>

    <!-- 关注/粉丝 -->
    <el-tab-pane label="关注/粉丝" name="follow">
      <el-input v-model="f.userId" placeholder="user_id" style="width:200px" />
      <el-input v-model="f.secId" placeholder="sec_id" style="width:260px;margin:0 8px" />
      <el-input-number v-model="f.num" :min="1" :max="500" style="width:120px" />
      <el-button type="primary" @click="run('followers')" style="margin-left:8px">粉丝</el-button>
      <el-button @click="run('following')">关注</el-button>
      <TaskHint :task-id="taskId" />
    </el-tab-pane>

    <!-- 收藏 -->
    <el-tab-pane label="用户收藏" name="favorites">
      <el-input v-model="f.secId" placeholder="sec_id" style="width:400px" />
      <el-button type="primary" @click="run('favorites')" :loading="loading">查询</el-button>
      <ResultBox :data="result" />
    </el-tab-pane>

    <!-- 通知 -->
    <el-tab-pane label="消息通知" name="notices">
      <el-input-number v-model="f.num" :min="1" :max="200" />
      <el-button type="primary" @click="run('notices')" :loading="loading">查询</el-button>
      <ResultBox :data="result" />
    </el-tab-pane>

    <!-- 推荐流 -->
    <el-tab-pane label="推荐流" name="feed">
      <el-input v-model="f.count" placeholder="count" style="width:120px" />
      <el-button type="primary" @click="run('feed')" :loading="loading">查询</el-button>
      <ResultBox :data="result" />
    </el-tab-pane>

    <!-- 收藏列表 -->
    <el-tab-pane label="我的收藏夹" name="collectList">
      <el-button type="primary" @click="run('collectList')" :loading="loading">查询</el-button>
      <ResultBox :data="result" />
    </el-tab-pane>

    <!-- 榜单 -->
    <el-tab-pane label="直播间榜单" name="rank">
      <el-input v-model="f.roomId" placeholder="room_id" style="width:200px" />
      <el-input v-model="f.anchorId" placeholder="anchor_id" style="width:200px;margin:0 8px" />
      <el-input v-model="f.secAnchorId" placeholder="sec_anchor_id" style="width:280px" />
      <el-button type="primary" @click="run('rank')" :loading="loading" style="margin-left:8px">查询</el-button>
      <ResultBox :data="result" />
    </el-tab-pane>
  </el-tabs>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { crawlApi } from '@/api'
import ResultBox from '@/components/ResultBox.vue'
import TaskHint from '@/components/TaskHint.vue'

const tab = ref('work')
const loading = ref(false)
const result = ref<any>(null)
const taskId = ref('')
const f = reactive({
  workUrl: '', userUrl: '', saveChoice: 'all', userId: '', secId: '',
  num: 20, count: '20', roomId: '', anchorId: '', secAnchorId: '',
})

async function run(kind: string) {
  loading.value = true
  result.value = null
  taskId.value = ''
  try {
    let r: any
    switch (kind) {
      case 'work': r = await crawlApi.work(f.workUrl); result.value = r; break
      case 'userWorks': r = await crawlApi.userWorks({ user_url: f.userUrl, save_choice: f.saveChoice }); taskId.value = r.task_id; break
      case 'userInfo': r = await crawlApi.userInfo(f.userUrl); result.value = r; break
      case 'comments': r = await crawlApi.comments(f.workUrl); taskId.value = r.task_id; break
      case 'followers': r = await crawlApi.followers(f.userId, f.secId, f.num); taskId.value = r.task_id; break
      case 'following': r = await crawlApi.following(f.userId, f.secId, f.num); taskId.value = r.task_id; break
      case 'favorites': r = await crawlApi.favorites(f.secId); result.value = r; break
      case 'notices': r = await crawlApi.notices(f.num); result.value = r; break
      case 'feed': r = await crawlApi.feed(f.count); result.value = r; break
      case 'collectList': r = await crawlApi.collectList(); result.value = r; break
      case 'rank': r = await crawlApi.rank(f.roomId, f.anchorId, f.secAnchorId); result.value = r; break
    }
    if (taskId.value) ElMessage.success('已提交任务,在「任务」页查看进度')
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}
</script>
