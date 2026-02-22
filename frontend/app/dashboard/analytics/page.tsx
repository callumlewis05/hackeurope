"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import type {
  InterventionCompactCountResponse,
  InterventionListResponse,
  InterventionResponse,
} from "@/lib/api-types";
import {
  getInterventionCategories,
  getInterventionMistakeTypes,
  listInterventions,
  toErrorMessage,
} from "@/lib/frontend-api";
import { useDashboardUser } from "../user-context";
import { ApexChart } from "./apex-chart";

type TimePeriod = "week" | "month" | "all";
type BucketGranularity = "day" | "week" | "month";

interface PeriodOption {
  value: TimePeriod;
  label: string;
  days: number | null;
}

interface CategoryRow {
  category: string;
  count: number;
}

interface TrendRow {
  key: string;
  label: string;
  moneySaved: number;
  platformFee: number;
  netValue: number;
  interventionRate: number;
}

interface EnrichedIntervention extends InterventionResponse {
  analyzedTimestamp: number;
}

const PERIOD_OPTIONS: PeriodOption[] = [
  { value: "week", label: "Week", days: 7 },
  { value: "month", label: "Month", days: 30 },
  { value: "all", label: "All", days: null },
];

const ACCENT_COLOR = "#FF4053";

function toTitleCase(value: string) {
  return value
    .trim()
    .replace(/[_-]+/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function sanitizeLabel(value: string) {
  const cleaned = value.replace(/\s+/g, " ").trim();
  if (!cleaned) {
    return "";
  }
  return toTitleCase(cleaned);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getLookbackDays(period: TimePeriod): number | undefined {
  if (period === "week") {
    return 7;
  }
  if (period === "month") {
    return 30;
  }
  return undefined;
}

function parseCompactCountPayload(payload: unknown): CategoryRow[] {
  let source = payload;

  if (typeof source === "string") {
    try {
      source = JSON.parse(source) as unknown;
    } catch {
      return [];
    }
  }

  if (!Array.isArray(source)) {
    return [];
  }

  const aggregate = new Map<string, number>();

  for (const entry of source) {
    if (!isRecord(entry)) {
      continue;
    }

    for (const [rawLabel, rawCount] of Object.entries(entry)) {
      const category = sanitizeLabel(rawLabel);
      const count = typeof rawCount === "number" ? rawCount : Number(rawCount);

      if (!category || !Number.isFinite(count)) {
        continue;
      }

      aggregate.set(category, (aggregate.get(category) ?? 0) + count);
    }
  }

  return [...aggregate.entries()]
    .map(([category, count]) => ({
      category,
      count,
    }))
    .sort((rowA, rowB) => rowB.count - rowA.count);
}

function formatCurrency(amount: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

function formatCompactCurrency(amount: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "EUR",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(amount);
}

function formatCount(value: number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

function formatPercentage(value: number) {
  return `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(value)}%`;
}

function getPeriodStart(period: TimePeriod, now = Date.now()) {
  const option = PERIOD_OPTIONS.find((item) => item.value === period);
  if (!option || option.days === null) {
    return null;
  }
  return now - option.days * 24 * 60 * 60 * 1000;
}

function filterByPeriod(items: EnrichedIntervention[], period: TimePeriod) {
  const start = getPeriodStart(period);
  if (start === null) {
    return items;
  }
  return items.filter((item) => item.analyzedTimestamp >= start);
}

function toDateParts(timestamp: number) {
  const date = new Date(timestamp);
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return { year, month, day };
}

function getWeekStart(timestamp: number) {
  const date = new Date(timestamp);
  const day = date.getDay();
  const diffToMonday = day === 0 ? -6 : 1 - day;
  date.setDate(date.getDate() + diffToMonday);
  date.setHours(0, 0, 0, 0);
  return date;
}

function getBucketGranularity(period: TimePeriod): BucketGranularity {
  if (period === "all") {
    return "month";
  }

  if (period === "month") {
    return "week";
  }

  return "day";
}

function getBucketIdentity(timestamp: number, granularity: BucketGranularity) {
  const date = new Date(timestamp);
  date.setHours(0, 0, 0, 0);

  if (granularity === "week") {
    const weekStart = getWeekStart(timestamp);
    const { year, month, day } = toDateParts(weekStart.getTime());
    return {
      key: `w-${year}-${month}-${day}`,
      startTimestamp: weekStart.getTime(),
    };
  }

  if (granularity === "month") {
    const monthDate = new Date(date.getFullYear(), date.getMonth(), 1);
    const { year, month } = toDateParts(monthDate.getTime());
    return {
      key: `m-${year}-${month}`,
      startTimestamp: monthDate.getTime(),
    };
  }

  const { year, month, day } = toDateParts(date.getTime());
  return {
    key: `d-${year}-${month}-${day}`,
    startTimestamp: date.getTime(),
  };
}

function formatBucketLabel(timestamp: number, granularity: BucketGranularity) {
  const date = new Date(timestamp);

  if (granularity === "month") {
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      year: "numeric",
    }).format(date);
  }

  if (granularity === "week") {
    const endDate = new Date(timestamp);
    endDate.setDate(endDate.getDate() + 6);
    return `${new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
    }).format(date)}-${new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
    }).format(endDate)}`;
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  }).format(date);
}

function buildTrendRows(items: EnrichedIntervention[], period: TimePeriod): TrendRow[] {
  const granularity = getBucketGranularity(period);
  const aggregate = new Map<
    string,
    {
      startTimestamp: number;
      analyses: number;
      interventions: number;
      moneySaved: number;
      platformFee: number;
    }
  >();

  for (const item of items) {
    const identity = getBucketIdentity(item.analyzedTimestamp, granularity);
    const current = aggregate.get(identity.key) ?? {
      startTimestamp: identity.startTimestamp,
      analyses: 0,
      interventions: 0,
      moneySaved: 0,
      platformFee: 0,
    };

    current.analyses += 1;
    if (item.was_intervened) {
      current.interventions += 1;
    }
    current.moneySaved += item.money_saved;
    current.platformFee += item.platform_fee;
    aggregate.set(identity.key, current);
  }

  return [...aggregate.entries()]
    .sort((entryA, entryB) => entryA[1].startTimestamp - entryB[1].startTimestamp)
    .map(([key, value]) => {
      const interventionRate = value.analyses > 0 ? (value.interventions / value.analyses) * 100 : 0;
      const netValue = value.moneySaved - value.platformFee;
      return {
        key,
        label: formatBucketLabel(value.startTimestamp, granularity),
        moneySaved: value.moneySaved,
        platformFee: value.platformFee,
        netValue,
        interventionRate,
      };
    });
}

function PeriodSelector({
  period,
  onChange,
}: {
  period: TimePeriod;
  onChange: (period: TimePeriod) => void;
}) {
  return (
    <div className="inline-flex flex-wrap items-center gap-2   bg-stone-100/75">
      {PERIOD_OPTIONS.map((option) => {
        const isActive = option.value === period;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={` px-3 py-2 text-xs font-semibold cursor-pointer transition-colors ${
              isActive
                ? "bg-stone-900 text-white"
                : "text-stone-600 hover:bg-stone-100 hover:text-stone-900"
            }`}
            aria-pressed={isActive}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function EmptyChart({ label }: { label: string }) {
  return (
    <div className="flex h-[360px] items-center justify-center border border-dashed border-stone-300 bg-stone-50 text-sm text-stone-400">
      {label}
    </div>
  );
}

export default function DashboardAnalyticsPage() {
  const router = useRouter();
  useDashboardUser();

  const [interventions, setInterventions] = useState<InterventionResponse[]>([]);
  const [mistakeTypeRows, setMistakeTypeRows] = useState<CategoryRow[]>([]);
  const [categoryRows, setCategoryRows] = useState<CategoryRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMistakes, setIsLoadingMistakes] = useState(true);
  const [isLoadingCategories, setIsLoadingCategories] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [overviewPeriod, setOverviewPeriod] = useState<TimePeriod>("month");
  const [mistakesPeriod, setMistakesPeriod] = useState<TimePeriod>("month");
  const [moneyPeriod, setMoneyPeriod] = useState<TimePeriod>("month");
  const [trendPeriod, setTrendPeriod] = useState<TimePeriod>("month");

  useEffect(() => {
    let isMounted = true;

    const loadInterventions = async () => {
      setIsLoading(true);
      setError(null);

      const allItems: InterventionResponse[] = [];
      const limit = 200;
      let offset = 0;
      let total = Number.POSITIVE_INFINITY;

      try {
        while (offset < total) {
          const response = await listInterventions({ limit, offset });

          if (!isMounted) {
            return;
          }

          if (response.status === 401) {
            router.replace("/");
            return;
          }

          if (!response.ok) {
            setError(toErrorMessage(response.data, "Unable to load analytics data."));
            setIsLoading(false);
            return;
          }

          const payload = (response.data as InterventionListResponse) ?? {
            items: [],
            total: 0,
            limit,
            offset,
          };
          const items = payload.items ?? [];

          allItems.push(...items);
          total = Number.isFinite(payload.total) ? payload.total : allItems.length;

          if (items.length < limit || items.length === 0) {
            break;
          }

          offset += items.length;
        }

        if (!isMounted) {
          return;
        }

        setInterventions(allItems);
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

    void loadInterventions();

    return () => {
      isMounted = false;
    };
  }, [router]);

  useEffect(() => {
    let isMounted = true;

    const loadMistakeTypeCounts = async () => {
      setIsLoadingMistakes(true);

      try {
        const lookbackDays = getLookbackDays(mistakesPeriod);
        const response = await getInterventionMistakeTypes(
          typeof lookbackDays === "number" ? { lookback_days: lookbackDays } : {},
        );

        if (!isMounted) {
          return;
        }

        if (response.status === 401) {
          router.replace("/");
          return;
        }

        if (!response.ok) {
          setMistakeTypeRows([]);
          setError((current) =>
            current ?? toErrorMessage(response.data, "Unable to load mistake-type counts."),
          );
          return;
        }

        const payload = response.data as InterventionCompactCountResponse | string | null;
        setMistakeTypeRows(parseCompactCountPayload(payload));
      } catch {
        if (!isMounted) {
          return;
        }
        setMistakeTypeRows([]);
        setError((current) => current ?? "Unable to reach the server.");
      } finally {
        if (isMounted) {
          setIsLoadingMistakes(false);
        }
      }
    };

    void loadMistakeTypeCounts();

    return () => {
      isMounted = false;
    };
  }, [mistakesPeriod, router]);

  useEffect(() => {
    let isMounted = true;

    const loadCategoryCounts = async () => {
      setIsLoadingCategories(true);

      try {
        const lookbackDays = getLookbackDays(moneyPeriod);
        const response = await getInterventionCategories(
          typeof lookbackDays === "number" ? { lookback_days: lookbackDays } : {},
        );

        if (!isMounted) {
          return;
        }

        if (response.status === 401) {
          router.replace("/");
          return;
        }

        if (!response.ok) {
          setCategoryRows([]);
          setError((current) =>
            current ?? toErrorMessage(response.data, "Unable to load category counts."),
          );
          return;
        }

        const payload = response.data as InterventionCompactCountResponse | string | null;
        setCategoryRows(parseCompactCountPayload(payload));
      } catch {
        if (!isMounted) {
          return;
        }
        setCategoryRows([]);
        setError((current) => current ?? "Unable to reach the server.");
      } finally {
        if (isMounted) {
          setIsLoadingCategories(false);
        }
      }
    };

    void loadCategoryCounts();

    return () => {
      isMounted = false;
    };
  }, [moneyPeriod, router]);

  const enrichedInterventions = useMemo<EnrichedIntervention[]>(() => {
    return interventions.flatMap((item) => {
      const analyzedTimestamp = Date.parse(item.analyzed_at);
      if (Number.isNaN(analyzedTimestamp)) {
        return [];
      }

      return [{ ...item, analyzedTimestamp }];
    });
  }, [interventions]);

  const overviewData = useMemo(
    () => filterByPeriod(enrichedInterventions, overviewPeriod),
    [enrichedInterventions, overviewPeriod],
  );
  const trendData = useMemo(
    () => filterByPeriod(enrichedInterventions, trendPeriod),
    [enrichedInterventions, trendPeriod],
  );

  const overviewTotals = useMemo(() => {
    const analyses = overviewData.length;
    const interventionsCount = overviewData.filter((item) => item.was_intervened).length;
    const moneySaved = overviewData.reduce((sum, item) => sum + item.money_saved, 0);
    const platformFees = overviewData.reduce((sum, item) => sum + item.platform_fee, 0);
    const netValue = moneySaved - platformFees;
    const interventionRate = analyses > 0 ? (interventionsCount / analyses) * 100 : 0;
    const avgSavedPerIntervention = interventionsCount > 0 ? moneySaved / interventionsCount : 0;
    const efficiencyRatio = platformFees > 0 ? moneySaved / platformFees : 0;

    return {
      analyses,
      interventionsCount,
      moneySaved,
      platformFees,
      netValue,
      interventionRate,
      avgSavedPerIntervention,
      efficiencyRatio,
    };
  }, [overviewData]);

  const categoryRowsForMistakes = useMemo(() => {
    return mistakeTypeRows.slice(0, 8);
  }, [mistakeTypeRows]);

  const categoryRowsForMoney = useMemo(() => {
    return categoryRows.slice(0, 8);
  }, [categoryRows]);

  const trendRows = useMemo(() => buildTrendRows(trendData, trendPeriod), [trendData, trendPeriod]);

  const mistakesChartOptions = useMemo<Record<string, unknown>>(
    () => ({
      chart: {
        type: "bar",
        toolbar: { show: false },
        animations: { easing: "easeinout", speed: 500 },
        fontFamily: "var(--font-inter), sans-serif",
      },
      colors: [ACCENT_COLOR],
      grid: {
        borderColor: "#ece7e1",
        strokeDashArray: 4,
      },
      dataLabels: { enabled: false },
      plotOptions: {
        bar: {
          borderRadius: 8,
          columnWidth: "55%",
          distributed: true,
        },
      },
      legend: { show: false },
      xaxis: {
        categories: categoryRowsForMistakes.map((row) => row.category),
        labels: {
          rotate: -25,
          trim: true,
          style: { fontSize: "12px", colors: "#57534e" },
        },
      },
      yaxis: {
        title: {
          text: "Count",
          style: { color: "#57534e", fontSize: "12px", fontWeight: 600 },
        },
        labels: {
          formatter: (value: number) => Math.round(value).toString(),
          style: { colors: "#57534e" },
        },
      },
      tooltip: {
        y: {
          formatter: (value: number) => Math.round(value).toString(),
        },
      },
    }),
    [categoryRowsForMistakes],
  );

  const mistakesChartSeries = useMemo(
    () => [
      {
        name: "Mistake Count",
        data: categoryRowsForMistakes.map((row) => Math.round(row.count)),
      },
    ],
    [categoryRowsForMistakes],
  );

  const moneyChartOptions = useMemo<Record<string, unknown>>(
    () => ({
      chart: {
        type: "bar",
        toolbar: { show: false },
        animations: { easing: "easeinout", speed: 500 },
        fontFamily: "var(--font-inter), sans-serif",
      },
      colors: [ACCENT_COLOR],
      grid: {
        borderColor: "#ece7e1",
        strokeDashArray: 4,
      },
      dataLabels: { enabled: false },
      plotOptions: {
        bar: {
          borderRadius: 8,
          columnWidth: "55%",
          distributed: true,
        },
      },
      legend: { show: false },
      xaxis: {
        categories: categoryRowsForMoney.map((row) => row.category),
        labels: {
          rotate: -25,
          trim: true,
          style: { colors: "#57534e", fontSize: "12px" },
        },
      },
      yaxis: {
        title: {
          text: "Count",
          style: { color: "#57534e", fontSize: "12px", fontWeight: 600 },
        },
        labels: {
          formatter: (value: number) => Math.round(value).toString(),
          style: { colors: "#57534e" },
        },
      },
      tooltip: {
        y: {
          formatter: (value: number) => Math.round(value).toString(),
        },
      },
    }),
    [categoryRowsForMoney],
  );

  const moneyChartSeries = useMemo(
    () => [
      {
        name: "Category Count",
        data: categoryRowsForMoney.map((row) => Math.round(row.count)),
      },
    ],
    [categoryRowsForMoney],
  );

  const trendChartOptions = useMemo<Record<string, unknown>>(
    () => ({
      chart: {
        type: "line",
        toolbar: { show: false },
        animations: { easing: "easeinout", speed: 550 },
        fontFamily: "var(--font-inter), sans-serif",
      },
      colors: [ACCENT_COLOR, "#f97316"],
      stroke: {
        curve: "smooth",
        width: [3, 2],
      },
      fill: {
        type: ["gradient", "solid"],
        gradient: {
          shadeIntensity: 0.7,
          opacityFrom: 0.28,
          opacityTo: 0.03,
          stops: [0, 95, 100],
        },
      },
      markers: {
        size: [4, 3],
        hover: {
          sizeOffset: 2,
        },
      },
      grid: {
        borderColor: "#ece7e1",
        strokeDashArray: 4,
      },
      dataLabels: { enabled: false },
      xaxis: {
        categories: trendRows.map((row) => row.label),
        labels: {
          trim: true,
          style: { colors: "#57534e", fontSize: "12px" },
        },
      },
      yaxis: [
        {
          title: {
            text: "Value (EUR)",
            style: { color: "#57534e", fontSize: "12px", fontWeight: 600 },
          },
          labels: {
            formatter: (value: number) => formatCompactCurrency(value),
            style: { colors: "#57534e" },
          },
        },
        {
          opposite: true,
          title: {
            text: "Intervention Rate",
            style: { color: "#57534e", fontSize: "12px", fontWeight: 600 },
          },
          labels: {
            formatter: (value: number) => `${value.toFixed(0)}%`,
            style: { colors: "#57534e" },
          },
          min: 0,
          max: 100,
        },
      ],
      tooltip: {
        shared: true,
        intersect: false,
        y: [
          { formatter: (value: number) => formatCurrency(value) },
          { formatter: (value: number) => `${value.toFixed(1)}%` },
        ],
      },
      legend: {
        position: "top",
        horizontalAlign: "left",
      },
    }),
    [trendRows],
  );

  const trendChartSeries = useMemo(
    () => [
      {
        name: "Money Saved",
        type: "area" as const,
        data: trendRows.map((row) => Number(row.moneySaved.toFixed(2))),
      },
      {
        name: "Intervention Rate",
        type: "line" as const,
        data: trendRows.map((row) => Number(row.interventionRate.toFixed(1))),
      },
    ],
    [trendRows],
  );

  const topMistakeCategory = categoryRowsForMistakes[0] ?? null;
  const topSavingsCategory = categoryRowsForMoney[0] ?? null;
  const strongestTrendPoint = trendRows.reduce<TrendRow | null>((current, row) => {
    if (!current) {
      return row;
    }
    return row.netValue > current.netValue ? row : current;
  }, null);

  return (
    <main className="mx-auto w-full max-w-[1200px] px-4 pb-14 pt-10">
      <h1 className="text-4xl tracking-tighter text-[#111]">
        Analytics
      </h1>
      <section className="">
        <div className="mb-4 flex flex-col gap-4 md:flex-row md:items-end md:justify-end">
          <PeriodSelector period={overviewPeriod} onChange={setOverviewPeriod} />
        </div>

        {error ? (
          <p className="mb-5 rounded-xl border border-[#ffccd2] bg-[#fff4f5] px-4 py-3 text-sm text-[#b42333]">
            {error}
          </p>
        ) : null}

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <article className="bg-stone-100/75 p-5">
            <p className="text-xs font-[450] uppercase tracking-tight mb-6">Saved so far</p>
            <p className="mt-2 text-3xl font-[450] tracking-tighter">
              {formatCurrency(overviewTotals.netValue)}
            </p>
          </article>

          <article className="bg-stone-100/75 p-5">
            <p className="text-xs font-[450] uppercase tracking-tight mb-6">Interventions</p>
            <p className="mt-2 text-3xl font-[450] tracking-tighter">
              {formatCount(overviewTotals.interventionsCount)}
            </p>
          </article>

          <article className="bg-stone-100/75 p-5">
            <p className="text-xs font-[450] uppercase tracking-tight mb-6">Avg saved / intervention</p>
            <p className="mt-2 text-3xl font-[450] tracking-tighter">
              {formatCurrency(overviewTotals.avgSavedPerIntervention)}
            </p>
          </article>
        </div>
      </section>

      <section className="mt-8 grid gap-4 xl:grid-cols-2">
        <article className="border border-stone-200 bg-white p-5 md:p-6">
          <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-xl font-[450] tracking-tighter text-[#111]">Mistake count by type</h2>
            </div>
            <PeriodSelector period={mistakesPeriod} onChange={setMistakesPeriod} />
          </div>

          {isLoadingMistakes ? <EmptyChart label="Loading mistake type counts..." /> : null}
          {!isLoadingMistakes && categoryRowsForMistakes.length === 0 ? (
            <EmptyChart label="No prevented mistakes in this period." />
          ) : null}
          {!isLoadingMistakes && categoryRowsForMistakes.length > 0 ? (
            <ApexChart options={mistakesChartOptions} series={mistakesChartSeries} height={360} />
          ) : null}
        </article>

        <article className="border border-stone-200 bg-white p-5  md:p-6">
          <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-xl font-[450] tracking-tighter">Category count</h2>
            </div>
            <PeriodSelector period={moneyPeriod} onChange={setMoneyPeriod} />
          </div>

          {isLoadingCategories ? <EmptyChart label="Loading category counts..." /> : null}
          {!isLoadingCategories && categoryRowsForMoney.length === 0 ? (
            <EmptyChart label="No category counts in this period." />
          ) : null}
          {!isLoadingCategories && categoryRowsForMoney.length > 0 ? (
            <ApexChart options={moneyChartOptions} series={moneyChartSeries} height={360} />
          ) : null}
        </article>
      </section>

      <section className="mt-4 border border-stone-200 bg-white p-5 md:p-6">
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-xl tracking-tighter font-[450]">Savings trend over time</h2>
          </div>
          <PeriodSelector period={trendPeriod} onChange={setTrendPeriod} />
        </div>

        {isLoading ? <EmptyChart label="Loading time trends..." /> : null}
        {!isLoading && trendRows.length === 0 ? (
          <EmptyChart label="Not enough data to render the trend for this period." />
        ) : null}
        {!isLoading && trendRows.length > 0 ? (
          <ApexChart options={trendChartOptions} series={trendChartSeries} height={380} />
        ) : null}
      </section>

      <section className="mt-4 grid gap-4 xl:grid-cols-3">
        <article className=" border border-stone-200 bg-white p-5">
          <p className="text-xs font-[450] uppercase tracking-tighter text-stone-500 mb-8">Top mistake type</p>
          <p className="mt-2 text-xl font-[450] tracking-tighter">
            {topMistakeCategory ? topMistakeCategory.category : "No data"}
          </p>
          <p className="mt-2 text-sm text-stone-500">
            {topMistakeCategory
              ? `${formatCount(topMistakeCategory.count)} occurrences in the selected period.`
              : "No interventions were recorded for this period."}
          </p>
        </article>

        <article className=" border border-stone-200 bg-white p-5">
          <p className="text-xs font-[450] uppercase tracking-tighter text-stone-500 mb-8">Top category</p>
          <p className="mt-2 text-xl font-[450] tracking-tighter">
            {topSavingsCategory ? topSavingsCategory.category : "No data"}
          </p>
          <p className="mt-2 text-sm text-stone-500">
            {topSavingsCategory
              ? `${formatCount(topSavingsCategory.count)} occurrences in the selected period.`
              : "No category counts were found for this period."}
          </p>
        </article>

        <article className=" border border-stone-200 bg-white p-5">
          <p className="text-xs font-[450] uppercase tracking-tighter text-stone-500 mb-8">Best trend window</p>
          <p className="mt-2 text-xl font-[450] tracking-tighter">
            {strongestTrendPoint ? strongestTrendPoint.label : "No data"}
          </p>
          <p className="mt-2 text-sm text-stone-500">
            {strongestTrendPoint
              ? `${formatCurrency(strongestTrendPoint.netValue)} net value with ${formatPercentage(strongestTrendPoint.interventionRate)} intervention rate.`
              : "No trend point available for the selected period."}
          </p>
        </article>
      </section>

    </main>
  );
}
