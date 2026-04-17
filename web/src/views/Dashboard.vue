<template>
  <div class="dashboard">
    <h1>系统概览</h1>

    <!-- 统计卡片 -->
    <div class="stats-cards">
      <div class="stat-card">
        <div class="stat-value">{{ stats.today_new || 0 }}</div>
        <div class="stat-label">今日新增文章</div>
        <div class="stat-sub">去重: {{ stats.today_duplicate || 0 }}</div>
      </div>

      <div class="stat-card">
        <div class="stat-value">{{ stats.active_sources || 0 }}</div>
        <div class="stat-label">活跃信息源</div>
        <div class="stat-sub">异常: {{ stats.abnormal_sources || 0 }}</div>
      </div>

      <div class="stat-card">
        <div class="stat-value">{{ stats.covered_languages || 0 }}</div>
        <div class="stat-label">覆盖语种</div>
        <div class="stat-sub">国家: {{ stats.covered_countries || 0 }}</div>
      </div>

      <div class="stat-card">
        <div class="stat-value">{{ stats.pending_candidates || 0 }}</div>
        <div class="stat-label">待审批候选源</div>
        <div class="stat-sub">
          <router-link to="/candidates">查看全部</router-link>
        </div>
      </div>
    </div>

    <!-- 站点健康矩阵 -->
    <div class="health-matrix">
      <h2>站点健康状态</h2>
      <div class="matrix-container">
        <div 
          v-for="country in healthMatrix" 
          :key="country.code" 
          class="country-group"
        >
          <div class="country-header">
            {{ country.flag }} {{ country.name }}
          </div>
          <div class="site-blocks">
            <div 
              v-for="site in country.sites" 
              :key="site.id"
              :class="['site-block', site.status]"
              :title="`${site.name}\n最后抓取: ${formatTime(site.last_crawl_at)}`"
            >
              <span class="status-dot"></span>
            </div>
          </div>
        </div>
      </div>
      <div class="matrix-legend">
        <span><span class="legend-dot active"></span> Active</span>
        <span><span class="legend-dot degraded"></span> Degraded</span>
        <span><span class="legend-dot paused"></span> Paused</span>
        <span><span class="legend-dot archived"></span> Archived</span>
      </div>
    </div>

    <!-- 最近抓取日志 -->
    <div class="recent-logs">
      <h2>最近抓取日志</h2>
      <div class="logs-table">
        <table>
          <thead>
            <tr>
              <th>站点</th>
              <th>状态</th>
              <th>新文章</th>
              <th>耗时</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in recentLogs" :key="log.id">
              <td>{{ log.source_name }}</td>
              <td>
                <span :class="['status-badge', log.status]">
                  {{ log.status }}
                </span>
              </td>
              <td>{{ log.articles_new || 0 }}</td>
              <td>{{ formatDuration(log.response_time_ms) }}</td>
              <td>{{ formatTime(log.started_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 需要修复的站点 -->
    <div class="needs-repair">
      <h2>需要修复的站点</h2>
      <div v-if="needsRepair.length === 0" class="empty-state">
        <p>暂无需要修复的站点</p>
      </div>
      <div v-else class="repair-list">
        <div v-for="source in needsRepair" :key="source.id" class="repair-card">
          <div class="repair-info">
            <h4>{{ source.name }}</h4>
            <span class="domain">{{ source.domain }}</span>
            <div class="repair-meta">
              <span>连续错误: {{ source.consecutive_errors }}</span>
              <span v-if="source.last_success_at">
                上次成功: {{ formatTime(source.last_success_at) }}
              </span>
            </div>
          </div>
          <div class="repair-actions">
            <button class="btn btn-primary" @click="retrySource(source.id)">
              手动重试
            </button>
            <button class="btn btn-secondary" @click="upgradeTier(source.id)">
              升级到 Tier 2
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { statsApi, sourcesApi } from '../api'

const stats = ref({})
const healthMatrix = ref([])
const recentLogs = ref([])
const needsRepair = ref([])
const loading = ref(true)

// 加载统计数据
const loadStats = async () => {
  try {
    const data = await statsApi.getStats()
    stats.value = data
  } catch (error) {
    console.error('Failed to load stats:', error)
  }
}

// 加载健康矩阵
const loadHealthMatrix = async () => {
  try {
    const data = await sourcesApi.getList({ limit: 200 })
    const sources = data.items || []

    // 按国家分组
    const countryGroups = {}
    sources.forEach(source => {
      const country = source.country || 'Unknown'
      if (!countryGroups[country]) {
        countryGroups[country] = {
          code: country,
          name: getCountryName(country),
          flag: getCountryFlag(country),
          sites: []
        }
      }
      countryGroups[country].sites.push(source)
    })

    healthMatrix.value = Object.values(countryGroups)
  } catch (error) {
    console.error('Failed to load health matrix:', error)
  }
}

// 加载最近日志
const loadRecentLogs = async () => {
  try {
    // 这里需要一个获取最近日志的 API
    // 暂时使用模拟数据
    recentLogs.value = []
  } catch (error) {
    console.error('Failed to load recent logs:', error)
  }
}

// 加载需要修复的站点
const loadNeedsRepair = async () => {
  try {
    const data = await sourcesApi.getNeedsRepair()
    needsRepair.value = data.items || []
  } catch (error) {
    console.error('Failed to load needs repair:', error)
  }
}

// 手动重试
const retrySource = async (id) => {
  try {
    await sourcesApi.retrySource(id)
    alert('已安排抓取')
  } catch (error) {
    console.error('Failed to retry source:', error)
    alert('操作失败')
  }
}

// 升级到 Tier 2
const upgradeTier = async (id) => {
  if (!confirm('确定要升级到 Tier 2 吗？这将启用动态渲染。')) return
  
  try {
    await sourcesApi.upgradeTier(id)
    alert('已升级到 Tier 2')
    loadNeedsRepair()
  } catch (error) {
    console.error('Failed to upgrade tier:', error)
    alert('升级失败')
  }
}

// 格式化时间
const formatTime = (dateStr) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN')
}

// 格式化持续时间
const formatDuration = (ms) => {
  if (!ms) return '-'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

// 获取国家名称
const getCountryName = (code) => {
  const names = {
    'US': '美国',
    'CN': '中国',
    'JP': '日本',
    'KR': '韩国',
    'DE': '德国',
    'FR': '法国',
    'GB': '英国',
  }
  return names[code] || code
}

// 获取国家旗帜
const getCountryFlag = (code) => {
  const flags = {
    'US': '🇺🇸',
    'CN': '🇨🇳',
    'JP': '🇯🇵',
    'KR': '🇰🇷',
    'DE': '🇩🇪',
    'FR': '🇫🇷',
    'GB': '🇬🇧',
  }
  return flags[code] || '🌍'
}

onMounted(async () => {
  loading.value = true
  await Promise.all([
    loadStats(),
    loadHealthMatrix(),
    loadRecentLogs(),
    loadNeedsRepair()
  ])
  loading.value = false
})
</script>

<style scoped>
.dashboard {
  max-width: 1400px;
  margin: 0 auto;
}

.dashboard h1 {
  margin-bottom: 30px;
}

.dashboard h2 {
  font-size: 1.25rem;
  margin-bottom: 20px;
  color: var(--text-primary);
}

/* 统计卡片 */
.stats-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 40px;
}

.stat-card {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
  text-align: center;
}

.stat-value {
  font-size: 2.5rem;
  font-weight: 700;
  color: var(--accent-color);
  margin-bottom: 5px;
}

.stat-label {
  font-size: 0.9rem;
  color: var(--text-secondary);
  margin-bottom: 5px;
}

.stat-sub {
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.stat-sub a {
  color: var(--accent-color);
}

/* 健康矩阵 */
.health-matrix {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 40px;
}

.matrix-container {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
}

.country-group {
  min-width: 150px;
}

.country-header {
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-bottom: 10px;
}

.site-blocks {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.site-block {
  width: 16px;
  height: 16px;
  border-radius: 3px;
  cursor: pointer;
  position: relative;
  transition: transform 0.2s;
}

.site-block:hover {
  transform: scale(1.2);
  z-index: 10;
}

.site-block.active {
  background-color: #22c55e;
}

.site-block.degraded {
  background-color: #f59e0b;
}

.site-block.paused {
  background-color: #ef4444;
}

.site-block.archived {
  background-color: #374151;
}

.matrix-legend {
  display: flex;
  gap: 20px;
  margin-top: 20px;
  padding-top: 15px;
  border-top: 1px solid var(--border-color);
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.legend-dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 2px;
  margin-right: 5px;
  vertical-align: middle;
}

.legend-dot.active { background-color: #22c55e; }
.legend-dot.degraded { background-color: #f59e0b; }
.legend-dot.paused { background-color: #ef4444; }
.legend-dot.archived { background-color: #374151; }

/* 最近日志 */
.recent-logs {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
}

.logs-table {
  overflow-x: auto;
}

.logs-table table {
  width: 100%;
  border-collapse: collapse;
}

.logs-table th,
.logs-table td {
  padding: 12px;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}

.logs-table th {
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 0.85rem;
}

.logs-table td {
  font-size: 0.9rem;
}

.status-badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
}

.status-badge.success {
  background-color: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

.status-badge.error {
  background-color: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.status-badge.warning {
  background-color: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
}

/* 需要修复的站点 */
.needs-repair {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
  margin-top: 40px;
}

.needs-repair h2 {
  margin-bottom: 20px;
}

.repair-list {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.repair-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px;
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
}

.repair-info h4 {
  margin-bottom: 5px;
}

.repair-info .domain {
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.repair-meta {
  display: flex;
  gap: 15px;
  margin-top: 8px;
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.repair-actions {
  display: flex;
  gap: 10px;
}

.empty-state {
  text-align: center;
  padding: 20px;
  color: var(--text-secondary);
}
</style>
