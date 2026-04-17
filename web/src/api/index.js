import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
api.interceptors.request.use(
  config => {
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  response => {
    return response.data
  },
  error => {
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

// 文章相关 API
export const articlesApi = {
  // 获取文章列表
  getList(params = {}) {
    return api.get('/articles', { params })
  },

  // 获取单篇文章
  getById(id) {
    return api.get(`/articles/${id}`)
  },

  // 获取事件详情（包含相关文章）
  getEventArticles(clusterId) {
    return api.get(`/articles/event/${clusterId}`)
  },

  // 翻译文章
  translate(id, data) {
    return api.post(`/articles/${id}/translate`, data)
  }
}

// 信息源相关 API
export const sourcesApi = {
  // 获取信息源列表
  getList(params = {}) {
    return api.get('/sources', { params })
  },

  // 获取单个信息源
  getById(id) {
    return api.get(`/sources/${id}`)
  },

  // 更新信息源
  update(id, data) {
    return api.patch(`/sources/${id}`, data)
  },

  // 获取候选信息源
  getCandidates() {
    return api.get('/sources/candidates')
  },

  // 审批候选信息源
  approveCandidate(id) {
    return api.post(`/sources/candidates/${id}/approve`)
  },

  // 拒绝候选信息源
  rejectCandidate(id) {
    return api.post(`/sources/candidates/${id}/reject`)
  },

  // 获取需要修复的站点
  getNeedsRepair() {
    return api.get('/sources/needs-repair')
  },

  // 手动重试
  retrySource(id) {
    return api.post(`/sources/${id}/retry`)
  },

  // 升级到 Tier 2
  upgradeTier(id) {
    return api.post(`/sources/${id}/upgrade-tier`)
  }
}

// 统计相关 API
export const statsApi = {
  // 获取系统统计
  getStats() {
    return api.get('/health/stats')
  },

  // 获取健康状态
  getHealth() {
    return api.get('/health')
  }
}

// 候选源相关 API
export const candidatesApi = {
  // 获取候选源列表
  getList(params = {}) {
    return api.get('/candidates', { params })
  },

  // 获取单个候选源
  getById(id) {
    return api.get(`/candidates/${id}`)
  },

  // 批准候选源
  approveCandidate(id, data = {}) {
    return api.post(`/candidates/${id}/approve`, data)
  },

  // 拒绝候选源
  rejectCandidate(id) {
    return api.post(`/candidates/${id}/reject`)
  }
}

// 事件相关 API
export const eventsApi = {
  // 获取事件列表
  getList(params = {}) {
    return api.get('/events', { params })
  },

  // 获取事件详情
  getById(id) {
    return api.get(`/events/${id}`)
  }
}

export default api
