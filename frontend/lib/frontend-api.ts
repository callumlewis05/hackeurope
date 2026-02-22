import type {
  ApiValidationError,
  CalendarResponse,
  InterventionCompactCountResponse,
  InterventionListResponse,
  InterventionResponse,
  InterventionStatsResponse,
  EmailStatusResponse,
  UserProfileResponse,
} from "@/lib/api-types";

interface ApiResult<T> {
  ok: boolean;
  status: number;
  data: T | ApiValidationError | { detail?: string } | null;
}

async function parseJsonSafely(response: Response) {
  try {
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

export function toErrorMessage(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== "object") {
    return fallback;
  }

  const maybeValidation = payload as Partial<ApiValidationError>;
  const validationMessage = maybeValidation.detail?.[0]?.msg;
  if (validationMessage) {
    return validationMessage;
  }

  const maybeDetail = (payload as { detail?: string }).detail;
  if (typeof maybeDetail === "string") {
    return maybeDetail;
  }

  return fallback;
}

async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<ApiResult<T>> {
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
    cache: "no-store",
  });

  const data = await parseJsonSafely(response);

  return {
    ok: response.ok,
    status: response.status,
    data: (data as ApiResult<T>["data"]) ?? null,
  };
}

export async function getMe() {
  return apiRequest<UserProfileResponse>("/api/me", {
    method: "GET",
  });
}

export async function listCalendars() {
  return apiRequest<CalendarResponse[]>("/api/calendars", {
    method: "GET",
  });
}

export async function addCalendar(name: string, icalUrl: string) {
  return apiRequest<CalendarResponse>("/api/calendars", {
    method: "POST",
    body: JSON.stringify({ name, ical_url: icalUrl }),
  });
}

export async function deleteCalendar(calendarId: string) {
  return apiRequest<null>(`/api/calendars/${encodeURIComponent(calendarId)}`, {
    method: "DELETE",
  });
}

interface ListInterventionsQuery {
  domain?: string;
  intervened_only?: boolean;
  limit?: number;
  offset?: number;
}

interface CompactCountsQuery {
  lookback_days?: number;
}

function toQueryString(params: ListInterventionsQuery = {}) {
  const query = new URLSearchParams();

  if (params.domain) {
    query.set("domain", params.domain);
  }

  if (typeof params.intervened_only === "boolean") {
    query.set("intervened_only", String(params.intervened_only));
  }

  if (typeof params.limit === "number") {
    query.set("limit", String(params.limit));
  }

  if (typeof params.offset === "number") {
    query.set("offset", String(params.offset));
  }

  const serializedQuery = query.toString();
  return serializedQuery ? `?${serializedQuery}` : "";
}

function toCompactCountsQueryString(params: CompactCountsQuery = {}) {
  const query = new URLSearchParams();

  if (typeof params.lookback_days === "number") {
    query.set("lookback_days", String(params.lookback_days));
  }

  const serializedQuery = query.toString();
  return serializedQuery ? `?${serializedQuery}` : "";
}

export async function listInterventions(params: ListInterventionsQuery = {}) {
  return apiRequest<InterventionListResponse>(`/api/interventions${toQueryString(params)}`, {
    method: "GET",
  });
}

export async function getInterventionStats() {
  return apiRequest<InterventionStatsResponse>("/api/interventions/stats", {
    method: "GET",
  });
}

export async function getIntervention(interventionId: string) {
  return apiRequest<InterventionResponse>(`/api/interventions/${encodeURIComponent(interventionId)}`, {
    method: "GET",
  });
}

export async function getInterventionCategories(params: CompactCountsQuery = {}) {
  return apiRequest<InterventionCompactCountResponse>(
    `/api/interventions/categories${toCompactCountsQueryString(params)}`,
    {
      method: "GET",
    },
  );
}

export async function getInterventionMistakeTypes(params: CompactCountsQuery = {}) {
  return apiRequest<InterventionCompactCountResponse>(
    `/api/interventions/mistake_types${toCompactCountsQueryString(params)}`,
    {
      method: "GET",
    },
  );
}

export async function getEmailStatus() {
  return apiRequest<EmailStatusResponse>("/api/email/status", {
    method: "GET",
  });
}

export async function connectEmail(providerToken: string, providerRefreshToken: string | null) {
  return apiRequest<EmailStatusResponse>("/api/email/connect", {
    method: "POST",
    body: JSON.stringify({
      provider_token: providerToken,
      provider_refresh_token: providerRefreshToken,
    }),
  });
}

export async function disconnectEmail() {
  return apiRequest<null>("/api/email/disconnect", {
    method: "DELETE",
  });
}
