import http, { createResourceApi } from './client'

const base = createResourceApi('green-spaces')

export const greenSpaceApi = {
  ...base,
  /** 下拉选项：仅返回未归档绿地 */
  options: (params) => http.get('/green-spaces/options', { params }),
  districts: () => http.get('/green-spaces/districts'),
  /** 绿地档案：台账 + 养护概览 + 近期任务/记录/更换 */
  profile: (id) => http.get(`/green-spaces/${id}/profile`),
  /** 合并重复档案：sourceId 的任务/记录/更换全部转移到 id，源档案删除 */
  merge: (id, sourceId) => http.post(`/green-spaces/${id}/merge`, { source_id: sourceId }),
}
