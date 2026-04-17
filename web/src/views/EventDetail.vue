<template>
  <div class="event-detail">
    <!-- 加载状态 -->
    <div v-if="loading" class="loading">
      <span>加载中...</span>
    </div>

    <!-- 事件内容 -->
    <div v-else-if="event" class="event-content">
      <!-- 事件头部 -->
      <header class="event-header">
        <h1>{{ representativeTitle }}</h1>
        
        <!-- 覆盖统计 -->
        <div class="event-stats">
          <span class="stat">
            <strong>{{ event.article_count }}</strong> 篇报道
          </span>
          <span class="stat">
            <strong>{{ event.language_count }}</strong> 种语言
          </span>
          <span class="stat">
            <strong>{{ event.country_count }}</strong> 个国家
          </span>
        </div>

        <!-- 覆盖地图（国家旗帜） -->
        <div class="coverage-flags">
          <span v-for="country in event.countries" :key="country" class="country-flag">
            {{ getCountryFlag(country) }}
          </span>
        </div>
      </header>

      <!-- 时间线视图 -->
      <section class="timeline">
        <h2>报道时间线</h2>
        
        <div class="articles-timeline">
          <div 
            v-for="article in sortedArticles" 
            :key="article.id" 
            class="timeline-item"
          >
            <!-- 时间线节点 -->
            <div class="timeline-marker">
              <span class="flag">{{ getCountryFlag(article.country) }}</span>
            </div>

            <!-- 文章卡片 -->
            <div class="article-card">
              <!-- 头部 -->
              <div class="card-header">
                <span class="source-name">{{ article.source_name }}</span>
                <span class="publish-time">{{ formatTime(article.published_at) }}</span>
              </div>

              <!-- 标题 -->
              <div class="card-title">
                <a :href="article.url" target="_blank" class="original-title">
                  {{ article.title }}
                </a>
                
                <!-- 翻译标题 -->
                <div v-if="getTranslatedTitle(article)" class="translated-title">
                  {{ getTranslatedTitle(article) }}
                </div>
              </div>

              <!-- 摘要 -->
              <p v-if="article.excerpt" class="excerpt">{{ article.excerpt }}</p>

              <!-- 操作按钮 -->
              <div class="card-actions">
                <button 
                  v-if="!getTranslatedContent(article)" 
                  class="btn btn-secondary btn-sm"
                  @click="translateArticle(article)"
                  :disabled="translating === article.id"
                >
                  {{ translating === article.id ? '翻译中...' : '翻译' }}
                </button>
                
                <a :href="article.url" target="_blank" class="btn btn-primary btn-sm">
                  查看原文
                </a>
              </div>

              <!-- 翻译内容 -->
              <div v-if="getTranslatedContent(article)" class="translated-content">
                <h4>翻译内容</h4>
                <p>{{ getTranslatedContent(article) }}</p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- 错误状态 -->
    <div v-else class="error-state">
      <p>无法加载事件详情</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { eventsApi, articlesApi } from '../api'

const route = useRoute()
const event = ref(null)
const loading = ref(true)
const translating = ref(null)

// 获取事件详情
const loadEvent = async () => {
  try {
    const eventId = route.params.id
    const data = await eventsApi.getById(eventId)
    event.value = data
  } catch (error) {
    console.error('Failed to load event:', error)
  } finally {
    loading.value = false
  }
}

// 按时间排序的文章
const sortedArticles = computed(() => {
  if (!event.value?.articles) return []
  return [...event.value.articles].sort((a, b) => {
    const dateA = new Date(a.published_at || a.crawled_at)
    const dateB = new Date(b.published_at || b.crawled_at)
    return dateB - dateA
  })
})

// 代表标题
const representativeTitle = computed(() => {
  if (!event.value?.articles?.length) return '事件详情'
  const rep = event.value.articles.find(a => !a.is_duplicate) || event.value.articles[0]
  return rep.title_zh || rep.title_en || rep.title
})

// 获取翻译标题
const getTranslatedTitle = (article) => {
  if (article.title_zh) return article.title_zh
  if (article.title_en) return article.title_en
  return null
}

// 获取翻译内容
const getTranslatedContent = (article) => {
  if (article.content_zh) return article.content_zh
  if (article.content_en) return article.content_en
  return null
}

// 翻译文章
const translateArticle = async (article) => {
  translating.value = article.id
  
  try {
    // 确定目标语言
    const targetLang = article.language === 'zh' ? 'en' : 'zh'
    
    const result = await articlesApi.translate(article.id, {
      target_language: targetLang
    })
    
    // 更新文章数据
    if (targetLang === 'zh') {
      article.title_zh = result.title_translated
      article.content_zh = result.content_translated
    } else {
      article.title_en = result.title_translated
      article.content_en = result.content_translated
    }
  } catch (error) {
    console.error('Failed to translate:', error)
    alert('翻译失败')
  } finally {
    translating.value = null
  }
}

// 获取国家旗帜
const getCountryFlag = (countryCode) => {
  const flags = {
    'US': '🇺🇸', 'CN': '🇨🇳', 'JP': '🇯🇵', 'KR': '🇰🇷',
    'DE': '🇩🇪', 'FR': '🇫🇷', 'GB': '🇬🇧', 'IT': '🇮🇹',
    'ES': '🇪🇸', 'SE': '🇸🇪', 'NL': '🇳🇱', 'AU': '🇦🇺',
  }
  return flags[countryCode] || '🌍'
}

// 格式化时间
const formatTime = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now - date
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffHours < 1) return '刚刚'
  if (diffHours < 24) return `${diffHours}小时前`
  if (diffDays < 7) return `${diffDays}天前`
  return date.toLocaleDateString('zh-CN')
}

onMounted(() => {
  loadEvent()
})
</script>

<style scoped>
.event-detail {
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px;
}

.loading, .error-state {
  text-align: center;
  padding: 60px;
  color: var(--text-secondary);
}

/* 事件头部 */
.event-header {
  margin-bottom: 40px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border-color);
}

.event-header h1 {
  font-size: 1.8rem;
  margin-bottom: 15px;
}

.event-stats {
  display: flex;
  gap: 20px;
  margin-bottom: 15px;
}

.stat {
  color: var(--text-secondary);
}

.stat strong {
  color: var(--accent-color);
  font-size: 1.2rem;
}

.coverage-flags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.country-flag {
  font-size: 1.5rem;
}

/* 时间线 */
.timeline h2 {
  margin-bottom: 20px;
}

.articles-timeline {
  position: relative;
  padding-left: 40px;
}

.articles-timeline::before {
  content: '';
  position: absolute;
  left: 15px;
  top: 0;
  bottom: 0;
  width: 2px;
  background-color: var(--border-color);
}

.timeline-item {
  position: relative;
  margin-bottom: 20px;
}

.timeline-marker {
  position: absolute;
  left: -40px;
  top: 10px;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--bg-card);
  border: 2px solid var(--border-color);
  border-radius: 50%;
}

.timeline-marker .flag {
  font-size: 1rem;
}

/* 文章卡片 */
.article-card {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 15px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 10px;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.card-title {
  margin-bottom: 10px;
}

.original-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
  text-decoration: none;
}

.original-title:hover {
  color: var(--accent-color);
}

.translated-title {
  margin-top: 8px;
  padding: 8px;
  background-color: var(--bg-secondary);
  border-radius: 4px;
  font-size: 0.95rem;
  color: var(--text-secondary);
}

.excerpt {
  font-size: 0.9rem;
  color: var(--text-secondary);
  margin-bottom: 15px;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-actions {
  display: flex;
  gap: 10px;
}

.btn-sm {
  padding: 6px 12px;
  font-size: 0.85rem;
}

.translated-content {
  margin-top: 15px;
  padding: 15px;
  background-color: var(--bg-secondary);
  border-radius: 6px;
}

.translated-content h4 {
  font-size: 0.9rem;
  margin-bottom: 10px;
  color: var(--text-secondary);
}

.translated-content p {
  font-size: 0.9rem;
  line-height: 1.6;
}
</style>
