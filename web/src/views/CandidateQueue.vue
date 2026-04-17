<template>
  <div class="candidate-queue">
    <h1>候选信息源审批</h1>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <select v-model="statusFilter">
        <option value="">全部</option>
        <option value="pending">待分析</option>
        <option value="approved">已批准</option>
        <option value="rejected">已拒绝</option>
      </select>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading">
      <span>加载中...</span>
    </div>

    <!-- 候选列表 -->
    <div v-else class="candidates-grid">
      <div 
        v-for="candidate in candidates" 
        :key="candidate.id" 
        class="candidate-card"
      >
        <!-- 头部 -->
        <div class="card-header">
          <div class="domain-info">
            <h3>{{ candidate.domain }}</h3>
            <span class="mention-count">
              被提及 {{ candidate.mention_count }} 次
            </span>
          </div>
          <span :class="['status-badge', candidate.status]">
            {{ getStatusLabel(candidate.status) }}
          </span>
        </div>

        <!-- LLM 分析结果 -->
        <div v-if="candidate.auto_analysis" class="analysis-section">
          <h4>AI 分析结果</h4>
          <div class="analysis-grid">
            <div class="analysis-item">
              <span class="label">汽车相关:</span>
              <span :class="['value', candidate.auto_analysis.is_automotive ? 'positive' : 'negative']">
                {{ candidate.auto_analysis.is_automotive ? '是' : '否' }}
              </span>
            </div>
            <div class="analysis-item">
              <span class="label">置信度:</span>
              <span class="value">{{ (candidate.auto_analysis.confidence * 100).toFixed(0) }}%</span>
            </div>
            <div class="analysis-item">
              <span class="label">语言:</span>
              <span class="value">{{ candidate.auto_analysis.language }}</span>
            </div>
            <div class="analysis-item">
              <span class="label">国家:</span>
              <span class="value">{{ candidate.auto_analysis.country }}</span>
            </div>
            <div class="analysis-item">
              <span class="label">更新频率:</span>
              <span class="value">{{ candidate.auto_analysis.update_frequency }}</span>
            </div>
            <div class="analysis-item">
              <span class="label">内容类型:</span>
              <span class="value">{{ candidate.auto_analysis.content_type }}</span>
            </div>
          </div>
          <p class="reason">{{ candidate.auto_analysis.reason }}</p>
        </div>

        <!-- 发现来源 -->
        <div v-if="candidate.discovered_from && candidate.discovered_from.length" class="sources-section">
          <h4>发现来源</h4>
          <ul class="source-list">
            <li v-for="(source, index) in candidate.discovered_from.slice(0, 3)" :key="index">
              <a :href="source.url" target="_blank">{{ source.article_title || '文章' }}</a>
            </li>
          </ul>
          <span v-if="candidate.discovered_from.length > 3" class="more-sources">
            +{{ candidate.discovered_from.length - 3 }} more
          </span>
        </div>

        <!-- 操作按钮 -->
        <div v-if="candidate.status === 'pending'" class="card-actions">
          <button class="btn btn-primary" @click="openApproveModal(candidate)">
            批准
          </button>
          <button class="btn btn-secondary" @click="reject(candidate.id)">
            拒绝
          </button>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="candidates.length === 0" class="empty-state">
        <p>暂无候选信息源</p>
      </div>
    </div>

    <!-- 批准弹窗 -->
    <div v-if="showApproveModal" class="modal-overlay" @click.self="closeApproveModal">
      <div class="modal">
        <h3>批准候选源</h3>
        <div class="form-group">
          <label>名称</label>
          <input v-model="approveForm.name" placeholder="输入站点名称" />
        </div>
        <div class="form-group">
          <label>国家</label>
          <select v-model="approveForm.country">
            <option value="US">美国</option>
            <option value="CN">中国</option>
            <option value="JP">日本</option>
            <option value="KR">韩国</option>
            <option value="DE">德国</option>
            <option value="FR">法国</option>
            <option value="GB">英国</option>
          </select>
        </div>
        <div class="form-group">
          <label>语言</label>
          <select v-model="approveForm.language">
            <option value="en">English</option>
            <option value="zh">中文</option>
            <option value="ja">日本語</option>
            <option value="ko">한국어</option>
            <option value="de">Deutsch</option>
            <option value="fr">Français</option>
          </select>
        </div>
        <div class="form-group">
          <label>优先级</label>
          <select v-model="approveForm.priority">
            <option value="high">高</option>
            <option value="medium">中</option>
            <option value="low">低</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="closeApproveModal">取消</button>
          <button class="btn btn-primary" @click="confirmApprove">确认批准</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { candidatesApi } from '../api'

const candidates = ref([])
const loading = ref(true)
const statusFilter = ref('')

// 批准弹窗
const showApproveModal = ref(false)
const currentCandidate = ref(null)
const approveForm = reactive({
  name: '',
  country: 'US',
  language: 'en',
  priority: 'medium'
})

// 加载候选列表
const loadCandidates = async () => {
  loading.value = true
  try {
    const params = {}
    if (statusFilter.value) params.status = statusFilter.value
    
    const data = await candidatesApi.getList(params)
    candidates.value = data.items || []
  } catch (error) {
    console.error('Failed to load candidates:', error)
  } finally {
    loading.value = false
  }
}

// 获取状态标签
const getStatusLabel = (status) => {
  const labels = {
    'new': '新发现',
    'pending_analysis': '待分析',
    'pending': '待审批',
    'approved': '已批准',
    'rejected': '已拒绝'
  }
  return labels[status] || status
}

// 打开批准弹窗
const openApproveModal = (candidate) => {
  currentCandidate.value = candidate
  approveForm.name = candidate.domain
  approveForm.country = candidate.auto_analysis?.country || 'US'
  approveForm.language = candidate.auto_analysis?.language || 'en'
  showApproveModal.value = true
}

// 关闭批准弹窗
const closeApproveModal = () => {
  showApproveModal.value = false
  currentCandidate.value = null
}

// 确认批准
const confirmApprove = async () => {
  if (!currentCandidate.value) return
  
  try {
    await candidatesApi.approveCandidate(currentCandidate.value.id, approveForm)
    closeApproveModal()
    loadCandidates()
  } catch (error) {
    console.error('Failed to approve candidate:', error)
  }
}

// 拒绝候选
const reject = async (id) => {
  if (!confirm('确定要拒绝这个候选源吗？')) return
  
  try {
    await candidatesApi.rejectCandidate(id)
    loadCandidates()
  } catch (error) {
    console.error('Failed to reject candidate:', error)
  }
}

// 监听筛选变化
watch(statusFilter, () => {
  loadCandidates()
})

onMounted(() => {
  loadCandidates()
})
</script>

<style scoped>
.candidate-queue {
  max-width: 1400px;
  margin: 0 auto;
}

.candidate-queue h1 {
  margin-bottom: 20px;
}

.filter-bar {
  margin-bottom: 20px;
}

.filter-bar select {
  width: 200px;
}

.loading {
  text-align: center;
  padding: 40px;
  color: var(--text-secondary);
}

.candidates-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 20px;
}

.candidate-card {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 15px;
}

.domain-info h3 {
  font-size: 1.1rem;
  margin-bottom: 5px;
}

.mention-count {
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.status-badge {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
}

.status-badge.pending {
  background-color: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
}

.status-badge.approved {
  background-color: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

.status-badge.rejected {
  background-color: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.analysis-section, .sources-section {
  margin-bottom: 15px;
  padding-bottom: 15px;
  border-bottom: 1px solid var(--border-color);
}

.analysis-section h4, .sources-section h4 {
  font-size: 0.9rem;
  color: var(--text-secondary);
  margin-bottom: 10px;
}

.analysis-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.analysis-item {
  display: flex;
  gap: 8px;
  font-size: 0.85rem;
}

.analysis-item .label {
  color: var(--text-secondary);
}

.analysis-item .value.positive {
  color: #22c55e;
}

.analysis-item .value.negative {
  color: #ef4444;
}

.reason {
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-top: 10px;
  font-style: italic;
}

.source-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.source-list li {
  font-size: 0.85rem;
  padding: 4px 0;
}

.source-list a {
  color: var(--accent-color);
}

.more-sources {
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.card-actions {
  display: flex;
  gap: 10px;
}

.empty-state {
  grid-column: 1 / -1;
  text-align: center;
  padding: 40px;
  color: var(--text-secondary);
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 24px;
  width: 400px;
  max-width: 90%;
}

.modal h3 {
  margin-bottom: 20px;
}

.form-group {
  margin-bottom: 15px;
}

.form-group label {
  display: block;
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-bottom: 5px;
}

.form-group input,
.form-group select {
  width: 100%;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}
</style>
