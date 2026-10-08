/// <reference types="vite/client" />

declare const __APP_VERSION__: string;

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
}

interface TurnstileRenderOptions {
  sitekey: string;
  callback?: (token: string) => void;
  "expired-callback"?: () => void;
  "error-callback"?: () => void;
  size?: "normal" | "compact" | "flexible" | "invisible";
  appearance?: "always" | "execute" | "interaction-only";
}

interface Window {
  turnstile?: {
    render(el: HTMLElement, opts: TurnstileRenderOptions): string;
    reset(widgetId?: string): void;
    remove(widgetId?: string): void;
  };
}
