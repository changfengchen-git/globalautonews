<script setup>
import { RouterView, RouterLink } from 'vue-router'
</script>

<template>
  <div class="app">
    <!-- 顶部导航栏 -->
    <header class="navbar">
      <div class="navbar-brand">
        <RouterLink to="/" class="logo">GlobalAutoNews</RouterLink>
      </div>
      <nav class="navbar-menu">
        <RouterLink to="/" class="nav-link">新闻</RouterLink>
        <RouterLink to="/sources" class="nav-link">信息源</RouterLink>
        <RouterLink to="/candidates" class="nav-link">候选源</RouterLink>
        <RouterLink to="/dashboard" class="nav-link">概览</RouterLink>
      </nav>
    </header>

    <!-- 主内容区 -->
    <main class="main-content">
      <RouterView />
    </main>

    <!-- 底部 -->
    <footer class="footer">
      <p>GlobalAutoNews &copy; 2026</p>
    </footer>
  </div>
</template>

<style scoped>
.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.navbar {
  background-color: #1a1d29;
  padding: 0 20px;
  display: flex;
  align-items: center;
  height: 60px;
  border-bottom: 1px solid #2a2d3a;
}

.navbar-brand {
  margin-right: 40px;
}

.logo {
  color: #fff;
  font-size: 1.5rem;
  font-weight: bold;
  text-decoration: none;
}

.navbar-menu {
  display: flex;
  gap: 20px;
}

.nav-link {
  color: #a0a0a0;
  text-decoration: none;
  padding: 8px 12px;
  border-radius: 4px;
  transition: all 0.2s;
}

.nav-link:hover {
  color: #fff;
  background-color: #2a2d3a;
}

.nav-link.router-link-active {
  color: #fff;
  background-color: #3a3d4a;
}

.main-content {
  flex: 1;
  background-color: #0f1117;
  padding: 20px;
}

.footer {
  background-color: #1a1d29;
  padding: 20px;
  text-align: center;
  color: #666;
  border-top: 1px solid #2a2d3a;
}
</style>
