import type { InterventionListResponse } from "@/lib/api-types";
import { proxyAuthedRequest } from "@/lib/proxy-auth";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.toString();
  const path = query ? `/api/interventions?${query}` : "/api/interventions";

  return proxyAuthedRequest<InterventionListResponse>({
    path,
    method: "GET",
  });
}
