import type { EmailStatusResponse } from "@/lib/api-types";
import { proxyAuthedRequest } from "@/lib/proxy-auth";

export async function GET() {
  return proxyAuthedRequest<EmailStatusResponse>({
    path: "/api/email/status",
    method: "GET",
  });
}
