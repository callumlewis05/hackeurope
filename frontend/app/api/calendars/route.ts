import { NextResponse } from "next/server";

import type { ApiValidationError, CalendarResponse } from "@/lib/api-types";
import { proxyAuthedRequest } from "@/lib/proxy-auth";
import { readJsonBody } from "@/lib/backend-api";

interface CreateCalendarRequestBody {
  name?: string;
  ical_url?: string;
}

function invalidCalendarPayloadResponse() {
  const detail: ApiValidationError["detail"] = [
    {
      loc: ["body"],
      msg: "name and ical_url are required",
      type: "value_error",
    },
  ];

  return NextResponse.json({ detail }, { status: 422 });
}

export async function GET() {
  return proxyAuthedRequest<CalendarResponse[]>({
    path: "/api/calendars",
    method: "GET",
  });
}

export async function POST(request: Request) {
  const body = await readJsonBody<CreateCalendarRequestBody>(request);

  if (!body || typeof body.name !== "string" || typeof body.ical_url !== "string") {
    return invalidCalendarPayloadResponse();
  }

  return proxyAuthedRequest<CalendarResponse>({
    path: "/api/calendars",
    method: "POST",
    body: {
      name: body.name,
      ical_url: body.ical_url,
    },
  });
}
