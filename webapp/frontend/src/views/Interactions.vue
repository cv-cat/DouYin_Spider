<template>
  <el-tabs v-model="tab">
    <el-tab-pane label="点赞视频" name="digg">
      <el-form label-width="120px" style="max-width:560px">
        <el-form-item label="作品 ID"><el-input v-model="f.awemeId" /></el-form-item>
        <el-form-item label="操作">
          <el-radio-group v-model="f.diggType">
            <el-radio value="1">点赞</el-radio><el-radio value="0">取消</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item><el-button type="primary" @click="digg" :loading="loading">执行</el-button></el-form-item>
      </el-form>
      <ResultBox :data="result" />
    </el-tab-pane>

    <el-tab-pane label="发表评论" name="comment">
      <el-form label-width="120px" style="max-width:560px">
        <el-form-item label="作品 ID"><el-input v-model="f.awemeId" /></el-form-item>
        <el-form-item label="评论内容"><el-input v-model="f.content" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="回复评论 ID"><el-input v-model="f.replyId" placeholder="留空为顶级评论" /></el-form-item>
        <el-form-item><el-button type="primary" @click="comment" :loading="loading">发表</el-button></el-form-item>
      </el-form>
      <ResultBox :data="result" />
    </el-tab-pane>

    <el-tab-pane label="收藏" name="collect">
      <el-form label-width="120px" style="max-width:560px">
        <el-form-item label="作品 ID"><el-input v-model="f.awemeId" /></el-form-item>
        <el-form-item label="操作">
          <el-radio-group v-model="f.collectAction">
            <el-radio value="1">收藏</el-radio><el-radio value="0">取消</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item><el-button type="primary" @click="collect" :loading="loading">执行</el-button></el-form-item>
        <el-divider>移动收藏</el-divider>
        <el-form-item label="收藏夹名"><el-input v-model="f.collectName" /></el-form-item>
        <el-form-item label="收藏夹 ID"><el-input v-model="f.collectId" /></el-form-item>
        <el-form-item>
          <el-button @click="collectMove" :loading="loading">移动到收藏夹</el-button>
          <el-button @click="collectRemove" :loading="loading">从收藏夹移除</el-button>
        </el-form-item>
      </el-form>
      <ResultBox :data="result" />
    </el-tab-pane>
  </el-tabs>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { interactApi } from '@/api'
import ResultBox from '@/components/ResultBox.vue'

const tab = ref('digg')
const loading = ref(false)
const result = ref<any>(null)
const f = reactive({ awemeId: '', diggType: '1', content: '', replyId: '', collectAction: '1', collectName: '', collectId: '' })

async function run(fn: () => Promise<any>) {
  loading.value = true; result.value = null
  try { result.value = await fn(); ElMessage.success('完成') } catch (e: any) { ElMessage.error(e.message) } finally { loading.value = false }
}
const digg = () => run(() => interactApi.digg(f.awemeId, f.diggType))
const comment = () => run(() => interactApi.comment(f.awemeId, f.content, f.replyId))
const collect = () => run(() => interactApi.collect(f.awemeId, f.collectAction))
const collectMove = () => run(() => interactApi.collectMove(f.awemeId, f.collectName, f.collectId))
const collectRemove = () => run(() => interactApi.collectRemove(f.awemeId, f.collectName, f.collectId))
</script>
