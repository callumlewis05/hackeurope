"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { FiSettings } from "react-icons/fi";

import type { UserProfileResponse } from "@/lib/api-types";
import { getMe, toErrorMessage } from "@/lib/frontend-api";
import { createClient } from "@/lib/supabase/client";

export default function DashboardLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const router = useRouter();
  const [user, setUser] = useState<UserProfileResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  useEffect(() => {
    let isMounted = true;

    const loadUser = async () => {
      try {
        const response = await getMe();

        if (!isMounted) {
          return;
        }

        if (!response.ok) {
          if (response.status === 401) {
            router.replace("/");
            return;
          }

          setError(toErrorMessage(response.data, "Unable to load your profile."));
          return;
        }

        setUser((response.data as UserProfileResponse) ?? null);
      } catch {
        if (!isMounted) {
          return;
        }

        setError("Unable to reach the server.");
      }
    };

    void loadUser();

    return () => {
      isMounted = false;
    };
  }, [router]);

  const handleLogout = async () => {
    if (isLoggingOut) {
      return;
    }

    setIsLoggingOut(true);
    try {
      const supabase = createClient();
      await supabase.auth.signOut();
      router.replace("/");
      router.refresh();
    } finally {
      setIsLoggingOut(false);
    }
  };

  return (
    <div className="min-h-screen">
      <header className={"my-4"}>
        <div className="mx-auto flex w-full max-w-full h-9 px-4 items-center justify-between gap-4">
          <Link
            href="/dashboard"
            aria-label="Dashboard"
            className="h-full w-10 flex items-center justify-center"
          >
            <Image src="/icon2.svg" alt="App icon" width={40} height={40} />
          </Link>

          <div className="hidden flex-1 text-sm text-stone-600 md:block">
            {error ? <span>{error}</span> : <span>{user ? `Signed in as ${user.email}` : "Loading profile..."}</span>}
          </div>

          <div className="flex h-full items-center gap-2">
            <Link
              href="/dashboard/settings"
              className="bg-stone-100 h-full flex items-center justify-center aspect-square transition-colors hover:bg-stone-200/60"
              aria-label="Settings"
            >
              <FiSettings aria-hidden="true" size={18} />
            </Link>
            <button
              type="button"
              onClick={handleLogout}
              disabled={isLoggingOut}
              className="bg-stone-900 hover:bg-stone-800 transition-colors px-4 h-full flex items-center text-sm font-[500] text-[#f6f6f6] disabled:opacity-60"
            >
              {isLoggingOut ? "Logging out..." : "Log out"}
            </button>
          </div>
        </div>
      </header>
      {children}
    </div>
  );
}
