// Utilities for filtering and grouping reason labels.
const HIDDEN_REASON_PATTERNS = [
  /longer statement length suggests substantive content\.?/i,
  /decision\/planning keywords detected/i,
  /contains numeric details/i,
  /strong prosodic emphasis boosted/i,
  /moderate prosodic emphasis added a small importance boost\.?/i,
  /high pitch variation detected/i,
  /high speaking energy detected/i,
  /pause emphasis detected before or after this segment/i,
  /domain-adaptive numeric boost applied/i,
  /domain-adaptive boost:\s*corporate focus keywords matched/i,
  /context-window boost:\s*neighboring turns indicate related substantive discussion\.?/i,
  /prosody contributed to importance score\.?/i,
  /supervised fusion model probability\s*=\s*\d*\.?\d+/i,
];

function normalizeReason(reason) {
  return String(reason || "").trim().replace(/\s+/g, " ");
}

function shouldHideReason(reason) {
  const normalized = normalizeReason(reason);
  if (!normalized) return true;
  return HIDDEN_REASON_PATTERNS.some((pattern) => pattern.test(normalized));
}

export function sanitizeImportanceReasons(reasons) {
  if (!Array.isArray(reasons) || reasons.length === 0) return [];
  return reasons
    .map((reason) => normalizeReason(reason))
    .filter((reason) => reason.length > 0 && !shouldHideReason(reason));
}
