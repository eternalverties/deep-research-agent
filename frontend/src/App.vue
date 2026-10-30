<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import ResearchForm from "./components/ResearchForm.vue";
import StatusPanel from "./components/StatusPanel.vue";
import TraceTimeline from "./components/TraceTimeline.vue";
import HitlPanel from "./components/HitlPanel.vue";
import ReportView from "./components/ReportView.vue";
import VerificationPanel from "./components/VerificationPanel.vue";
import { api } from "./api";
import type {
  Evidence,
  InterruptPayload,
  Report,
  ResearchStatus,
  ResumeDecision,
  VerificationSummary,
} from "./types";

const query = ref("");
const status = ref<ResearchStatus | null>(null);
const threadId = ref<string | null>(null);
const submitting = ref(false);
const errorMessage = ref("");
const elapsed = ref(0);
const health = ref<"checking" | "ok" | "bad">("checking");

let pollTimer: ReturnType<typeof setTimeout> | null = null;
let tickTimer: ReturnType<typeof setInterval> | null = null;
let startedAt = 0;

const traceEvents = computed(() => status.value?.trace ?? []);
const claims = computed(() => status.value?.claims ?? []);
const evidence = computed<Evidence[]>(() => status.value?.evidence ?? []);
const verification = computed<VerificationSummary | null>(
  () => status.value?.verification ?? null,
);
const report = computed<Report | null>(() => status.value?.report ?? null);
const searchProvider = computed(() => status.value?.search_provider ?? "");
const hitlPayload = computed<InterruptPayload | null>(
  () => status.value?.interrupt ?? null,
);
const isCompleted = computed(
  () => status.value?.status === "completed" && Boolean(report.value),
);
const showEmpty = computed(() => !status.value && !errorMessage.value);

function startTimers() {
  stopTimers();
  elapsed.value = 0;
  tickTimer = setInterval(() => {
    elapsed.value = Date.now() - startedAt;
  }, 500);
}

function stopTimers() {
  if (pollTimer) clearTimeout(pollTimer);
  if (tickTimer) clearInterval(tickTimer);
  pollTimer = null;
  tickTimer = null;
}

function schedulePoll(delay = 2000) {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = setTimeout(() => {
    void poll();
  }, delay);
}

async function poll() {
  if (!threadId.value) return;
  try {
    const data = await api.status(threadId.value);
    status.value = data;

    if (data.infrastructure_error) {
      errorMessage.value = `检索服务不可用：${data.infrastructure_error}`;
      stopTimers();
      return;
    }
    if (data.status === "completed") {
      stopTimers();
      return;
    }
    if (data.status === "interrupted") {
      stopTimers();
      return;
    }
    if (data.status === "error") {
      errorMessage.value = data.error ?? "运行失败。";
      stopTimers();
      return;
    }
    schedulePoll();
  } catch (error) {
    const message = error instanceof Error ? error.message : "请求失败。";
    if (message.includes("Unknown thread_id") || message.includes("404")) {
      localStorage.removeItem("dra.threadId");
      threadId.value = null;
      status.value = null;
    }
    errorMessage.value = message;
    stopTimers();
  }
}

async function startResearch(value: string) {
  submitting.value = true;
  errorMessage.value = "";
  status.value = null;
  threadId.value = null;
  localStorage.removeItem("dra.threadId");
  stopTimers();

  try {
    const accepted = await api.start(value);
    threadId.value = accepted.thread_id;
    localStorage.setItem("dra.threadId", accepted.thread_id);
    status.value = {
      thread_id: accepted.thread_id,
      status: "running",
      report: null,
      guardrail_flags: [],
      llm_calls: 0,
      iterations: 0,
      repairs: 0,
      verification: null,
      claims: null,
      evidence: null,
      trace: [],
      search_provider: null,
      infrastructure_error: null,
      error: null,
      interrupt: null,
    };
    startedAt = Date.now();
    startTimers();
    schedulePoll(0);
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "提交失败。";
  } finally {
    submitting.value = false;
  }
}

async function resume(decision: ResumeDecision) {
  if (!threadId.value) return;
  try {
    await api.resume(threadId.value, decision);
    if (status.value) {
      status.value = { ...status.value, status: "running", interrupt: null };
    }
    errorMessage.value = "";
    startedAt = Date.now();
    startTimers();
    schedulePoll(0);
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "恢复失败。";
  }
}

async function checkHealth() {
  try {
    const data = await api.health();
    health.value = data.status === "ok" ? "ok" : "bad";
  } catch {
    health.value = "bad";
  }
}

onMounted(async () => {
  void checkHealth();
  const saved = localStorage.getItem("dra.threadId");
  if (!saved) return;
  threadId.value = saved;
  startedAt = Date.now();
  startTimers();
  await poll();
});

onUnmounted(stopTimers);
</script>

<template>
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand">
        <div class="logo">DR</div>
        <div>
          <h1>Deep Research Agent</h1>
          <p>Vue 3 + TypeScript · 多智能体深度研究</p>
        </div>
      </div>
      <div class="top-actions">
        <span class="health">
          <span class="dot" :class="health"></span>
          <span>
            {{ health === "ok" ? "API 在线" : health === "bad" ? "API 离线" : "检测中" }}
          </span>
        </span>
        <a href="/docs" target="_blank" rel="noopener">API 文档</a>
        <a
          href="https://github.com/eternalverties/deep-research-agent"
          target="_blank"
          rel="noopener"
        >
          GitHub
        </a>
      </div>
    </div>
  </header>

  <main>
    <section class="hero">
      <div class="eyebrow">LangGraph · Multi-Agent · Evidence Grounded</div>
      <h2>
        从一个问题，到一份
        <span class="grad">可溯源的研究报告</span>
      </h2>
      <p>
        Planner 拆解问题，并行研究员联网检索，Critic 发现缺口后补研，
        Synthesizer 生成带引用的报告，Verifier 逐条核验断言与证据。
      </p>
    </section>

    <ResearchForm
      v-model="query"
      :disabled="submitting"
      @submit="startResearch"
    />

    <StatusPanel
      v-if="status || errorMessage"
      :status="status"
      :elapsed="elapsed"
      :error-message="errorMessage"
      :search-provider="searchProvider"
    />

    <TraceTimeline v-if="traceEvents.length" :events="traceEvents" />

    <HitlPanel v-if="hitlPayload" :payload="hitlPayload" @decision="resume" />

    <ReportView
      v-if="isCompleted && report && !errorMessage"
      :report="report"
      :flags="status?.guardrail_flags ?? []"
    />

    <VerificationPanel
      v-if="isCompleted && !errorMessage && claims.length"
      :claims="claims"
      :evidence="evidence"
      :verification="verification"
    />

    <section v-if="showEmpty" class="empty">
      提交问题后，这里会显示研究进度、执行轨迹、证据核验与最终报告。
    </section>
  </main>

  <footer>Built with Vue 3 · TypeScript · LangGraph · FastAPI</footer>
</template>
