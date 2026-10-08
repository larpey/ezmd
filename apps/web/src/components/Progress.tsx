import type { JobState } from "@intomd/sdk";

const STATE_LABELS: Record<string, string> = {
  queued: "Waiting in queue",
  fetching: "Fetching",
  detecting: "Detecting type",
  converting: "Converting",
  transcribing: "Transcribing",
  ocr: "Reading images",
  rendering: "Formatting",
  postprocessing: "Formatting",
  done: "Done",
  failed: "Failed",
  needs_user_action: "Needs your action",
  expired: "Expired on the server",
};

interface ProgressProps {
  state: JobState | string;
  progress: number;
  message?: string;
  converter?: string | null;
}

export function stateLabel(state: string, converter?: string | null): string {
  const base = STATE_LABELS[state] ?? state;
  return state === "converting" && converter ? `${base} (${converter})` : base;
}

export function Progress({ state, progress, message, converter }: ProgressProps) {
  const pct = Math.max(0, Math.min(100, Math.round(progress)));
  const determinate = pct > 0;
  const label = stateLabel(state, converter);
  return (
    <div className="progress" role="status" aria-live="polite">
      <div className="progress-text">
        <strong>{label}</strong>
        {message && message !== label && <span className="muted"> {message}</span>}
        {determinate && <span className="muted"> {pct}%</span>}
      </div>
      {determinate ? (
        <progress max={100} value={pct} aria-label={`${label} ${pct}%`} />
      ) : (
        <progress aria-label={label} />
      )}
    </div>
  );
}
