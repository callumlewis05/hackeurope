import { NextResponse } from "next/server";

import type { ApiValidationError, EmailStatusResponse } from "@/lib/api-types";
import { proxyAuthedRequest } from "@/lib/proxy-auth";
import { readJsonBody } from "@/lib/backend-api";

interface ConnectEmailRequestBody {
  provider_token?: string;
  provider_refresh_token?: string | null;
}

function invalidPayloadResponse() {
  const detail: ApiValidationError["detail"] = [
    {
      loc: ["body"],
      msg: "provider_token is required",
      type: "value_error",
    },
  ];

  return NextResponse.json({ detail }, { status: 422 });
}

export async function POST(request: Request) {
  const body = await readJsonBody<ConnectEmailRequestBody>(request);

  if (!body || typeof body.provider_token !== "string") {
    return invalidPayloadResponse();
  }

  return proxyAuthedRequest<EmailStatusResponse>({
    path: "/api/email/connect",
    method: "POST",
    body: {
      provider_token: body.provider_token,
      provider_refresh_token: body.provider_refresh_token ?? null,
    },
  });
}
