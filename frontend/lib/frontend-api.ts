import type { ApiValidationError, CalendarResponse, UserProfileResponse } from "@/lib/api-types";

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
