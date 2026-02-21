"use client";

import { useMemo, useState } from "react";

type InterventionEvent = {
  id: string;
  title: string;
  category: string;
  decision: "Allowed" | "Blocked";
  date: string;
  amountEur: number;
};

type StatCardProps = {
  label: string;
  value: string;
};

const statCards: StatCardProps[] = [
  { label: "Money Saved", value: "500 Eur" },
  { label: "Interventions", value: "245" },
  { label: "Average Saved", value: "2.35 Eur" },
];

const interventionEvents: InterventionEvent[] = [
  {
    id: "evt-1",
    title: "Trip to Spain",
    category: "Travel",
    decision: "Allowed",
    date: "13 Jul",
    amountEur: 35,
  },
  {
    id: "evt-2",
    title: "Hotel Booking",
    category: "Travel",
    decision: "Allowed",
    date: "12 Jul",
    amountEur: 120,
  },
  {
    id: "evt-3",
    title: "Office Subscription",
    category: "Software",
    decision: "Blocked",
    date: "11 Jul",
    amountEur: 22,
  },
  {
    id: "evt-4",
    title: "Taxi Ride",
    category: "Transport",
    decision: "Allowed",
    date: "10 Jul",
    amountEur: 18,
  },
  {
    id: "evt-5",
    title: "Cloud Compute Invoice",
    category: "Infrastructure",
    decision: "Blocked",
    date: "09 Jul",
    amountEur: 260,
  },
  {
    id: "evt-6",
    title: "Client Dinner",
    category: "Meals",
    decision: "Allowed",
    date: "08 Jul",
    amountEur: 74,
  },
  {
    id: "evt-7",
    title: "Design Tool Renewal",
    category: "Software",
    decision: "Allowed",
    date: "07 Jul",
    amountEur: 36,
  },
  {
    id: "evt-8",
    title: "Airport Parking",
    category: "Transport",
    decision: "Blocked",
    date: "06 Jul",
    amountEur: 48,
  },
  {
    id: "evt-9",
    title: "Training Course",
    category: "Education",
    decision: "Allowed",
    date: "05 Jul",
    amountEur: 99,
  },
  {
    id: "evt-10",
    title: "Team Offsite Venue",
    category: "Operations",
    decision: "Blocked",
    date: "04 Jul",
    amountEur: 310,
  },
  {
    id: "evt-11",
    title: "Printer Supplies",
    category: "Office",
    decision: "Allowed",
    date: "03 Jul",
    amountEur: 27,
  },
  {
    id: "evt-12",
    title: "Domain Renewal",
    category: "Infrastructure",
    decision: "Allowed",
    date: "02 Jul",
    amountEur: 19,
  },
];

function StatCard({ label, value }: StatCardProps) {
  return (
    <article className="bg-stone-100 p-6">
      <p className="text-[0.95rem] font-[450] mb-6">{label}</p>
      <p className="mt-2 text-4xl font-normal tracking-tighter">{value}</p>
    </article>
  );
}

export default function DashboardPage() {
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const selectedEvent = useMemo(
    () =>
      selectedEventId
        ? interventionEvents.find((event) => event.id === selectedEventId) ?? null
        : null,
    [selectedEventId],
  );

  const handleEventClick = (eventId: string) => {
    setSelectedEventId((currentId) => (currentId === eventId ? null : eventId));
  };

  return (
    <main className="mx-auto w-full max-w-[1200px] py-20">
      <section className={`grid gap-4 ${selectedEvent ? "md:grid-cols-3" : "grid-cols-1"}`}>
        <div className={`space-y-8 ${selectedEvent ? "md:col-span-2" : ""}`}>
          <div className="font-spectral text-4xl -tracking-[0.2rem] mb-12">Welcome back!</div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {statCards.map((card) => (
              <StatCard key={card.label} label={card.label} value={card.value} />
            ))}
          </div>

          <section>
            <h2 className="mb-3 text-md text-lg font-medium">
              Intervention History
            </h2>

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
                  <th className="px-4 font-medium border-r border-stone-200">Category</th>
                  <th className="px-4 font-medium border-r border-stone-200">Decision</th>
                  <th className="px-4 font-medium text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {interventionEvents.map((event) => {
                  const isSelected = selectedEventId === event.id;

                  return (
                    <tr
                      key={event.id}
                      onClick={() => handleEventClick(event.id)}
                      className={`h-14 border-b border-stone-200 last:border-b-0 cursor-pointer ${
                        isSelected ? "bg-stone-100/80" : ""
                      }`}
                    >
                      <td className="px-4 min-w-0 truncate font-[450] tracking-tight border-r border-stone-200">
                        {event.title}
                      </td>
                      <td className="px-4 min-w-0 truncate tracking-tighter font-[450] border-r border-stone-200">
                        {event.date}
                      </td>
                      {/*<td className="px-4 min-w-0 border-r border-stone-200">*/}
                      {/*  <span className="inline-flex h-8 max-w-full font-[450] tracking-tighter w-fit items-center px-3 bg-stone-100">*/}
                      {/*    <span className="truncate">{event.category}</span>*/}
                      {/*  </span>*/}
                      {/*</td>*/}
                      <td className="px-4 min-w-0 truncate tracking-tighter font-[450] border-r border-stone-200">
                        {event.category}
                      </td>
                      <td className="px-4 min-w-0 border-r border-stone-200">
                        <span
                          className={`inline-flex h-8 max-w-full w-fit font-[550] tracking-tighter items-center px-3 ${
                            event.decision === "Allowed"
                              ? "bg-stone-100"
                              : "bg-[#FF4053] text-white"
                          }`}
                        >
                          <span className="truncate">{event.decision}</span>
                        </span>
                      </td>
                      <td className="px-4 min-w-0 w-full text-right font-[450] tracking-tighter whitespace-nowrap">
                        {event.amountEur} Eur
                      </td>
                    </tr>
                  );
                })}
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
                <dd className="font-medium text-[#111]">{selectedEvent.date}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Category</dt>
                <dd className="font-medium text-[#111]">{selectedEvent.category}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Decision</dt>
                <dd className="font-medium text-[#111]">{selectedEvent.decision}</dd>
              </div>
              <div>
                <dt className="text-stone-500">Amount</dt>
                <dd className="font-medium text-[#111]">{selectedEvent.amountEur} Eur</dd>
              </div>
            </dl>
          </aside>
        ) : null}
      </section>
    </main>
  );
}
