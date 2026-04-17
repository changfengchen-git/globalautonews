<template>
  <div class="article-card" @click="$emit('click')">
    <!-- 题图缩略图 -->
    <div class="article-image">
      <img 
        v-if="article.image_url" 
        :src="article.image_url" 
        :alt="article.title"
        @error="handleImageError"
      />
      <div v-else class="image-placeholder">
        <span>📰</span>
      </div>
    </div>

    <!-- 文章内容 -->
    <div class="article-content">
      <!-- 标题 -->
      <h3 class="article-title">{{ article.title }}</h3>

      <!-- 摘要 -->
      <p class="article-excerpt">{{ excerpt }}</p>

      <!-- 元信息行 -->
      <div class="article-meta">
        <span class="source">{{ article.source_name }}</span>
        <span class="separator">|</span>
        <span class="country">{{ countryFlag }} {{ article.country }}</span>
        <span class="separator">|</span>
        <span class="language">{{ languageLabel }}</span>
        <span class="separator">|</span>
        <span class="time">{{ formattedTime }}</span>
      </div>

      <!-- 事件聚类链接 -->
      <div v-if="article.event_cluster_id && article.cluster_article_count > 1" class="cluster-link">
        <span class="cluster-icon">🔗</span>
        <span>{{ article.cluster_article_count }} 篇报道</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  article: {
    type: Object,
    required: true
  }
})

defineEmits(['click'])

// 图片加载失败处理
const imageError = ref(false)

const handleImageError = () => {
  imageError.value = true
}

// 摘要（最多2行）
const excerpt = computed(() => {
  const text = props.article.excerpt || props.article.content || ''
  if (text.length > 150) {
    return text.substring(0, 150) + '...'
  }
  return text
})

// 国旗 emoji
const countryFlags = {
  'US': '🇺🇸',
  'CN': '🇨🇳',
  'JP': '🇯🇵',
  'KR': '🇰🇷',
  'DE': '🇩🇪',
  'FR': '🇫🇷',
  'GB': '🇬🇧',
  'IT': '🇮🇹',
  'ES': '🇪🇸',
  'SE': '🇸🇪',
}

const countryFlag = computed(() => {
  return countryFlags[props.article.country] || '🌍'
})

// 语言标签
const languageNames = {
  'en': 'EN',
  'zh': '中文',
  'ja': '日文',
  'ko': '韩文',
  'de': '德文',
  'fr': '法文',
  'es': '西文',
}

const languageLabel = computed(() => {
  return languageNames[props.article.language] || props.article.language || '未知'
})

// 格式化时间
const formattedTime = computed(() => {
  const date = props.article.published_at || props.article.crawled_at
  if (!date) return ''
  
  const now = new Date()
  const publishDate = new Date(date)
  const diffMs = now - publishDate
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return '刚刚'
  if (diffMins < 60) return `${diffMins}分钟前`
  if (diffHours < 24) return `${diffHours}小时前`
  if (diffDays < 7) return `${diffDays}天前`
  
  return publishDate.toLocaleDateString('zh-CN')
})
</script>

<style scoped>
.article-card {
  display: flex;
  gap: 15px;
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 15px;
  cursor: pointer;
  transition: all 0.2s;
}

.article-card:hover {
  border-color: var(--accent-color);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.article-image {
  width: 120px;
  height: 80px;
  flex-shrink: 0;
  border-radius: 4px;
  overflow: hidden;
  background-color: var(--bg-secondary);
}

.article-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.image-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: var(--text-secondary);
}

.article-content {
  flex: 1;
  min-width: 0;
}

.article-title {
  font-size: 1rem;
  font-weight: 600;
  margin-bottom: 8px;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.article-excerpt {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin-bottom: 10px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.5;
}

.article-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.75rem;
  color: var(--text-secondary);
  flex-wrap: wrap;
}

.separator {
  color: var(--border-color);
}

.cluster-link {
  margin-top: 8px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.75rem;
  color: var(--accent-color);
  background-color: rgba(59, 130, 246, 0.1);
  padding: 4px 8px;
  border-radius: 4px;
}

.cluster-icon {
  font-size: 0.875rem;
}
</style>
