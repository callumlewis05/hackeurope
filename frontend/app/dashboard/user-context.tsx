"use client";

import { createContext, useContext } from "react";

import type { UserProfileResponse } from "@/lib/api-types";

interface DashboardUserContextValue {
  user: UserProfileResponse | null;
  isLoadingUser: boolean;
}

const DashboardUserContext = createContext<DashboardUserContextValue>({
  user: null,
  isLoadingUser: true,
});

interface DashboardUserProviderProps extends DashboardUserContextValue {
  children: React.ReactNode;
}

export function DashboardUserProvider({
  user,
  isLoadingUser,
  children,
}: DashboardUserProviderProps) {
  return (
    <DashboardUserContext.Provider value={{ user, isLoadingUser }}>
      {children}
    </DashboardUserContext.Provider>
  );
}

export function useDashboardUser() {
  return useContext(DashboardUserContext);
}

export function getUserDisplayName(user: UserProfileResponse | null) {
  const trimmedName = user?.name?.trim();
  if (trimmedName) {
    return trimmedName;
  }

  return "User";
}
