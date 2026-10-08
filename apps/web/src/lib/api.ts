import { IntomdClient } from "@intomd/sdk";

export const CLIENT_NAME = `intomd-web/${__APP_VERSION__}`;

/** Creates the SDK client used by the whole UI. The UI never calls fetch directly. */
export function createClient(turnstileToken: () => Promise<string | undefined>): IntomdClient {
  return new IntomdClient({
    baseUrl: import.meta.env.VITE_API_BASE ?? "",
    clientName: CLIENT_NAME,
    turnstileToken,
    retry: true,
  });
}

export function errorMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message;
  return "Something went wrong. Please try again.";
}
