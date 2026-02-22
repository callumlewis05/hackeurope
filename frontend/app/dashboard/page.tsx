"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import type {
  InterventionListResponse,
  InterventionResponse,
  InterventionStatsResponse,
} from "@/lib/api-types";
import { getInterventionStats, listInterventions, toErrorMessage } from "@/lib/frontend-api";
import Image from "next/image";
import { getUserDisplayName, useDashboardUser } from "./user-context";

type StatCardProps = {
  label: string;
  value: string;
};

function formatCurrency(amount: number) {
  return `${new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount)} Eur`;
}

function formatShortDate(timestamp: string) {
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }

  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
  }).format(parsed);
}

function formatDateTime(timestamp: string) {
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }

  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function formatCount(value: number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

function toDecision(wasIntervened: boolean) {
  return wasIntervened ? "Blocked" : "Allowed";
}

function StatCard({ label, value }: StatCardProps) {
  return (
    <article className="bg-stone-100 p-6">
      <p className="text-[0.95rem] font-[450] mb-6">{label}</p>
      <div className={"flex items-end gap-2"}>
        <p className="mt-2 text-4xl font-normal tracking-tighter">{value}</p>
      </div>
    </article>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const { user } = useDashboardUser();
  const [interventions, setInterventions] = useState<InterventionResponse[]>([]);
  const [stats, setStats] = useState<InterventionStatsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    const loadDashboardData = async () => {
      try {
        const [statsResponse, interventionsResponse] = await Promise.all([
          getInterventionStats(),
          listInterventions({ limit: 50, offset: 0 }),
        ]);

        if (!isMounted) {
          return;
        }

        if (statsResponse.status === 401 || interventionsResponse.status === 401) {
          router.replace("/");
          return;
        }

        if (!statsResponse.ok) {
          setError(toErrorMessage(statsResponse.data, "Unable to load intervention stats."));
          setIsLoading(false);
          return;
        }

        if (!interventionsResponse.ok) {
          setError(toErrorMessage(interventionsResponse.data, "Unable to load interventions."));
          setIsLoading(false);
          return;
        }

        setStats((statsResponse.data as InterventionStatsResponse) ?? null);
        setInterventions(((interventionsResponse.data as InterventionListResponse) ?? { items: [] }).items);
        setError(null);
      } catch {
        if (!isMounted) {
          return;
        }

        setError("Unable to reach the server.");
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    void loadDashboardData();

    return () => {
      isMounted = false;
    };
  }, [router]);

  const totalMoneySaved = useMemo(
    () => stats?.total_money_saved ?? interventions.reduce((sum, item) => sum + item.money_saved, 0),
    [interventions, stats],
  );
  const totalInterventions = useMemo(
    () => stats?.total_interventions ?? interventions.filter((item) => item.was_intervened).length,
    [interventions, stats],
  );
  const totalComputeCost = useMemo(
    () => stats?.total_compute_cost ?? interventions.reduce((sum, item) => sum + item.compute_cost, 0),
    [interventions, stats],
  );
  const statCards: StatCardProps[] = [
    {
      label: "Total Money Saved",
      value: formatCurrency(totalMoneySaved),
    },
    { label: "Interventions", value: formatCount(totalInterventions) },
    { label: "Compute Cost", value: formatCurrency(totalComputeCost) },
  ];

  const selectedEvent = useMemo(
    () =>
      selectedEventId
        ? interventions.find((event) => event.id === selectedEventId) ?? null
        : null,
    [interventions, selectedEventId],
  );

  const handleEventClick = (eventId: string) => {
    setSelectedEventId((currentId) => (currentId === eventId ? null : eventId));
  };

  const welcomeTitle = user ? `Welcome back, ${getUserDisplayName(user)}!` : "Welcome back!";

  return (
    <main className="mx-auto w-full max-w-[1200px] py-20">
      <section className={`grid gap-4 ${selectedEvent ? "md:grid-cols-3" : "grid-cols-1"}`}>
        <div className={`space-y-8 ${selectedEvent ? "md:col-span-2" : ""}`}>
          <div className="font-spectral text-4xl -tracking-[0.2rem] mb-12">{welcomeTitle}</div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {statCards.map((card) => (
              <StatCard key={card.label} label={card.label} value={card.value} />
            ))}
          </div>

          <section>
            <h2 className="mb-3 text-md text-lg font-medium">
              Intervention History
            </h2>
            {error ? <p className="mb-3 text-sm text-red-600">{error}</p> : null}

            <table className="w-full table-fixed border border-stone-200 border-collapse text-sm text-[#111]">
              <colgroup>
                <col className="w-[60%]" />
                <col className="w-[15%]" />
                <col className="w-[15%]" />
                <col className="w-[15%]" />
                <col className="w-[15%]" />
              </colgroup>
              <thead>
                <tr className="h-12 border-b border-stone-200 text-left">
                  <th className="px-4 font-medium border-r border-stone-200">Title</th>
                  <th className="px-4 font-medium border-r border-stone-200">Date</th>
                  <th className="px-4 font-medium border-r border-stone-200">Domain</th>
                  <th className="px-4 font-medium border-r border-stone-200">Decision</th>
                  <th className="px-4 font-medium text-right">Money Saved</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr className="h-14 border-b border-stone-200">
                    <td colSpan={5} className="px-4 text-sm text-stone-500">
                      Loading interventions...
                    </td>
                  </tr>
                ) : null}
                {!isLoading && interventions.length === 0 ? (
                  <tr className="h-48 text-center font-[450] border-b border-stone-200">
                    <td colSpan={5} className="px-4 text-sm text-stone-400">
                      <Image src={"/icon-sad.svg"} alt={"Sad icon"} width={38} height={38} className="mx-auto mb-2" />
                      No interventions found.
                    </td>
                  </tr>
                ) : null}
                {!isLoading
                  ? interventions.map((event) => {
                    const isSelected = selectedEventId === event.id;
                    const decision = toDecision(event.was_intervened);

                    return (
                      <tr
                        key={event.id}
                        onClick={() => handleEventClick(event.id)}
                        className={`h-14 border-b border-stone-200 last:border-b-0 cursor-pointer ${
                          isSelected ? "bg-stone-100/80" : ""
                        }`}
                      >
                        <td className="px-4 min-w-0 truncate font-[450] tracking-tight border-r border-stone-200">
                          {event.title || "Untitled"}
                        </td>
                        <td className="px-4 min-w-0 truncate tracking-tighter font-[450] border-r border-stone-200">
                          {formatShortDate(event.analyzed_at)}
                        </td>
                        <td className="px-4 min-w-0 truncate tracking-tighter font-[450] border-r border-stone-200">
                          {event.domain}
                        </td>
                        <td className="px-4 min-w-0 border-r border-stone-200">
                          <span
                            className={`inline-flex h-8 max-w-full w-fit font-[550] tracking-tighter items-center px-3 ${
                              decision === "Allowed"
                                ? "bg-stone-100"
                                : "bg-[#FF4053] text-white"
                            }`}
                          >
                            <span className="truncate">{decision}</span>
                          </span>
                        </td>
                        <td className="px-4 min-w-0 w-full text-right font-[450] tracking-tighter whitespace-nowrap">
                          {formatCurrency(event.money_saved)}
                        </td>
                      </tr>
                    );
                  })
                  : null}
              </tbody>
            </table>
          </section>
        </div>

        {selectedEvent ? (
          <aside className="sticky top-5 border border-stone-200 p-5 md:col-span-1 self-start">
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-wide text-stone-500">
                  Intervention
                </p>
                <h3 className="text-lg font-medium">{selectedEvent.title}</h3>
              </div>
              <button
                type="button"
                onClick={() => setSelectedEventId(null)}
                className="text-sm text-stone-600 hover:text-stone-900"
              >
                Close
              </button>
            </div>

            <dl className="space-y-4 text-sm">
              <div>
                <dt className="text-stone-500">ID</dt>
                <dd className="font-medium text-[#111]">{selectedEvent.id}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Date</dt>
                <dd className="font-medium text-[#111]">{formatDateTime(selectedEvent.analyzed_at)}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Domain</dt>
                <dd className="font-medium text-[#111]">{selectedEvent.domain}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Intent Type</dt>
                <dd className="font-medium text-[#111]">{selectedEvent.intent_type}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Decision</dt>
                <dd className="font-medium text-[#111]">{toDecision(selectedEvent.was_intervened)}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Money Saved</dt>
                <dd className="font-medium text-[#111]">{formatCurrency(selectedEvent.money_saved)}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Compute Cost</dt>
                <dd className="font-medium text-[#111]">{formatCurrency(selectedEvent.compute_cost)}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Platform Fee</dt>
                <dd className="font-medium text-[#111]">{formatCurrency(selectedEvent.platform_fee)}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Risk Factors</dt>
                <dd className="font-medium text-[#111]">
                  {selectedEvent.risk_factors.length > 0 ? selectedEvent.risk_factors.join(", ") : "None"}
                </dd>
              </div>
              <div>
                <dt className="text-stone-500">Intervention Message</dt>
                <dd className="font-medium text-[#111]">
                  {selectedEvent.intervention_message || "No intervention message."}
                </dd>
              </div>
            </dl>
          </aside>
        ) : null}
      </section>
    </main>
  );
}
