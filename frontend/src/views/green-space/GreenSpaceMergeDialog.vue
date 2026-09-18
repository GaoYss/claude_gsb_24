<template>
  <el-dialog
    :model-value="visible"
    title="合并绿地档案"
    width="620px"
    destroy-on-close
    @update:model-value="close"
  >
    <template v-if="source">
      <el-alert
        type="warning"
        show-icon
        :closable="false"
        title="合并后，源档案的养护任务、养护记录与绿植更换记录将全部转移到保留档案，源档案随后删除，该操作不可撤销。"
      />

      <div class="merge-block">
        <div class="merge-label">源档案（合并后删除）</div>
        <div class="merge-card">
          <div class="merge-name">{{ source.name }} <span class="merge-code">{{ source.code }}</span></div>
          <div class="merge-meta">
            {{ source.district }} · {{ source.address || '地址未登记' }}
          </div>
          <div class="merge-meta">
            任务 {{ source.statistics?.task_count ?? 0 }} 项 ·
            记录 {{ source.statistics?.record_count ?? 0 }} 条 ·
            更换 {{ source.statistics?.replacement_count ?? 0 }} 条
          </div>
        </div>
      </div>

      <div class="merge-block">
        <div class="merge-label">合并到（保留该档案）</div>
        <GreenSpaceSelect
          v-model="targetId"
          :exclude-id="source.id"
          placeholder="搜索并选择要保留的绿地档案"
        />
      </div>
    </template>

    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button type="danger" :disabled="!targetId" :loading="submitting" @click="confirmMerge">
        确认合并
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

import { greenSpaceApi } from '@/api'
import GreenSpaceSelect from '@/components/common/GreenSpaceSelect.vue'

const emit = defineEmits(['merged'])

const visible = ref(false)
const submitting = ref(false)
const source = ref(null)
const targetId = ref(null)

function open(row) {
  source.value = row
  targetId.value = null
  visible.value = true
}

function close() {
  visible.value = false
}

async function confirmMerge() {
  if (!targetId.value || !source.value) return
  submitting.value = true
  try {
    const data = await greenSpaceApi.merge(targetId.value, source.value.id)
    const moved = data?.moved || {}
    ElMessage.success(
      `合并完成：已转移任务 ${moved.maintenance_task ?? 0} 项、记录 ${moved.maintenance_record ?? 0} 条、` +
        `更换 ${moved.plant_replacement ?? 0} 条`,
    )
    emit('merged', data)
    close()
  } finally {
    submitting.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.merge-block {
  margin-top: 16px;
}

.merge-label {
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
}

.merge-card {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 10px 14px;
  background: #fafafa;
}

.merge-name {
  font-weight: 600;
}

.merge-code {
  color: #909399;
  font-weight: 400;
  font-size: 12px;
  margin-left: 6px;
}

.merge-meta {
  color: #909399;
  font-size: 12px;
  margin-top: 4px;
}
</style>
