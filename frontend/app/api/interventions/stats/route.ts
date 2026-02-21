import type { InterventionStatsResponse } from "@/lib/api-types";
import { proxyAuthedRequest } from "@/lib/proxy-auth";

export async function GET() {
  return proxyAuthedRequest<InterventionStatsResponse>({
    path: "/api/interventions/stats",
    method: "GET",
  });
}
