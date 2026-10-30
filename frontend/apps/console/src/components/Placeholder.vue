<script setup lang="ts">
defineProps<{ title: string; desc?: string }>();
</script>

<template>
  <el-card shadow="never">
    <template #header>{{ title }}</template>
    <el-empty :description="desc ?? '功能开发中，敬请期待'" />
  </el-card>
</template>
