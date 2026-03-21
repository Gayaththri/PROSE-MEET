/**
 * Prosody Graph Panel — Acoustic Analysis
 * Shows pitch and energy over time so examiners can see the raw signal processing.
 */
import { useMemo } from "react";
import {
  SignalIcon,
  ChartBarSquareIcon,
  ChartBarIcon,
} from "@heroicons/react/24/outline";
import LoadingSkeleton from "./LoadingSkeleton";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

function buildAcousticSeries(transcript) {
  if (!Array.isArray(transcript) || transcript.length === 0) return [];
  // Keep charts in true meeting chronology so they align with "Full conversation".
  const chronological = [...transcript].sort(
    (a, b) => (Number(a?.start) || 0) - (Number(b?.start) || 0)
  );
  return chronological.map((seg) => {
    const start = typeof seg.start === "number" ? seg.start : 0;
    const end = typeof seg.end === "number" ? seg.end : start;
    // Align chart points with the same "start time" convention used by the transcript/timeline.
    // (Timeline detail uses [starts - ends]; this keeps x-axis times consistent.)
    const time = start;
    const pitch = typeof seg.mean_pitch === "number" && Number.isFinite(seg.mean_pitch) && seg.mean_pitch > 0
      ? seg.mean_pitch
      : null;
    const energy = typeof seg.mean_energy === "number" && Number.isFinite(seg.mean_energy) && seg.mean_energy > 0
      ? seg.mean_energy
      : null;
    return {
      time,
      pitch,
      energy,
    };
  });
}

export default function AcousticAnalysisPanel({ transcript = [], loading = false }) {
  const data = useMemo(
    () => buildAcousticSeries(transcript),
    [transcript]
  );
  const totalSegments = transcript.length;
  const validPitchPoints = data.filter((p) => typeof p.pitch === "number").length;
  const validEnergyPoints = data.filter((p) => typeof p.energy === "number").length;
  const hasAnyAcousticData = validPitchPoints > 0 || validEnergyPoints > 0;

  if (!data.length || !hasAnyAcousticData) {
    return (
      <article className="saas-card saas-card-full saas-acoustic-card">
        <h3 className="saas-card-title">
          <span className="saas-card-icon" aria-hidden="true">
            <SignalIcon width={18} height={18} />
          </span>{" "}
          Acoustic Analysis
        </h3>
        {loading ? (
          <>
            <p className="saas-acoustic-desc">
              Acoustic charts will appear after transcript segments are available.
            </p>
            <div className="saas-acoustic-charts">
              <LoadingSkeleton className="saas-skeleton-chart" />
              <LoadingSkeleton className="saas-skeleton-chart" />
            </div>
          </>
        ) : (
          <p className="saas-acoustic-desc">
            No prosodic features available for this meeting.
          </p>
        )}
      </article>
    );
  }

  return (
    <article className="saas-card saas-card-full saas-acoustic-card">
      <div className="saas-acoustic-header">
        <div>
          <h3 className="saas-card-title">
            <span className="saas-card-icon" aria-hidden="true">
              <SignalIcon width={18} height={18} />
            </span>{" "}
            Prosody graph
          </h3>
          <p className="saas-acoustic-desc">
            Pitch and energy extracted from the audio over time. This view shows the
            underlying signal processing used for prosody-aware importance.
          </p>
        </div>
        <div className="saas-acoustic-summary">
          <span className="saas-acoustic-summary-label">Valid points</span>
          <strong>{Math.max(validPitchPoints, validEnergyPoints)}</strong>
          <span className="saas-acoustic-summary-label">
            Pitch {validPitchPoints} | Energy {validEnergyPoints} | Segments {totalSegments}
          </span>
        </div>
      </div>

      <div className="saas-acoustic-charts">
        <div className="saas-acoustic-chart">
          <div className="saas-acoustic-chart-title">
            <span className="saas-acoustic-chart-icon" aria-hidden="true">
              <ChartBarSquareIcon width={16} height={16} />
            </span>{" "}
            Pitch curve
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis
                dataKey="time"
                tickFormatter={(v) => `${v.toFixed(0)}s`}
                fontSize={11}
              />
              <YAxis
                tickFormatter={(v) => v.toFixed(0)}
                fontSize={11}
              />
              <Tooltip
                labelFormatter={(v) => `${v.toFixed(1)}s`}
                formatter={(value) => value.toFixed(2)}
              />
              <Line
                type="monotone"
                dataKey="pitch"
                name="Pitch (proxy)"
                stroke="#6366f1"
                dot={false}
                strokeWidth={2}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="saas-acoustic-chart">
          <div className="saas-acoustic-chart-title">
            <span className="saas-acoustic-chart-icon" aria-hidden="true">
              <ChartBarIcon width={16} height={16} />
            </span>{" "}
            Energy curve
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis
                dataKey="time"
                tickFormatter={(v) => `${v.toFixed(0)}s`}
                fontSize={11}
              />
              <YAxis
                tickFormatter={(v) => v.toFixed(3)}
                fontSize={11}
              />
              <Tooltip
                labelFormatter={(v) => `${v.toFixed(1)}s`}
                formatter={(value) => value.toFixed(3)}
              />
              <Line
                type="monotone"
                dataKey="energy"
                name="Energy"
                stroke="#f97316"
                dot={false}
                strokeWidth={2}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </article>
  );
}

