import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { updateSession } from "@/lib/supabase/proxy";

function redirectWithCookies(
  targetUrl: URL,
  sessionResponse: NextResponse<unknown>,
) {
  const redirectResponse = NextResponse.redirect(targetUrl);

  sessionResponse.cookies.getAll().forEach((cookie) => {
    redirectResponse.cookies.set(cookie);
  });

  return redirectResponse;
}

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const { response, user } = await updateSession(request);

  if (pathname.startsWith("/dashboard") && !user) {
    const loginUrl = new URL("/", request.url);
    return redirectWithCookies(loginUrl, response);
  }

  if (pathname === "/" && user) {
    const dashboardUrl = new URL("/dashboard", request.url);
    return redirectWithCookies(dashboardUrl, response);
  }

  return response;
}

export const config = {
  matcher: ["/", "/dashboard/:path*", "/api/:path*"],
};
