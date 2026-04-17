<template>
  <div class="news-feed">
    <!-- 顶部搜索栏 -->
    <div class="search-bar">
      <input 
        type="text" 
        v-model="searchQuery" 
        placeholder="搜索新闻..."
        @keyup.enter="handleSearch"
      />
      <button class="btn btn-primary" @click="handleSearch">搜索</button>
    </div>

    <div class="content-wrapper">
      <!-- 左侧筛选面板 -->
      <aside class="filter-panel">
        <h3>筛选条件</h3>
        
        <!-- 语种筛选 -->
        <div class="filter-section">
          <h4>语种</h4>
          <div class="checkbox-list">
            <label v-for="lang in availableLanguages" :key="lang.code" class="checkbox-item">
              <input type="checkbox" v-model="selectedLanguages" :value="lang.code" />
              <span>{{ lang.name }} ({{ lang.count }})</span>
            </label>
          </div>
        </div>

        <!-- 国家筛选 -->
        <div class="filter-section">
          <h4>国家</h4>
          <div class="checkbox-list">
            <label v-for="country in availableCountries" :key="country.code" class="checkbox-item">
              <input type="checkbox" v-model="selectedCountries" :value="country.code" />
              <span>{{ country.flag }} {{ country.name }} ({{ country.count }})</span>
            </label>
          </div>
        </div>

        <!-- 信息源筛选 -->
        <div class="filter-section">
          <h4>信息源</h4>
          <select v-model="selectedSource">
            <option value="">全部</option>
            <option v-for="source in availableSources" :key="source.id" :value="source.id">
              {{ source.name }}
            </option>
          </select>
        </div>

        <!-- 时间范围 -->
        <div class="filter-section">
          <h4>时间范围</h4>
          <div class="date-range">
            <input type="date" v-model="dateFrom" placeholder="开始日期" />
            <span>至</span>
            <input type="date" v-model="dateTo" placeholder="结束日期" />
          </div>
        </div>

        <!-- 显示重复文章 -->
        <div class="filter-section">
          <label class="checkbox-item">
            <input type="checkbox" v-model="showDuplicates" />
            <span>显示重复文章</span>
          </label>
        </div>

        <button class="btn btn-secondary" @click="resetFilters">重置筛选</button>
      </aside>

      <!-- 中间文章列表 -->
      <main class="article-list">
        <!-- 排序切换 -->
        <div class="sort-bar">
          <span>排序：</span>
          <button 
            :class="['sort-btn', { active: sortBy === 'latest' }]" 
            @click="sortBy = 'latest'"
          >
            最新
          </button>
          <button 
            :class="['sort-btn', { active: sortBy === 'important' }]" 
            @click="sortBy = 'important'"
          >
            最重要
          </button>
        </div>

        <!-- 文章卡片列表 -->
        <div class="articles">
          <ArticleCard 
            v-for="article in articles" 
            :key="article.id" 
            :article="article"
            @click="openArticle(article)"
          />
        </div>

        <!-- 加载状态 -->
        <div v-if="loading" class="loading">
          <span>加载中...</span>
        </div>

        <!-- 无更多内容 -->
        <div v-if="!hasMore && !loading" class="no-more">
          <span>没有更多文章了</span>
        </div>

        <!-- 分页 -->
        <div class="pagination" v-if="hasMore && !loading">
          <button class="btn btn-secondary" @click="loadMore">加载更多</button>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch, onMounted, computed } from 'vue'
import { articlesApi } from '../api'
import ArticleCard from '../components/ArticleCard.vue'

// 筛选条件
const searchQuery = ref('')
const selectedLanguages = ref([])
const selectedCountries = ref([])
const selectedSource = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const showDuplicates = ref(false)
const sortBy = ref('latest')

// 数据
const articles = ref([])
const loading = ref(false)
const hasMore = ref(true)
const page = ref(1)
const limit = 20

// 可用的筛选选项
const availableLanguages = ref([
  { code: 'en', name: 'English', count: 0 },
  { code: 'zh', name: '中文', count: 0 },
  { code: 'ja', name: '日本語', count: 0 },
  { code: 'ko', name: '한국어', count: 0 },
  { code: 'de', name: 'Deutsch', count: 0 },
  { code: 'fr', name: 'Français', count: 0 },
  { code: 'es', name: 'Español', count: 0 },
])

const availableCountries = ref([
  { code: 'US', name: '美国', flag: '🇺🇸', count: 0 },
  { code: 'CN', name: '中国', flag: '🇨🇳', count: 0 },
  { code: 'JP', name: '日本', flag: '🇯🇵', count: 0 },
  { code: 'KR', name: '韩国', flag: '🇰🇷', count: 0 },
  { code: 'DE', name: '德国', flag: '🇩🇪', count: 0 },
  { code: 'FR', name: '法国', flag: '🇫🇷', count: 0 },
  { code: 'GB', name: '英国', flag: '🇬🇧', count: 0 },
])

const availableSources = ref([])

// 加载文章
const loadArticles = async (reset = false) => {
  if (loading.value) return
  
  if (reset) {
    page.value = 1
    articles.value = []
    hasMore.value = true
  }

  loading.value = true

  try {
    const params = {
      page: page.value,
      limit: limit,
      sort: sortBy.value,
    }

    if (searchQuery.value) params.q = searchQuery.value
    if (selectedLanguages.value.length) params.languages = selectedLanguages.value.join(',')
    if (selectedCountries.value.length) params.countries = selectedCountries.value.join(',')
    if (selectedSource.value) params.source_id = selectedSource.value
    if (dateFrom.value) params.date_from = dateFrom.value
    if (dateTo.value) params.date_to = dateTo.value
    if (!showDuplicates.value) params.exclude_duplicates = true

    const data = await articlesApi.getList(params)
    
    if (reset) {
      articles.value = data.items || []
    } else {
      articles.value = [...articles.value, ...(data.items || [])]
    }

    hasMore.value = data.items && data.items.length === limit
    page.value++
  } catch (error) {
    console.error('Failed to load articles:', error)
  } finally {
    loading.value = false
  }
}

// 搜索
const handleSearch = () => {
  loadArticles(true)
}

// 加载更多
const loadMore = () => {
  loadArticles(false)
}

// 重置筛选
const resetFilters = () => {
  searchQuery.value = ''
  selectedLanguages.value = []
  selectedCountries.value = []
  selectedSource.value = ''
  dateFrom.value = ''
  dateTo.value = ''
  showDuplicates.value = false
  sortBy.value = 'latest'
  loadArticles(true)
}

// 打开文章
const openArticle = (article) => {
  window.open(article.url, '_blank')
}

// 监听筛选条件变化
watch([selectedLanguages, selectedCountries, selectedSource, dateFrom, dateTo, showDuplicates, sortBy], () => {
  loadArticles(true)
}, { deep: true })

// 初始化
onMounted(() => {
  loadArticles(true)
})
</script>

<style scoped>
.news-feed {
  max-width: 1400px;
  margin: 0 auto;
}

.search-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.search-bar input {
  flex: 1;
  padding: 10px 15px;
  font-size: 16px;
}

.content-wrapper {
  display: flex;
  gap: 20px;
}

.filter-panel {
  width: 260px;
  flex-shrink: 0;
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
  height: fit-content;
  position: sticky;
  top: 20px;
}

.filter-panel h3 {
  margin-bottom: 20px;
  font-size: 1.1rem;
}

.filter-section {
  margin-bottom: 20px;
}

.filter-section h4 {
  font-size: 0.9rem;
  color: var(--text-secondary);
  margin-bottom: 10px;
}

.checkbox-list {
  max-height: 200px;
  overflow-y: auto;
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  cursor: pointer;
  font-size: 0.9rem;
}

.checkbox-item input {
  width: auto;
}

.date-range {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.date-range span {
  color: var(--text-secondary);
  font-size: 0.8rem;
}

.article-list {
  flex: 1;
}

.sort-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
  color: var(--text-secondary);
}

.sort-btn {
  padding: 6px 12px;
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-secondary);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.sort-btn:hover {
  border-color: var(--accent-color);
  color: var(--text-primary);
}

.sort-btn.active {
  background-color: var(--accent-color);
  border-color: var(--accent-color);
  color: white;
}

.articles {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.loading, .no-more {
  text-align: center;
  padding: 30px;
  color: var(--text-secondary);
}

.pagination {
  text-align: center;
  padding: 20px;
}
</style>
