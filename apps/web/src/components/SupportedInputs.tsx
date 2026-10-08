import type { Capabilities } from "@intomd/sdk";

interface SupportedInputsProps {
  capabilities: Capabilities | null;
}

/** Lists what this instance can convert, straight from GET /v1/capabilities. */
export function SupportedInputs({ capabilities }: SupportedInputsProps) {
  if (!capabilities) return null;
  const families = new Map<string, Set<string>>();
  for (const c of capabilities.converters) {
    if (c.loaded === false) continue;
    const set = families.get(c.family) ?? new Set<string>();
    for (const m of [...(c.extensions ?? []), ...c.mimes]) set.add(m);
    if (c.experimental) set.add("(experimental)");
    families.set(c.family, set);
  }
  return (
    <details className="supported">
      <summary>Supported inputs ({families.size} families)</summary>
      {families.size === 0 ? (
        <p className="muted">No converters are loaded on this instance.</p>
      ) : (
        <dl className="supported-list">
          {[...families.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([family, types]) => (
            <div key={family} className="supported-row">
              <dt>{family}</dt>
              <dd>{[...types].join(", ")}</dd>
            </div>
          ))}
        </dl>
      )}
      {capabilities.limits.max_upload_bytes != null && (
        <p className="muted">Max upload: {Math.round(capabilities.limits.max_upload_bytes / (1024 * 1024))} MB.</p>
      )}
    </details>
  );
}
