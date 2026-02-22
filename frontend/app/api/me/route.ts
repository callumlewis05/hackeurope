import type { UserProfileResponse } from "@/lib/api-types";
import { proxyAuthedRequest } from "@/lib/proxy-auth";

export async function GET() {
  return proxyAuthedRequest<UserProfileResponse>({
    path: "/api/me",
    method: "GET",
  });
}
