import http, { createResourceApi } from './client'

const base = createResourceApi('green-spaces')

export const greenSpaceApi = {
  ...base,
  /** 创建/更新支持 allow_duplicate 等查询参数（确认疑似重复后重试） */
  create: (payload, params) => http.post('/green-spaces', payload, { params }),
  update: (id, payload, params) => http.put(`/green-spaces/${id}`, payload, { params }),
  /** 下拉选项：仅返回未归档绿地 */
  options: (params) => http.get('/green-spaces/options', { params }),
  districts: () => http.get('/green-spaces/districts'),
  /** 绿地档案：台账 + 养护概览 + 近期任务/记录/更换 */
  profile: (id) => http.get(`/green-spaces/${id}/profile`),
  /** 合并重复档案：sourceId 的任务/记录/更换全部并入 id，source 删除 */
  merge: (id, sourceId) => http.post(`/green-spaces/${id}/merge`, { source_id: sourceId }),
}
