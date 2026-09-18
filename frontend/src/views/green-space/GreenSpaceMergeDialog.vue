<template>
  <el-dialog
    :model-value="visible"
    title="合并绿地档案"
    width="840px"
    top="8vh"
    destroy-on-close
    @update:model-value="close"
  >
    <el-alert type="warning" show-icon :closable="false" class="merge-alert">
      <template #title>
        合并后，被合并方的全部养护任务、养护记录与绿植更换将转移至保留方，
        被合并方档案将被删除且不可恢复。请选择保留方。
      </template>
    </el-alert>

    <div class="merge-select">
      <span class="select-label">被合并的另一条档案（同行政区）：</span>
      <el-select
        v-model="selectedId"
        filterable
        remote
        clearable
        :remote-method="search"
        :loading="searching"
        placeholder="输入名称或编号搜索"
        style="width: 380px"
        @change="onSelect"
      >
        <el-option
          v-for="item in candidates"
          :key="item.id"
          :value="item.id"
          :label="`${item.code} ${item.name}`"
        />
      </el-select>
    </div>

    <div class="merge-compare">
      <div
        v-for="side in sides"
        :key="side.key"
        class="space-card"
        :class="{ active: keep === side.key && side.space, disabled: !side.space }"
        @click="side.space && (keep = side.key)"
      >
        <div class="keep-line">
          <el-radio v-model="keep" :value="side.key" :disabled="!side.space">保留该档案</el-radio>
        </div>
        <template v-if="side.space">
          <div class="space-title">{{ side.space.name }}</div>
          <div class="space-meta">编号 {{ side.space.code }} · {{ side.space.district }}</div>
          <div class="space-meta">地址：{{ side.space.address || '未填写' }}</div>
          <div class="space-meta">面积：{{ formatArea(side.space.area_sqm) }}</div>
          <div class="space-stats">
            任务 {{ statsOf(side.space).task_count }} 项 ·
            记录 {{ statsOf(side.space).record_count }} 条 ·
            更换 {{ statsOf(side.space).replacement_count }} 条
          </div>
        </template>
        <el-empty v-else description="尚未选择" :image-size="60" />
      </div>
    </div>

    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button type="danger" :disabled="!selected" :loading="merging" @click="confirmMerge">
        确认合并
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { greenSpaceApi } from '@/api'
import { formatArea } from '@/utils/format'

const emit = defineEmits(['merged'])

const visible = ref(false)
const current = ref(null)
const selectedId = ref(null)
const selected = ref(null)
const candidates = ref([])
const searching = ref(false)
const keep = ref('current')
const merging = ref(false)

const sides = computed(() => [
  { key: 'current', space: current.value },
  { key: 'other', space: selected.value },
])

function statsOf(space) {
  const stats = space?.statistics || {}
  return {
    task_count: stats.task_count ?? 0,
    record_count: stats.record_count ?? 0,
    replacement_count: stats.replacement_count ?? 0,
  }
}

function open(row) {
  current.value = row
  selectedId.value = null
  selected.value = null
  keep.value = 'current'
  visible.value = true
  search('')
}

function close() {
  visible.value = false
}

async function search(keyword) {
  if (!current.value) return
  searching.value = true
  try {
    const data = await greenSpaceApi.list({
      keyword: keyword?.trim() || undefined,
      district: current.value.district,
      page_size: 10,
    })
    candidates.value = (data?.items || []).filter((item) => item.id !== current.value.id)
  } finally {
    searching.value = false
  }
}

function onSelect(id) {
  selected.value = candidates.value.find((item) => item.id === id) || null
}

async function confirmMerge() {
  const target = keep.value === 'current' ? current.value : selected.value
  const source = keep.value === 'current' ? selected.value : current.value
  if (!target || !source) return
  const moved = statsOf(source)
  try {
    await ElMessageBox.confirm(
      `确认将「${source.name}」合并至「${target.name}」？` +
        `其 ${moved.task_count} 项任务、${moved.record_count} 条记录、` +
        `${moved.replacement_count} 条更换将全部转移保留，「${source.name}」档案将被删除。`,
      '合并确认',
      { type: 'warning', confirmButtonText: '确认合并', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  merging.value = true
  try {
    await greenSpaceApi.merge(target.id, source.id)
    ElMessage.success('绿地档案合并完成，原有任务与记录已全部保留')
    emit('merged', target)
    close()
  } catch {
    // 合并失败由请求层统一提示
  } finally {
    merging.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.merge-alert {
  margin-bottom: 16px;
}

.merge-select {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.select-label {
  color: #606266;
  font-size: 13px;
  white-space: nowrap;
}

.merge-compare {
  display: flex;
  gap: 16px;
}

.space-card {
  flex: 1;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  padding: 12px 16px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.space-card.active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary) inset;
}

.space-card.disabled {
  cursor: not-allowed;
  background: #fafafa;
}

.keep-line {
  margin-bottom: 8px;
}

.space-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 4px;
}

.space-meta {
  color: #909399;
  font-size: 12px;
  line-height: 1.8;
}

.space-stats {
  color: #606266;
  font-size: 12px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #e4e7ed;
}
</style>
