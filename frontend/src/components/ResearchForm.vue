<script setup lang="ts">
import { ref } from "vue";

const query = defineModel<string>({ default: "" });
const props = withDefaults(defineProps<{ disabled?: boolean }>(), {
  disabled: false,
});
const emit = defineEmits<{ (event: "submit", query: string): void }>();

const error = ref("");
const samples = [
  {
    label: "LangGraph vs CrewAI",
    query: "LangGraph 和 CrewAI 在多智能体编排上的主要区别是什么？",
  },
  {
    label: "Agent 落地挑战",
    query: "大模型 Agent 在企业落地时面临的主要技术挑战是什么？",
  },
  {
    label: "RAG vs 微调",
    query: "RAG 和微调的适用场景与主要取舍是什么？",
  },
];

function submit() {
  const value = query.value.trim();
  if (value.length < 6) {
    error.value = "请输入一个具体的研究问题（至少 6 个字符）。";
    return;
  }
  error.value = "";
  emit("submit", value);
}
</script>

<template>
  <form class="card form-card" @submit.prevent="submit">
    <label for="query">研究问题</label>
    <textarea
      id="query"
      v-model="query"
      maxlength="2000"
      placeholder="例如：远程办公对软件团队协作效率的影响是什么？"
    ></textarea>
    <p v-if="error" class="field-error">{{ error }}</p>
    <div class="form-row">
      <div class="samples">
        <span>试试：</span>
        <button
          v-for="sample in samples"
          :key="sample.label"
          type="button"
          class="chip"
          @click="query = sample.query"
        >
          {{ sample.label }}
        </button>
      </div>
      <button type="submit" class="btn btn-primary" :disabled="props.disabled">
        {{ props.disabled ? "研究中…" : "开始研究" }}
      </button>
    </div>
  </form>
</template>
