import { NextResponse } from "next/server";

import {
  authHeader,
  authJsonHeader,
  backendJsonRequest,
  cloneResponseData,
} from "@/lib/backend-api";
import { createClient } from "@/lib/supabase/server";

interface ProxyAuthRequestOptions {
  path: string;
  method: "GET" | "POST" | "DELETE";
  body?: unknown;
}

async function sendAuthedRequest<T>(accessToken: string, options: ProxyAuthRequestOptions) {
  return backendJsonRequest<T>(options.path, {
    method: options.method,
    headers: options.body === undefined ? authHeader(accessToken) : authJsonHeader(accessToken),
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
}

function unauthorizedResponse() {
  return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
}

export async function proxyAuthedRequest<T>(options: ProxyAuthRequestOptions) {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return unauthorizedResponse();
  }

  const {
    data: { session },
  } = await supabase.auth.getSession();

  const accessToken = session?.access_token;
  if (!accessToken) {
    return unauthorizedResponse();
  }

  const backendResponse = await sendAuthedRequest<T>(accessToken, options);
  return cloneResponseData(backendResponse.status, backendResponse.data);
}
