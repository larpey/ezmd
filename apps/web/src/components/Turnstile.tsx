import { useEffect, useRef } from "react";

const SCRIPT_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

let loader: Promise<void> | null = null;
function loadScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  loader ??= new Promise<void>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = SCRIPT_SRC;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => {
      loader = null;
      reject(new Error("Turnstile failed to load"));
    };
    document.head.appendChild(s);
  });
  return loader;
}

export interface TurnstileHandle {
  /** Returns the current token (single use) and resets the widget for the next one. */
  take: () => Promise<string | undefined>;
}

interface TurnstileProps {
  siteKey: string;
  handleRef: { current: TurnstileHandle | null };
}

/** Mounted only when capabilities.turnstile_site_key is present. Loaded from Cloudflare (CSP must allow it). */
export function Turnstile({ siteKey, handleRef }: TurnstileProps) {
  const el = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let widgetId: string | undefined;
    let token: string | undefined;
    let cancelled = false;
    let waiters: Array<(t: string | undefined) => void> = [];
    const settle = (t: string | undefined): void => {
      token = t;
      if (t) {
        waiters.forEach((w) => w(t));
        waiters = [];
      }
    };
    handleRef.current = {
      take: () => {
        const ready = token
          ? Promise.resolve(token)
          : new Promise<string | undefined>((resolve) => {
              waiters.push(resolve);
              setTimeout(() => resolve(undefined), 15_000);
            });
        return ready.then((t) => {
          token = undefined;
          if (widgetId) window.turnstile?.reset(widgetId);
          return t;
        });
      },
    };
    loadScript()
      .then(() => {
        if (cancelled || !el.current || !window.turnstile) return;
        widgetId = window.turnstile.render(el.current, {
          sitekey: siteKey,
          appearance: "interaction-only",
          callback: settle,
          "expired-callback": () => settle(undefined),
          "error-callback": () => settle(undefined),
        });
      })
      .catch(() => {
        // The API will answer turnstile_required; the UI shows that error.
      });
    return () => {
      cancelled = true;
      handleRef.current = null;
      if (widgetId) window.turnstile?.remove(widgetId);
    };
  }, [siteKey, handleRef]);

  return <div ref={el} className="turnstile" aria-label="Human verification" />;
}
