import { NextResponse } from "next/server";

import { proxyAuthedRequest } from "@/lib/proxy-auth";

interface RouteParams {
  params: Promise<{ calendar_id: string }>;
}

export async function DELETE(_request: Request, context: RouteParams) {
  const { calendar_id: calendarId } = await context.params;

  if (!calendarId) {
    return NextResponse.json(
      {
        detail: [
          {
            loc: ["path", "calendar_id"],
            msg: "calendar_id is required",
            type: "value_error",
          },
        ],
      },
      { status: 422 },
    );
  }

  return proxyAuthedRequest<null>({
    path: `/api/calendars/${encodeURIComponent(calendarId)}`,
    method: "DELETE",
  });
}
