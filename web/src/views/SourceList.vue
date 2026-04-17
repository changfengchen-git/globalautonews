<template>
  <div class="source-list">
    <h1>信息源列表</h1>
    
    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-value">{{ stats.total }}</div>
        <div class="stat-label">总站点</div>
      </div>
      <div class="stat-card active">
        <div class="stat-value">{{ stats.active }}</div>
        <div class="stat-label">活跃</div>
      </div>
      <div class="stat-card degraded">
        <div class="stat-value">{{ stats.degraded }}</div>
        <div class="stat-label">异常</div>
      </div>
      <div class="stat-card paused">
        <div class="stat-value">{{ stats.paused }}</div>
        <div class="stat-label">暂停</div>
      </div>
      <div class="stat-card archived">
        <div class="stat-value">{{ stats.archived }}</div>
        <div class="stat-label">归档</div>
      </div>
    </div>

    <!-- 筛选和搜索 -->
    <div class="filter-bar">
      <div class="search-box">
        <input 
          type="text" 
          v-model="searchQuery" 
          placeholder="搜索站点名称或域名..."
          @input="handleSearch"
        />
      </div>
      
      <div class="filters">
        <select v-model="statusFilter" @change="loadSources">
          <option value="">全部状态</option>
          <option value="active">活跃</option>
          <option value="degraded">异常</option>
          <option value="paused">暂停</option>
          <option value="archived">归档</option>
        </select>
        
        <select v-model="countryFilter" @change="loadSources">
          <option value="">全部国家</option>
          <option v-for="country in countries" :key="country" :value="country">
            {{ getCountryFlag(country) }} {{ country }}
          </option>
        </select>
        
        <select v-model="priorityFilter" @change="loadSources">
          <option value="">全部优先级</option>
          <option value="high">高</option>
          <option value="medium">中</option>
          <option value="low">低</option>
        </select>
      </div>
    </div>

    <!-- 站点表格 -->
    <div class="table-container">
      <table class="sources-table">
        <thead>
          <tr>
            <th class="sortable" @click="sortBy('name')">
              站点名称
              <span v-if="sortField === 'name'">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th>域名</th>
            <th>状态</th>
            <th>优先级</th>
            <th class="sortable" @click="sortBy('consecutive_errors')">
              错误数
              <span v-if="sortField === 'consecutive_errors'">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th>国家</th>
            <th>语言</th>
            <th>Tier</th>
            <th class="sortable" @click="sortBy('crawl_interval_minutes')">
              抓取间隔
              <span v-if="sortField === 'crawl_interval_minutes'">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th>最后抓取</th>
            <th>最后成功</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="source in sources" :key="source.id" :class="getRowClass(source)">
            <td class="name-cell">
              <span class="source-name">{{ source.name }}</span>
            </td>
            <td class="domain-cell">
              <a :href="'https://' + source.domain" target="_blank">{{ source.domain }}</a>
            </td>
            <td>
              <span :class="['status-badge', source.status]">
                <span class="status-dot"></span>
                {{ getStatusLabel(source.status) }}
              </span>
            </td>
            <td>
              <span :class="['priority-badge', source.priority]">
                {{ getPriorityLabel(source.priority) }}
              </span>
            </td>
            <td class="error-cell">
              <span v-if="source.consecutive_errors > 0" class="error-count">
                {{ source.consecutive_errors }}
              </span>
              <span v-else class="no-error">0</span>
            </td>
            <td>{{ getCountryFlag(source.country) }} {{ source.country || '-' }}</td>
            <td>{{ source.language || '-' }}</td>
            <td>
              <span :class="['tier-badge', 'tier-' + source.tier]">
                Tier {{ source.tier }}
              </span>
            </td>
            <td>{{ formatInterval(source.crawl_interval_minutes) }}</td>
            <td>{{ formatTime(source.last_crawl_at) }}</td>
            <td :class="['success-cell', { 'never': !source.last_success_at }]">
              {{ formatTime(source.last_success_at) || '从未成功' }}
            </td>
            <td class="actions-cell">
              <button 
                v-if="source.status === 'paused' || source.consecutive_errors > 0"
                class="btn btn-sm btn-primary" 
                @click="retrySource(source)"
                :disabled="retrying === source.id"
              >
                {{ retrying === source.id ? '重试中...' : '重试' }}
              </button>
              <button 
                v-if="source.tier < 2 && source.last_error_type === 'extract_empty'"
                class="btn btn-sm btn-secondary" 
                @click="upgradeTier(source)"
              >
                升级 T2
              </button>
              <button 
                v-if="source.status !== 'archived'"
                class="btn btn-sm btn-danger" 
                @click="pauseSource(source)"
              >
                暂停
              </button>
              <button 
                v-if="source.status === 'paused'"
                class="btn btn-sm btn-success" 
                @click="resumeSource(source)"
              >
                恢复
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      
      <!-- 空状态 -->
      <div v-if="sources.length === 0 && !loading" class="empty-state">
        <p>暂无匹配的站点</p>
      </div>
      
      <!-- 加载状态 -->
      <div v-if="loading" class="loading">
        <span>加载中...</span>
      </div>
    </div>

    <!-- 分页 -->
    <div class="pagination">
      <span class="page-info">
        显示 {{ (page - 1) * pageSize + 1 }} - {{ Math.min(page * pageSize, total) }} / 共 {{ total }} 个站点
      </span>
      <div class="page-buttons">
        <button class="btn btn-secondary" :disabled="page <= 1" @click="changePage(page - 1)">
          上一页
        </button>
        <span class="page-number">{{ page }}</span>
        <button class="btn btn-secondary" :disabled="page * pageSize >= total" @click="changePage(page + 1)">
          下一页
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { sourcesApi } from '../api'

// 数据
const sources = ref([])
const loading = ref(true)
const total = ref(0)
const page = ref(1)
const pageSize = 50

// 筛选
const searchQuery = ref('')
const statusFilter = ref('')
const countryFilter = ref('')
const priorityFilter = ref('')
const sortField = ref('name')
const sortOrder = ref('asc')

// 统计
const stats = reactive({
  total: 0,
  active: 0,
  degraded: 0,
  paused: 0,
  archived: 0
})

// 操作状态
const retrying = ref(null)

// 国家列表
const countries = computed(() => {
  const set = new Set(sources.value.map(s => s.country).filter(Boolean))
  return Array.from(set).sort()
})

// 加载站点列表
const loadSources = async () => {
  loading.value = true
  
  try {
    const params = {
      page: page.value,
      page_size: pageSize,
    }
    
    if (statusFilter.value) params.status = statusFilter.value
    if (countryFilter.value) params.country = countryFilter.value
    if (priorityFilter.value) params.priority = priorityFilter.value
    
    const data = await sourcesApi.getList(params)
    sources.value = data.items || []
    total.value = data.total || 0
    
    // 计算统计
    await loadStats()
    
  } catch (error) {
    console.error('Failed to load sources:', error)
  } finally {
    loading.value = false
  }
}

// 加载统计
const loadStats = async () => {
  try {
    // 获取所有状态的计数
    const [activeData, degradedData, pausedData, archivedData] = await Promise.all([
      sourcesApi.getList({ status: 'active', page_size: 1 }),
      sourcesApi.getList({ status: 'degraded', page_size: 1 }),
      sourcesApi.getList({ status: 'paused', page_size: 1 }),
      sourcesApi.getList({ status: 'archived', page_size: 1 }),
    ])
    
    stats.total = total.value
    stats.active = activeData.total || 0
    stats.degraded = degradedData.total || 0
    stats.paused = pausedData.total || 0
    stats.archived = archivedData.total || 0
    
  } catch (error) {
    console.error('Failed to load stats:', error)
  }
}

// 搜索
const handleSearch = () => {
  // 简单的客户端搜索过滤
  // 实际项目中应该调用 API 搜索
}

// 排序
const sortBy = (field) => {
  if (sortField.value === field) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = field
    sortOrder.value = 'asc'
  }
  
  sources.value.sort((a, b) => {
    let aVal = a[sortField.value] || ''
    let bVal = b[sortField.value] || ''
    
    if (typeof aVal === 'string') {
      aVal = aVal.toLowerCase()
      bVal = bVal.toLowerCase()
    }
    
    if (sortOrder.value === 'asc') {
      return aVal > bVal ? 1 : -1
    } else {
      return aVal < bVal ? 1 : -1
    }
  })
}

// 分页
const changePage = (newPage) => {
  page.value = newPage
  loadSources()
}

// 操作：重试
const retrySource = async (source) => {
  retrying.value = source.id
  try {
    await sourcesApi.retrySource(source.id)
    alert('已安排抓取')
    loadSources()
  } catch (error) {
    console.error('Failed to retry:', error)
    alert('操作失败')
  } finally {
    retrying.value = null
  }
}

// 操作：升级 Tier
const upgradeTier = async (source) => {
  if (!confirm(`确定要将 ${source.name} 升级到 Tier 2 吗？这将启用动态渲染。`)) return
  
  try {
    await sourcesApi.upgradeTier(source.id)
    alert('已升级到 Tier 2')
    loadSources()
  } catch (error) {
    console.error('Failed to upgrade:', error)
    alert('升级失败')
  }
}

// 操作：暂停
const pauseSource = async (source) => {
  if (!confirm(`确定要暂停 ${source.name} 吗？`)) return
  
  try {
    await sourcesApi.update(source.id, { status: 'paused' })
    loadSources()
  } catch (error) {
    console.error('Failed to pause:', error)
    alert('操作失败')
  }
}

// 操作：恢复
const resumeSource = async (source) => {
  try {
    await sourcesApi.update(source.id, { status: 'active' })
    loadSources()
  } catch (error) {
    console.error('Failed to resume:', error)
    alert('操作失败')
  }
}

// 格式化函数
const getStatusLabel = (status) => {
  const labels = {
    'active': '活跃',
    'degraded': '异常',
    'paused': '暂停',
    'archived': '归档',
    'pending': '待定'
  }
  return labels[status] || status
}

const getPriorityLabel = (priority) => {
  const labels = {
    'high': '高',
    'medium': '中',
    'low': '低'
  }
  return labels[priority] || priority
}

const getCountryFlag = (countryCode) => {
  const flags = {
    'US': '🇺🇸', 'CN': '🇨🇳', 'JP': '🇯🇵', 'KR': '🇰🇷',
    'DE': '🇩🇪', 'FR': '🇫🇷', 'GB': '🇬🇧', 'IT': '🇮🇹',
    'ES': '🇪🇸', 'SE': '🇸🇪', 'NL': '🇳🇱', 'AU': '🇦🇺',
    'HK': '🇭🇰', 'TW': '🇹🇼', 'IN': '🇮🇳', 'BR': '🇧🇷',
    'CA': '🇨🇦', 'RU': '🇷🇺', 'MX': '🇲🇽', 'TH': '🇹🇭',
  }
  return flags[countryCode] || '🌍'
}

const formatInterval = (minutes) => {
  if (!minutes) return '-'
  if (minutes < 60) return `${minutes}分钟`
  if (minutes < 1440) return `${Math.round(minutes / 60)}小时`
  return `${Math.round(minutes / 1440)}天`
}

const formatTime = (dateStr) => {
  if (!dateStr) return null
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return '刚刚'
  if (diffMins < 60) return `${diffMins}分钟前`
  if (diffHours < 24) return `${diffHours}小时前`
  if (diffDays < 7) return `${diffDays}天前`
  
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

const getRowClass = (source) => {
  if (source.status === 'paused') return 'row-paused'
  if (source.status === 'archived') return 'row-archived'
  if (source.consecutive_errors >= 5) return 'row-error'
  return ''
}

// 初始化
onMounted(() => {
  loadSources()
})
</script>

<style scoped>
.source-list {
  max-width: 1600px;
  margin: 0 auto;
  padding: 20px;
}

.source-list h1 {
  margin-bottom: 20px;
}

/* 统计卡片 */
.stats-row {
  display: flex;
  gap: 15px;
  margin-bottom: 25px;
  flex-wrap: wrap;
}

.stat-card {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 15px 25px;
  text-align: center;
  min-width: 100px;
}

.stat-value {
  font-size: 1.8rem;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-top: 5px;
}

.stat-card.active .stat-value { color: #22c55e; }
.stat-card.degraded .stat-value { color: #f59e0b; }
.stat-card.paused .stat-value { color: #ef4444; }
.stat-card.archived .stat-value { color: #6b7280; }

/* 筛选栏 */
.filter-bar {
  display: flex;
  gap: 15px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.search-box {
  flex: 1;
  min-width: 250px;
}

.search-box input {
  width: 100%;
  padding: 10px 15px;
  font-size: 0.95rem;
}

.filters {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.filters select {
  min-width: 120px;
  padding: 10px 12px;
}

/* 表格 */
.table-container {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
}

.sources-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}

.sources-table th,
.sources-table td {
  padding: 12px 15px;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}

.sources-table th {
  background-color: var(--bg-secondary);
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 0.85rem;
  white-space: nowrap;
}

.sources-table th.sortable {
  cursor: pointer;
  user-select: none;
}

.sources-table th.sortable:hover {
  color: var(--text-primary);
}

.sources-table tbody tr:hover {
  background-color: rgba(59, 130, 246, 0.05);
}

.sources-table tbody tr.row-paused {
  opacity: 0.7;
  background-color: rgba(239, 68, 68, 0.05);
}

.sources-table tbody tr.row-archived {
  opacity: 0.5;
  background-color: rgba(107, 114, 128, 0.05);
}

.sources-table tbody tr.row-error {
  background-color: rgba(245, 158, 11, 0.05);
}

/* 单元格样式 */
.name-cell .source-name {
  font-weight: 500;
}

.domain-cell a {
  color: var(--accent-color);
  text-decoration: none;
  font-size: 0.85rem;
}

.domain-cell a:hover {
  text-decoration: underline;
}

.error-cell .error-count {
  color: #ef4444;
  font-weight: 600;
}

.error-cell .no-error {
  color: #22c55e;
}

.success-cell.never {
  color: #ef4444;
  font-style: italic;
}

.actions-cell {
  white-space: nowrap;
}

/* 状态徽章 */
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: 500;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-badge.active {
  background-color: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}
.status-badge.active .status-dot { background-color: #22c55e; }

.status-badge.degraded {
  background-color: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}
.status-badge.degraded .status-dot { background-color: #f59e0b; }

.status-badge.paused {
  background-color: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}
.status-badge.paused .status-dot { background-color: #ef4444; }

.status-badge.archived {
  background-color: rgba(107, 114, 128, 0.15);
  color: #6b7280;
}
.status-badge.archived .status-dot { background-color: #6b7280; }

/* 优先级徽章 */
.priority-badge {
  padding: 3px 8px;
  border-radius: 3px;
  font-size: 0.75rem;
  font-weight: 500;
}

.priority-badge.high {
  background-color: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.priority-badge.medium {
  background-color: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.priority-badge.low {
  background-color: rgba(107, 114, 128, 0.15);
  color: #6b7280;
}

/* Tier 徽章 */
.tier-badge {
  padding: 3px 8px;
  border-radius: 3px;
  font-size: 0.75rem;
  font-weight: 500;
  background-color: var(--bg-secondary);
  color: var(--text-secondary);
}

.tier-badge.tier-2 {
  background-color: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
}

.tier-badge.tier-3 {
  background-color: rgba(139, 92, 246, 0.15);
  color: #8b5cf6;
}

/* 按钮 */
.btn-sm {
  padding: 5px 10px;
  font-size: 0.8rem;
  margin-right: 5px;
}

.btn-danger {
  background-color: transparent;
  border: 1px solid #ef4444;
  color: #ef4444;
}

.btn-danger:hover {
  background-color: #ef4444;
  color: white;
}

.btn-success {
  background-color: transparent;
  border: 1px solid #22c55e;
  color: #22c55e;
}

.btn-success:hover {
  background-color: #22c55e;
  color: white;
}

/* 分页 */
.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 20px;
  padding: 15px;
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.page-info {
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.page-buttons {
  display: flex;
  align-items: center;
  gap: 15px;
}

.page-number {
  font-weight: 600;
  min-width: 30px;
  text-align: center;
}

/* 空状态和加载 */
.empty-state, .loading {
  text-align: center;
  padding: 40px;
  color: var(--text-secondary);
}
</style>
