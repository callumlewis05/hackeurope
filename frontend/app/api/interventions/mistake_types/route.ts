import type { InterventionCompactCountResponse } from "@/lib/api-types";
import { proxyAuthedRequest } from "@/lib/proxy-auth";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.toString();
  const path = query ? `/api/interventions/mistake_types?${query}` : "/api/interventions/mistake_types";

  return proxyAuthedRequest<InterventionCompactCountResponse>({
    path,
    method: "GET",
  });
}
