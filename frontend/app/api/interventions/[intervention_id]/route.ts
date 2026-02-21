import { NextResponse } from "next/server";

import type { InterventionResponse } from "@/lib/api-types";
import { proxyAuthedRequest } from "@/lib/proxy-auth";

interface RouteParams {
  params: Promise<{ intervention_id: string }>;
}

export async function GET(_request: Request, context: RouteParams) {
  const { intervention_id: interventionId } = await context.params;

  if (!interventionId) {
    return NextResponse.json(
      {
        detail: [
          {
            loc: ["path", "intervention_id"],
            msg: "intervention_id is required",
            type: "value_error",
          },
        ],
      },
      { status: 422 },
    );
  }

  return proxyAuthedRequest<InterventionResponse>({
    path: `/api/interventions/${encodeURIComponent(interventionId)}`,
    method: "GET",
  });
}
