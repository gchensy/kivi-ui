/** Thin fetch wrapper for the FastAPI backend (same origin via Next rewrites). */

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
  }

  /** Field names reported by a 422 validation error. */
  get fields(): string[] {
    if (this.code !== "validation_error" || !Array.isArray(this.detail)) return [];
    return this.detail.map((e: { field?: string }) => e.field ?? "").filter(Boolean);
  }
}

type Json = Record<string, unknown> | unknown[];

export async function api<T>(path: string, init: { method?: string; body?: Json; signal?: AbortSignal } = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      method: init.method ?? (init.body ? "POST" : "GET"),
      credentials: "same-origin",
      signal: init.signal,
      headers: {
        Accept: "application/json",
        "X-Requested-With": "kivi-ui",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
      },
      body: init.body ? JSON.stringify(init.body) : undefined,
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(0, "network", "Network error");
  }
  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    // A proxied request to a backend that is down comes back as a bare 500.
    if (!payload || typeof payload.code !== "string") {
      throw new ApiError(response.status, response.status >= 500 ? "network" : "unknown", response.statusText);
    }
    throw new ApiError(response.status, payload.code, payload.message, payload.detail);
  }
  return payload as T;
}

/** Multipart upload (the browser sets the boundary); same error handling as `api`. */
export async function upload<T>(path: string, form: FormData): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      method: "POST",
      credentials: "same-origin",
      headers: { Accept: "application/json", "X-Requested-With": "kivi-ui" },
      body: form,
    });
  } catch {
    throw new ApiError(0, "network", "Network error");
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    if (!payload || typeof payload.code !== "string") {
      throw new ApiError(response.status, response.status === 413 ? "file_too_large" : "network", response.statusText);
    }
    throw new ApiError(response.status, payload.code, payload.message, payload.detail);
  }
  return payload as T;
}

/** Translate an error into a message key, honouring per-field validation errors. */
export function errorMessage(error: unknown, t: (key: string, vars?: Record<string, string | number>) => string): string {
  if (error instanceof ApiError) {
    if (error.code === "validation_error" && error.fields.length) {
      return error.fields.map((f) => t(`errors.field_${f}`)).join("；");
    }
    const vars = (error.detail && typeof error.detail === "object" ? error.detail : {}) as Record<string, number>;
    const key = `errors.${error.code}`;
    const text = t(key, vars);
    return text === key ? error.message || t("errors.unknown") : text;
  }
  return t("errors.unknown");
}
