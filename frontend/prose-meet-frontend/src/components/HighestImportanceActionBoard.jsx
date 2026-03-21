/**
 * Highest-importance moments as a vertical action-items list (one row each).
 * Icons reflect inferred type from segment text + importance_reasons.
 */
import { useMemo } from "react";
import { sanitizeImportanceReasons } from "../reasonFilters";

const DEFAULT_LIMIT = 8;
const ACTION_KEYWORDS = [
  "need to", "must", "should", "plan", "decide",
  "deadline", "budget", "aim", "goal", "will",
];
const TOPIC_KEYWORDS = [
  "project", "product", "requirement", "requirements", "budget", "design",
];
const FILLER_PHRASES = [
  "i don't know", "yeah", "okay", "i think",
];

function isNonSubstantiveSegment(seg) {
  const text = String(seg?.text || seg?.content || "").toLowerCase().trim();
  if (!text) return true;

  const chatterPatterns = [
    /\bblah\b/,
    /\bgood (morning|afternoon|evening)\b/,
    /\bhello\b/,
    /\bhi\b/,
    /\bwelcome\b/,
    /\bhow do you spell your name\b/,
    /\bspell your name\b/,
    /\bmy name is\b/,
    /\bi have no artistic talent\b/,
    /\bglad you could all come\b/,
    /\bexcited to start this team\b/,
  ];
  return chatterPatterns.some((pattern) => pattern.test(text));
}

function segmentText(seg) {
  return String(seg?.text || seg?.content || "").trim();
}

function containsAnyKeyword(textLower, keywords) {
  return keywords.some((keyword) => textLower.includes(keyword));
}

function countKeywordHits(textLower, keywords) {
  return keywords.reduce((acc, keyword) => acc + (textLower.includes(keyword) ? 1 : 0), 0);
}

function containsActionKeyword(seg) {
  const text = segmentText(seg).toLowerCase();
  return containsAnyKeyword(text, ACTION_KEYWORDS);
}

function semanticScore(seg) {
  const text = segmentText(seg).toLowerCase();
  const rawImportance = typeof seg?.importance_score === "number" ? seg.importance_score : 0;
  const reasons = sanitizeImportanceReasons(seg?.importance_reasons);
  const semanticReasonHits = reasons.filter(
    (reason) => !/(pitch|energy|pause|prosody|acoustic)/i.test(reason),
  ).length;
  const semanticKeywords = [
    "action", "next", "deadline", "decision", "agree", "plan", "owner", "follow",
    "risk", "issue", "target", "budget", "deliver", "meeting", "project",
    "requirement", "scope", "timeline", "market", "profit", "email", "instructions",
  ];
  const keywordHits = countKeywordHits(text, semanticKeywords);
  const wordCount = text.split(/\s+/).filter(Boolean).length;
  let score = 0;
  score += Math.min(rawImportance, 1.2) * 0.6;
  score += Math.min(keywordHits * 0.12, 0.24);
  score += Math.min(semanticReasonHits * 0.12, 0.24);
  if (wordCount >= 10) score += 0.1;
  return Math.max(0, Math.min(1.5, score));
}

function prosodyScore(seg) {
  const pitch = String(seg?.pitch_variation_level || "").toLowerCase();
  const energy = String(seg?.energy_level || "").toLowerCase();
  let score = 0;
  if (pitch === "high") score += 0.45;
  else if (pitch && pitch !== "—" && pitch !== "none" && pitch !== "low") score += 0.25;
  if (energy === "high") score += 0.45;
  else if (energy && energy !== "—" && energy !== "none" && energy !== "low") score += 0.25;
  if (seg?.pause_emphasis === true) score += 0.2;
  return Math.max(0, Math.min(1.2, score));
}

function actionKeywordScore(seg) {
  const text = segmentText(seg).toLowerCase();
  const hits = countKeywordHits(text, ACTION_KEYWORDS);
  return Math.max(0, Math.min(1, hits / 3));
}

function containsFillerPhrase(seg) {
  const text = segmentText(seg).toLowerCase();
  return containsAnyKeyword(text, FILLER_PHRASES);
}

function containsTopicKeyword(seg) {
  const text = segmentText(seg).toLowerCase();
  return containsAnyKeyword(text, TOPIC_KEYWORDS);
}

function applyPenaltiesAndBoosts(seg, baseScore) {
  const words = segmentText(seg).split(/\s+/).filter(Boolean);
  let score = baseScore;

  if (!containsActionKeyword(seg)) {
    score *= 0.6;
  }
  if (words.length < 5) {
    score *= 0.7;
  }
  if (containsFillerPhrase(seg)) {
    score *= 0.6;
  }
  if (containsTopicKeyword(seg)) {
    score += 0.2;
  }
  return score;
}

function finalImportanceScore(seg) {
  const rawImportance =
    typeof seg?.importance_score === "number" && Number.isFinite(seg.importance_score)
      ? seg.importance_score
      : 0;

  const sem = semanticScore(seg);
  const pro = prosodyScore(seg);
  const act = actionKeywordScore(seg);

  // Composite ranking for action items:
  // - Keep high model/rule importance as the main signal
  // - Require semantic/action relevance
  // - Reward prosodic emphasis as supporting evidence
  const base =
    0.45 * rawImportance +
    0.30 * sem +
    0.15 * pro +
    0.10 * act;
  return applyPenaltiesAndBoosts(seg, base);
}

function normalizeForSimilarity(text) {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function isNearDuplicate(textA, textB) {
  const a = normalizeForSimilarity(textA);
  const b = normalizeForSimilarity(textB);
  if (!a || !b) return false;

  const tokensA = new Set(a.split(" ").filter(Boolean));
  const tokensB = new Set(b.split(" ").filter(Boolean));
  if (!tokensA.size || !tokensB.size) return false;

  let intersection = 0;
  for (const token of tokensA) {
    if (tokensB.has(token)) intersection += 1;
  }
  const union = new Set([...tokensA, ...tokensB]).size;
  const jaccard = union ? intersection / union : 0;
  return jaccard >= 0.72;
}

function dedupeSimilarSegments(sortedSegments) {
  const kept = [];
  for (const seg of sortedSegments) {
    const text = segmentText(seg);
    const duplicate = kept.some((existing) => isNearDuplicate(text, segmentText(existing)));
    if (!duplicate) kept.push(seg);
  }
  return kept;
}

function isActionableSegment(seg) {
  return containsActionKeyword(seg) && semanticScore(seg) >= 0.45 && finalImportanceScore(seg) >= 0.45;
}

export function getTopImportanceSegments(transcript, limit = DEFAULT_LIMIT) {
  if (!Array.isArray(transcript) || transcript.length === 0) return [];

  const candidates = transcript.filter((seg) => !isNonSubstantiveSegment(seg));
  const scored = candidates.map((seg) => ({
    ...seg,
    __priority_score: finalImportanceScore(seg),
  }));

  const sorted = [...scored].sort(
    (a, b) => (b.__priority_score ?? 0) - (a.__priority_score ?? 0),
  );
  const unique = dedupeSimilarSegments(sorted);
  return unique.slice(0, Math.min(limit, unique.length));
}

function getActionIconMeta(segment) {
  const reasons = Array.isArray(segment.importance_reasons)
    ? segment.importance_reasons.join(" ")
    : "";
  const blob = `${segment.text || segment.content || ""} ${reasons}`.toLowerCase();

  if (/\?|question|clarif|unsure|wonder(ing)?/.test(blob)) {
    return { kind: "question", label: "Follow-up" };
  }
  if (/deadline|due |due:|tomorrow|by eod|eod|asap|by friday|by monday|end of|timeline/.test(blob)) {
    return { kind: "time", label: "Timeline" };
  }
  if (/decision|agreed|conclude|approve|commit|action item|follow up|next step|we will|let's do/.test(blob)) {
    return { kind: "decision", label: "Decision / owner" };
  }
  if (/risk|urgent|critical|blocker|issue|problem|concern|escalat|must not/.test(blob)) {
    return { kind: "risk", label: "Risk / flag" };
  }
  if (/energy|pitch|pause|prosody|volume|loud|emphas/.test(blob)) {
    return { kind: "prosody", label: "Emphasis" };
  }
  if (/goal|objective|milestone|deliverable|priority|flag/.test(blob)) {
    return { kind: "priority", label: "Priority" };
  }
  if (/discuss|conversation|said|mentioned|proposed/.test(blob)) {
    return { kind: "discussion", label: "Discussion" };
  }
  return { kind: "highlight", label: "Key moment" };
}

export default function HighestImportanceActionBoard({
  segments = [],
  emptyMessage = "No action items yet — scores appear after analysis completes.",
}) {
  const rows = useMemo(
    () =>
      segments.map((seg, idx) => {
        const meta = getActionIconMeta(seg);
        const id = seg.segment_id ?? `seg-${idx}-${seg.start}-${seg.end}`;
        return { seg, meta, id };
      }),
    [segments],
  );

  if (!rows.length) {
    return (
      <div className="saas-action-items-empty" role="status">
        <p>{emptyMessage}</p>
      </div>
    );
  }

  const actionRows = rows.filter(({ seg }) => isActionableSegment(seg));

  return (
    <div className="saas-priority-groups">
      <div className="saas-priority-group">
        <h4 className="saas-priority-group-title">Key decisions / action items</h4>
        {actionRows.length === 0 ? (
          <p className="saas-action-items-empty-inline">No explicit action-oriented items detected.</p>
        ) : (
          <ol className="saas-action-items-list" aria-label="Top action-oriented important moments">
            {actionRows.map(({ seg, id }, index) => {
              const body = seg.text || seg.content || "(no text)";
              const score =
                typeof seg.importance_score === "number"
                  ? seg.importance_score.toFixed(2)
                  : "—";
              const timeLabel =
                typeof seg.start === "number" && typeof seg.end === "number"
                  ? `${seg.start.toFixed(1)}s – ${seg.end.toFixed(1)}s`
                  : "—";
              const visibleReasons = sanitizeImportanceReasons(seg.importance_reasons);

              return (
                <li key={id} className="saas-action-items-row is-decision">
                  <span className="saas-action-items-index" aria-hidden="true">
                    {index + 1}
                  </span>
                  <div className="saas-action-items-body">
                    <div className="saas-action-items-meta">
                      <span className="saas-action-items-type">Action / decision</span>
                      <span className="saas-action-items-time">{timeLabel}</span>
                      <span className="saas-action-items-score">Score {score}</span>
                    </div>
                    <p className="saas-action-items-text">{body}</p>
                    {visibleReasons.length > 0 && (
                      <ul className="saas-action-items-reasons">
                        {visibleReasons.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
}
