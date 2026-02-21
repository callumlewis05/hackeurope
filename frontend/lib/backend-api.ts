import { NextResponse } from "next/server";

const DEFAULT_BACKEND_BASE_URL = "https://0db0ec8f5fb9.ngrok.app";

const configuredBackendBaseUrl =
  process.env.BACKEND_API_BASE_URL ??
  process.env.NEXT_PUBLIC_BACKEND_API_BASE_URL ??
  DEFAULT_BACKEND_BASE_URL;

const backendBaseUrl = configuredBackendBaseUrl.replace(/\/$/, "");

interface JsonResponse<T> {
  status: number;
  data: T | null;
}

export async function readJsonBody<T>(request: Request): Promise<T | null> {
  try {
    return (await request.json()) as T;
  } catch {
    return null;
  }
}

export async function backendJsonRequest<T>(
  path: string,
  init: RequestInit,
): Promise<JsonResponse<T>> {
  const response = await fetch(`${backendBaseUrl}${path}`, {
    ...init,
    cache: "no-store",
  });

  let data: T | null = null;

  try {
    data = (await response.json()) as T;
  } catch {
    data = null;
  }

  return {
    status: response.status,
    data,
  };
}

export function cloneResponseData<T>(status: number, data: T | null): NextResponse {
  if (data === null) {
    return new NextResponse(null, { status });
  }

  return NextResponse.json(data, { status });
}

export function authHeader(accessToken: string): HeadersInit {
  return {
    Accept: "application/json",
    Authorization: `Bearer ${accessToken}`,
  };
}

export function authJsonHeader(accessToken: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...authHeader(accessToken),
  };
}
