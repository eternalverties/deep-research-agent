<script setup lang="ts">
import { computed } from "vue";

type Segment = {
  type: "text" | "link" | "bold";
  text: string;
  href?: string;
};

const props = defineProps<{ text: string }>();

function parseInline(input: string): Segment[] {
  const segments: Segment[] = [];
  const regex = /(\[([^\]]+)\]\((https?:\/\/[^)\s]+)\))|(\*\*([^*]+)\*\*)/g;
  let last = 0;

  for (const match of input.matchAll(regex)) {
    const index = match.index ?? 0;
    if (index > last) {
      segments.push({ type: "text", text: input.slice(last, index) });
    }
    if (match[3]) {
      segments.push({ type: "link", text: match[2], href: match[3] });
    } else if (match[5]) {
      segments.push({ type: "bold", text: match[5] });
    }
    last = index + match[0].length;
  }

  if (last < input.length) {
    segments.push({ type: "text", text: input.slice(last) });
  }
  return segments;
}

const paragraphs = computed(() =>
  String(props.text ?? "")
    .split(/\n{2,}/)
    .map((paragraph) => parseInline(paragraph)),
);
</script>

<template>
  <div class="rich-text">
    <p v-for="(segments, index) in paragraphs" :key="index">
      <template v-for="(segment, segmentIndex) in segments" :key="segmentIndex">
        <a
          v-if="segment.type === 'link'"
          :href="segment.href"
          target="_blank"
          rel="noopener"
        >
          {{ segment.text }}
        </a>
        <strong v-else-if="segment.type === 'bold'">{{ segment.text }}</strong>
        <span v-else>{{ segment.text }}</span>
      </template>
    </p>
  </div>
</template>
