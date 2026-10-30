<script setup lang="ts">
import { computed } from "vue";
import type { TraceEvent } from "../types";
import { formatDuration } from "../utils";

const props = defineProps<{ events: TraceEvent[] }>();

const sorted = computed(() =>
  [...props.events].sort((left, right) => left.started_at - right.started_at),
);

const nodeLabels: Record<string, string> = {
  input_guard: "输入护栏",
  planner: "Planner",
  researcher: "Researcher",
  critic: "Critic",
  synthesizer: "Synthesizer",
  verifier: "Verifier",
  output_guard: "输出护栏",
  fail: "失败处理",
};

function nodeLabel(node: string): string {
  return nodeLabels[node] ?? node;
}
</script>

<template>
  <section v-if="sorted.length" class="card trace-card">
    <div class="section-head">
      <h2>执行轨迹</h2>
      <span class="muted">{{ sorted.length }} 个事件</span>
    </div>
    <div class="trace-list">
      <div
        v-for="(event, index) in sorted"
        :key="`${event.node}-${event.started_at}-${index}`"
        class="trace-item"
      >
        <div class="trace-head-row">
          <span class="trace-node">{{ nodeLabel(event.node) }}</span>
          <span class="trace-meta">
            {{ formatDuration(event.duration_ms) }} ·
            {{ event.llm_calls }} 次模型调用 · 轮次 {{ event.iteration }}
          </span>
        </div>
        <div class="trace-detail">{{ event.detail }}</div>
      </div>
    </div>
  </section>
</template>
