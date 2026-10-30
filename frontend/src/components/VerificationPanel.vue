<script setup lang="ts">
import { computed } from "vue";
import type { Claim, Evidence, VerificationSummary } from "../types";
import { safeUrl } from "../utils";

const props = defineProps<{
  claims: Claim[];
  evidence: Evidence[];
  verification: VerificationSummary | null;
}>();

const evidenceMap = computed(
  () => new Map(props.evidence.map((item) => [item.evidence_id, item])),
);

const summaryText = computed(() => {
  const summary = props.verification;
  const total = summary?.total ?? props.claims.length;
  const supported = summary?.supported ?? 0;
  const contradicted = summary?.contradicted ?? 0;
  const insufficient = summary?.insufficient ?? 0;
  return `${total} 条断言 · 支持 ${supported} · 矛盾 ${contradicted} · 证据不足 ${insufficient}`;
});

const claimLabels: Record<Claim["status"], string> = {
  supported: "证据支持",
  contradicted: "存在矛盾",
  insufficient: "证据不足",
};

function evidenceForClaim(claim: Claim): Evidence[] {
  return claim.evidence_ids
    .map((id) => evidenceMap.value.get(id))
    .filter((item): item is Evidence => Boolean(item));
}
</script>

<template>
  <section v-if="claims.length" class="card report-card verification-card">
    <div class="section-head">
      <h2>证据核验</h2>
      <span class="muted">{{ summaryText }}</span>
    </div>
    <div class="verification-body">
      <article
        v-for="claim in claims"
        :key="claim.claim_id"
        class="claim-item"
      >
        <div class="claim-head">
          <p class="claim-text">{{ claim.content }}</p>
          <span class="status-chip" :class="claim.status">
            {{ claimLabels[claim.status] ?? claim.status }}
          </span>
        </div>
        <p v-if="claim.reason" class="claim-reason">{{ claim.reason }}</p>
        <div v-if="evidenceForClaim(claim).length" class="evidence-list">
          <div
            v-for="item in evidenceForClaim(claim)"
            :key="item.evidence_id"
            class="evidence-item"
          >
            <a
              :href="safeUrl(item.source_url) ?? '#'"
              target="_blank"
              rel="noopener"
            >
              {{ item.source_title || item.source_url }}
            </a>
            <div>{{ item.quote }}</div>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>
