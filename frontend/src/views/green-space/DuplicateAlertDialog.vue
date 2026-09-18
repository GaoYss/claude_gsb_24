<template>
  <el-dialog
    :model-value="visible"
    title="发现疑似重复的绿地档案"
    width="880px"
    top="8vh"
    @update:model-value="close"
  >
    <el-alert type="warning" show-icon :closable="false" class="dup-alert">
      <template #title>
        同一行政区内已存在 {{ duplicates.length }} 处名称或位置相近的绿地档案，请核对是否为同一绿地。
        若确属重复，可{{ isEdit ? '合并档案' : '取消本次建档，直接使用已有档案' }}；确认不重复可继续{{ isEdit ? '保存' : '新建' }}。
      </template>
    </el-alert>

    <el-table :data="duplicates" border stripe size="small" class="dup-table">
      <el-table-column prop="code" label="绿地编号" width="130" />
      <el-table-column label="绿地名称" min-width="150">
        <template #default="{ row }">
          <div>{{ row.name }}</div>
          <el-tag v-if="row.match_reasons?.includes('name')" type="danger" size="small">名称相近</el-tag>
          <el-tag v-if="row.match_reasons?.includes('address')" type="warning" size="small">位置相近</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="district" label="行政区" width="85" />
      <el-table-column label="详细地址" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">{{ row.address || '未填写' }}</template>
      </el-table-column>
      <el-table-column label="面积" width="100" align="right">
        <template #default="{ row }">{{ formatArea(row.area_sqm) }}</template>
      </el-table-column>
      <el-table-column label="已有养护数据" width="170">
        <template #default="{ row }">
          任务 {{ row.statistics?.task_count ?? 0 }} 项 · 记录 {{ row.statistics?.record_count ?? 0 }} 条 ·
          更换 {{ row.statistics?.replacement_count ?? 0 }} 条
        </template>
      </el-table-column>
      <el-table-column label="操作" :width="isEdit ? 185 : 90" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="emit('view', row)">查看档案</el-button>
          <el-button v-if="isEdit" link type="danger" @click="emit('merge', row)">合并到该档案</el-button>
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button type="primary" @click="confirm">确认不重复，仍要{{ isEdit ? '保存' : '新建' }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'

import { formatArea } from '@/utils/format'

const emit = defineEmits(['confirm', 'merge', 'view'])

const visible = ref(false)
const duplicates = ref([])
const mode = ref('create')

const isEdit = computed(() => mode.value === 'edit')

function open(items, currentMode = 'create') {
  duplicates.value = items || []
  mode.value = currentMode
  visible.value = true
}

function close() {
  visible.value = false
}

function confirm() {
  visible.value = false
  emit('confirm')
}

defineExpose({ open, close })
</script>

<style scoped>
.dup-alert {
  margin-bottom: 12px;
}

.dup-table .el-tag + .el-tag {
  margin-left: 4px;
}
</style>
