import { proxyAuthedRequest } from "@/lib/proxy-auth";

export async function DELETE() {
  return proxyAuthedRequest<null>({
    path: "/api/email/disconnect",
    method: "DELETE",
  });
}
