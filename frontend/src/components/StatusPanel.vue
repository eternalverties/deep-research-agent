<script setup lang="ts">
import { computed } from "vue";
import type { ResearchStatus } from "../types";
import { formatDuration, statusLabel } from "../utils";

const props = defineProps<{
  status: ResearchStatus | null;
  elapsed: number;
  errorMessage: string;
  searchProvider: string;
}>();

const badgeStatus = computed(() =>
  props.errorMessage ? "error" : props.status?.status ?? "running",
);
const providerText = computed(() => {
  if (!props.searchProvider) return "";
  if (props.searchProvider === "bing") {
    return "搜索降级：BING RSS（免费后备），结果质量可能低于 Tavily / Serper";
  }
  return `搜索源：${props.searchProvider.toUpperCase()}`;
});
const providerClass = computed(() =>
  props.searchProvider === "bing" ? "warning" : "provider",
);
</script>

<template>
  <section v-if="status || errorMessage" class="card status-card">
    <div class="status-head">
      <div class="status-left">
        <span class="badge" :class="badgeStatus">{{ statusLabel(badgeStatus) }}</span>
        <span v-if="status?.thread_id" class="thread mono">
          {{ status.thread_id }}
        </span>
      </div>
      <div class="metrics">
        <div class="metric">
          <span>{{ status?.llm_calls ?? 0 }}</span>
          <label>模型调用</label>
        </div>
        <div class="metric">
          <span>{{ status?.iterations ?? 0 }}</span>
          <label>迭代轮数</label>
        </div>
        <div class="metric">
          <span>{{ status?.repairs ?? 0 }}</span>
          <label>修复次数</label>
        </div>
        <div class="metric">
          <span>{{ formatDuration(elapsed) }}</span>
          <label>耗时</label>
        </div>
      </div>
    </div>
    <div
      v-if="badgeStatus === 'running'"
      class="progress"
      aria-label="研究进行中"
    >
      <div></div>
    </div>
    <div v-if="providerText" :class="providerClass">{{ providerText }}</div>
    <div v-if="errorMessage" class="error" role="alert">{{ errorMessage }}</div>
  </section>
</template>
