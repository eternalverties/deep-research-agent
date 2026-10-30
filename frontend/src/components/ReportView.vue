<script setup lang="ts">
import { computed, ref } from "vue";
import RichText from "./RichText.vue";
import type { Report } from "../types";
import { hostname, safeUrl } from "../utils";

const props = defineProps<{ report: Report; flags: string[] }>();
const copied = ref(false);

const uniqueCitations = computed(() => {
  const seen = new Set<string>();
  return (props.report.citations ?? []).filter((citation) => {
    if (!citation.url || seen.has(citation.url)) return false;
    seen.add(citation.url);
    return Boolean(safeUrl(citation.url));
  });
});

function markdown(): string {
  let output = `# 研究报告\n\n## 摘要\n${props.report.summary ?? ""}\n\n`;
  for (const section of props.report.sections ?? []) {
    output += `## ${section.heading}\n${section.content}\n\n`;
  }
  if (uniqueCitations.value.length) {
    output += "## 参考来源\n";
    for (const citation of uniqueCitations.value) {
      output += `- [${citation.title || citation.url}](${citation.url})\n`;
    }
  }
  return output;
}

async function copy() {
  const text = markdown();
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  copied.value = true;
  window.setTimeout(() => {
    copied.value = false;
  }, 1500);
}
</script>

<template>
  <section class="card report-card">
    <div class="section-head">
      <h2>研究报告</h2>
      <button type="button" class="btn btn-ghost" @click="copy">
        {{ copied ? "已复制" : "复制 Markdown" }}
      </button>
    </div>
    <div v-if="flags.length" class="flags">
      <span v-for="flag in flags" :key="flag" class="flag">{{ flag }}</span>
    </div>
    <div class="summary">
      <RichText :text="report.summary" />
    </div>
    <section
      v-for="section in report.sections"
      :key="section.heading"
      class="report-section"
    >
      <h3>{{ section.heading }}</h3>
      <RichText :text="section.content" />
      <div v-if="section.citations?.length" class="section-cites">
        <a
          v-for="url in section.citations"
          :key="url"
          :href="safeUrl(url) ?? '#'"
          target="_blank"
          rel="noopener"
        >
          {{ hostname(url) }}
        </a>
      </div>
    </section>
    <div v-if="uniqueCitations.length" class="citations">
      <h3>参考来源</h3>
      <div class="citation-list">
        <a
          v-for="citation in uniqueCitations"
          :key="citation.url"
          :href="safeUrl(citation.url) ?? '#'"
          target="_blank"
          rel="noopener"
        >
          {{ citation.title || citation.url }}
        </a>
      </div>
    </div>
  </section>
</template>
