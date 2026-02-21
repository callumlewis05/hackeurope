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
  return (
    <main className="mx-auto w-full max-w-[1200px] py-12">
      <section className="space-y-8">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {statCards.map((card) => (
            <StatCard key={card.label} label={card.label} value={card.value} />
          ))}
        </div>

        <section>
          <h2 className="mb-3 text-md font-bold">
            Intervention History
          </h2>

          <div className="space-y-2">
            {interventionEvents.map((event, index) => (
              <article
                key={event.id}
                className={`grid w-full grid-cols-[minmax(0,40fr)_minmax(0,15fr)_minmax(0,15fr)_minmax(0,15fr)_minmax(0,15fr)] gap-x-2 px-4 h-14 items-center text-sm text-[#111] ${
                  index % 2 === 1 ? "bg-stone-50/60" : ""
                }`}
              >
                <span className={"min-w-0 truncate font-[450] text-[1rem]"}>{event.title}</span>
                <span className={"min-w-0 truncate"}>{event.date}</span>
                <span className={"min-w-0"}>
                  <span className={"inline-flex h-8 max-w-full w-fit items-center px-3.5 rounded bg-stone-100"}>
                    <span className="truncate">{event.category}</span>
                  </span>
                </span>
                <span
                  className={"min-w-0"}
                >
                  <span
                    className={`inline-flex h-8 max-w-full w-fit items-center px-3.5 rounded ${
                      event.decision === "Allowed"
                        ? "bg-green-100 text-green-800"
                        : "bg-red-100 text-red-800"
                    }`}
                  >
                    <span className="truncate">{event.decision}</span>
                  </span>
                </span>
                <span className={"min-w-0 w-full text-right text-lg font-[450] whitespace-nowrap"}>{event.amountEur} Eur</span>
              </article>
            ))}
          </div>
        </section>
      </section>
    </main>
  );
}
