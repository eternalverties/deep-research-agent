<script setup lang="ts">
import { ref, watch } from "vue";
import type { InterruptPayload, ResumeDecision } from "../types";

const props = defineProps<{ payload: InterruptPayload }>();
const emit = defineEmits<{
  (event: "decision", decision: ResumeDecision): void;
}>();

const mode = ref<"" | "edit" | "reject">("");
const editText = ref("");
const feedback = ref("");
const error = ref("");

watch(
  () => props.payload,
  (payload) => {
    mode.value = "";
    editText.value = (payload.proposed_subtasks ?? []).join("\n");
    feedback.value = "";
    error.value = "";
  },
  { immediate: true, deep: true },
);

function choose(action: "approve" | "edit" | "reject" | "abort") {
  if (action === "approve") {
    emit("decision", { action: "approve" });
    return;
  }
  if (action === "abort") {
    emit("decision", { action: "abort", reason: "用户在界面中中止" });
    return;
  }
  mode.value = action;
  error.value = "";
}

function submitExtra() {
  if (mode.value === "edit") {
    const subtasks = editText.value
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    if (!subtasks.length) {
      error.value = "至少保留一个子任务。";
      return;
    }
    emit("decision", { action: "edit", subtasks });
  } else if (mode.value === "reject") {
    emit("decision", { action: "reject", feedback: feedback.value.trim() });
  }
  mode.value = "";
}
</script>

<template>
  <section class="card hitl">
    <h3>需要你的审批</h3>
    <p>
      {{ payload.message || "系统已生成研究计划，请确认方向后再继续。" }}
    </p>
    <p v-if="payload.query" class="muted">问题：{{ payload.query }}</p>
    <ol>
      <li v-for="task in payload.proposed_subtasks ?? []" :key="task">
        {{ task }}
      </li>
    </ol>
    <div class="hitl-actions">
      <button type="button" class="btn btn-primary" @click="choose('approve')">
        批准并继续
      </button>
      <button type="button" class="btn btn-ghost" @click="choose('edit')">
        修改后继续
      </button>
      <button type="button" class="btn btn-ghost" @click="choose('reject')">
        打回重规划
      </button>
      <button type="button" class="btn btn-danger" @click="choose('abort')">
        中止
      </button>
    </div>
    <div v-if="mode" class="hitl-extra">
      <label for="hitl-extra-text">
        {{ mode === "edit" ? "修改子任务（每行一个）" : "给规划器的反馈" }}
      </label>
      <textarea
        v-if="mode === 'edit'"
        id="hitl-extra-text"
        v-model="editText"
      ></textarea>
      <textarea v-else id="hitl-extra-text" v-model="feedback"></textarea>
      <p v-if="error" class="field-error">{{ error }}</p>
      <button type="button" class="btn btn-primary" @click="submitExtra">
        提交
      </button>
    </div>
  </section>
</template>
