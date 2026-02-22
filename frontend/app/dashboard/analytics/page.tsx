"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import type {
  InterventionListResponse,
  InterventionResponse,
} from "@/lib/api-types";
import { listInterventions, toErrorMessage } from "@/lib/frontend-api";
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
  analyses: number;
  mistakes: number;
  moneySaved: number;
  interventionRate: number;
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
  derivedCategory: string;
}

const PERIOD_OPTIONS: PeriodOption[] = [
  { value: "week", label: "Week", days: 7 },
  { value: "month", label: "Month", days: 30 },
  { value: "all", label: "All", days: null },
];

const CATEGORY_KEYS = new Set([
  "category",
  "purchase_category",
  "product_category",
  "item_category",
  "intent_category",
  "subcategory",
]);

const ACCENT_COLOR = "#FF4053";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toTitleCase(value: string) {
  return value
    .trim()
    .replace(/[_-]+/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function sanitizeCategory(value: string) {
  const cleaned = value.replace(/\s+/g, " ").trim();
  if (!cleaned) {
    return "";
  }
  return toTitleCase(cleaned);
}

function extractCategoryFromIntentData(value: unknown, depth = 0): string | null {
  if (depth > 4 || !value) {
    return null;
  }

  if (Array.isArray(value)) {
    for (const nestedValue of value) {
      const nestedCategory = extractCategoryFromIntentData(nestedValue, depth + 1);
      if (nestedCategory) {
        return nestedCategory;
      }
    }
    return null;
  }

  if (!isRecord(value)) {
    return null;
  }

  for (const [rawKey, nestedValue] of Object.entries(value)) {
    const key = rawKey.toLowerCase();

    if (CATEGORY_KEYS.has(key) && typeof nestedValue === "string") {
      const normalized = sanitizeCategory(nestedValue);
      if (normalized) {
        return normalized;
      }
    }

    const nestedCategory = extractCategoryFromIntentData(nestedValue, depth + 1);
    if (nestedCategory) {
      return nestedCategory;
    }
  }

  return null;
}

function inferCategoryFromRiskFactors(riskFactors: string[]) {
  const normalized = riskFactors.join(" ").toLowerCase();

  if (normalized.includes("subscription")) return "Subscriptions";
  if (normalized.includes("impulse")) return "Impulse Spending";
  if (normalized.includes("urgent")) return "Urgent Purchases";
  if (normalized.includes("duplicate")) return "Duplicate Orders";
  if (normalized.includes("upsell")) return "Upsell Pressure";
  if (normalized.includes("finance")) return "Financial Risk";

  return null;
}

function inferCategoryFromDomain(domain: string) {
  const normalized = domain.toLowerCase();

  if (/(amazon|ebay|etsy|walmart|target|aliexpress)/.test(normalized)) return "Shopping";
  if (/(booking|airbnb|expedia|trip|flight|hotel)/.test(normalized)) return "Travel";
  if (/(ubereats|doordash|grubhub|deliveroo)/.test(normalized)) return "Food Delivery";
  if (/(uber|lyft|taxi|train|rail)/.test(normalized)) return "Transport";
  if (/(apple|google|microsoft|adobe|spotify|netflix)/.test(normalized)) return "Digital Services";

  return "Uncategorized";
}

function deriveCategory(intervention: InterventionResponse) {
  const intentCategory = extractCategoryFromIntentData(intervention.intent_data);
  if (intentCategory) {
    return intentCategory;
  }

  const riskCategory = inferCategoryFromRiskFactors(intervention.risk_factors ?? []);
  if (riskCategory) {
    return riskCategory;
  }

  return inferCategoryFromDomain(intervention.domain);
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

function buildCategoryRows(items: EnrichedIntervention[]): CategoryRow[] {
  const aggregate = new Map<string, { analyses: number; mistakes: number; moneySaved: number }>();

  for (const item of items) {
    const key = item.derivedCategory;
    const current = aggregate.get(key) ?? { analyses: 0, mistakes: 0, moneySaved: 0 };
    current.analyses += 1;
    current.moneySaved += item.money_saved;
    if (item.was_intervened) {
      current.mistakes += 1;
    }
    aggregate.set(key, current);
  }

  return [...aggregate.entries()].map(([category, value]) => {
    const rate = value.analyses > 0 ? (value.mistakes / value.analyses) * 100 : 0;
    return {
      category,
      analyses: value.analyses,
      mistakes: value.mistakes,
      moneySaved: value.moneySaved,
      interventionRate: rate,
    };
  });
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
  const [isLoading, setIsLoading] = useState(true);
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

  const enrichedInterventions = useMemo<EnrichedIntervention[]>(() => {
    return interventions.flatMap((item) => {
      const analyzedTimestamp = Date.parse(item.analyzed_at);
      if (Number.isNaN(analyzedTimestamp)) {
        return [];
      }

      return [{ ...item, analyzedTimestamp, derivedCategory: deriveCategory(item) }];
    });
  }, [interventions]);

  const overviewData = useMemo(
    () => filterByPeriod(enrichedInterventions, overviewPeriod),
    [enrichedInterventions, overviewPeriod],
  );
  const mistakesData = useMemo(
    () => filterByPeriod(enrichedInterventions, mistakesPeriod),
    [enrichedInterventions, mistakesPeriod],
  );
  const moneyData = useMemo(
    () => filterByPeriod(enrichedInterventions, moneyPeriod),
    [enrichedInterventions, moneyPeriod],
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
    return buildCategoryRows(mistakesData)
      .filter((row) => row.mistakes > 0)
      .sort((rowA, rowB) => rowB.mistakes - rowA.mistakes)
      .slice(0, 8);
  }, [mistakesData]);

  const categoryRowsForMoney = useMemo(() => {
    return buildCategoryRows(moneyData)
      .filter((row) => row.moneySaved > 0)
      .sort((rowA, rowB) => rowB.moneySaved - rowA.moneySaved)
      .slice(0, 8);
  }, [moneyData]);

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
          text: "Mistakes Prevented",
          style: { color: "#57534e", fontSize: "12px", fontWeight: 600 },
        },
        labels: {
          formatter: (value: number) => Math.round(value).toString(),
          style: { colors: "#57534e" },
        },
      },
      tooltip: {
        y: {
          formatter: (value: number) => `${Math.round(value)} prevented`,
        },
      },
    }),
    [categoryRowsForMistakes],
  );

  const mistakesChartSeries = useMemo(
    () => [
      {
        name: "Mistakes Prevented",
        data: categoryRowsForMistakes.map((row) => row.mistakes),
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
          horizontal: true,
          barHeight: "58%",
        },
      },
      legend: { show: false },
      xaxis: {
        labels: {
          formatter: (value: number) => formatCompactCurrency(value),
          style: { colors: "#57534e" },
        },
      },
      yaxis: {
        categories: categoryRowsForMoney.map((row) => row.category),
        labels: {
          style: { colors: "#57534e", fontSize: "12px" },
        },
      },
      tooltip: {
        y: {
          formatter: (value: number) => formatCurrency(value),
        },
      },
    }),
    [categoryRowsForMoney],
  );

  const moneyChartSeries = useMemo(
    () => [
      {
        name: "Money Saved",
        data: categoryRowsForMoney.map((row) => Number(row.moneySaved.toFixed(2))),
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
      colors: [ACCENT_COLOR, "#111827", "#f97316"],
      stroke: {
        curve: "smooth",
        width: [3, 3, 2],
      },
      fill: {
        type: ["gradient", "solid", "solid"],
        gradient: {
          shadeIntensity: 0.7,
          opacityFrom: 0.28,
          opacityTo: 0.03,
          stops: [0, 95, 100],
        },
      },
      markers: {
        size: [4, 4, 3],
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
        name: "Net Value",
        type: "line" as const,
        data: trendRows.map((row) => Number(row.netValue.toFixed(2))),
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
    <main className="mx-auto w-full max-w-[1400px] px-4 pb-14 pt-10">
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

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <article className="bg-stone-100/75 p-5">
            <p className="text-xs font-[450] uppercase tracking-tight mb-6">Net value</p>
            <p className="mt-2 text-3xl font-[450] tracking-tighter">
              {formatCurrency(overviewTotals.netValue)}
            </p>
            <p className="mt-1 text-sm text-stone-400 font-[450] leading-tight">
              Savings minus platform fees.
            </p>
          </article>

          <article className="bg-stone-100/75 p-5">
            <p className="text-xs font-[450] uppercase tracking-tight mb-6">Interventions</p>
            <p className="mt-2 text-3xl font-[450] tracking-tighter">
              {formatCount(overviewTotals.interventionsCount)}
            </p>
            <p className="mt-1 text-sm text-stone-400 font-[450] leading-tight">
              {formatPercentage(overviewTotals.interventionRate)} intervention rate across {formatCount(overviewTotals.analyses)} analyses.
            </p>
          </article>

          <article className="bg-stone-100/75 p-5">
            <p className="text-xs font-[450] uppercase tracking-tight mb-6">Avg saved / intervention</p>
            <p className="mt-2 text-3xl font-[450] tracking-tighter">
              {formatCurrency(overviewTotals.avgSavedPerIntervention)}
            </p>
            <p className="mt-1 text-sm text-stone-400 font-[450] leading-tight">
              Mean value captured whenever a mistake is prevented.
            </p>
          </article>

          <article className="bg-stone-100/75 p-5">
            <p className="text-xs font-[450] uppercase tracking-tight mb-6">Savings efficiency</p>
            <p className="mt-2 text-3xl font-[450] tracking-tighter ">
              {overviewTotals.efficiencyRatio > 0 ? `${overviewTotals.efficiencyRatio.toFixed(1)}x` : "0.0x"}
            </p>
            <p className="mt-1 text-sm text-stone-400 font-[450] leading-tight">
              Money saved per euro spent on platform fees.
            </p>
          </article>
        </div>
      </section>

      <section className="mt-8 grid gap-4 xl:grid-cols-2">
        <article className="border border-stone-200 bg-white p-5 md:p-6">
          <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-xl font-[450] tracking-tighter text-[#111]">Mistake count by category</h2>

            </div>
            <PeriodSelector period={mistakesPeriod} onChange={setMistakesPeriod} />
          </div>

          {isLoading ? <EmptyChart label="Loading category trends..." /> : null}
          {!isLoading && categoryRowsForMistakes.length === 0 ? (
            <EmptyChart label="No prevented mistakes in this period." />
          ) : null}
          {!isLoading && categoryRowsForMistakes.length > 0 ? (
            <ApexChart options={mistakesChartOptions} series={mistakesChartSeries} height={360} />
          ) : null}
        </article>

        <article className="border border-stone-200 bg-white p-5  md:p-6">
          <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-xl font-[450] tracking-tighter">Money saved by category</h2>
            </div>
            <PeriodSelector period={moneyPeriod} onChange={setMoneyPeriod} />
          </div>

          {isLoading ? <EmptyChart label="Loading savings breakdown..." /> : null}
          {!isLoading && categoryRowsForMoney.length === 0 ? (
            <EmptyChart label="No money-saved records in this period." />
          ) : null}
          {!isLoading && categoryRowsForMoney.length > 0 ? (
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
          <p className="text-xs font-[450] uppercase tracking-tighter text-stone-500 mb-8">Top risk category</p>
          <p className="mt-2 text-xl font-[450] tracking-tighter]">
            {topMistakeCategory ? topMistakeCategory.category : "No data"}
          </p>
          <p className="mt-2 text-sm text-stone-500">
            {topMistakeCategory
              ? `${formatCount(topMistakeCategory.mistakes)} prevented mistakes (${formatPercentage(topMistakeCategory.interventionRate)} rate).`
              : "No interventions were recorded for this period."}
          </p>
        </article>

        <article className=" border border-stone-200 bg-white p-5">
          <p className="text-xs font-[450] uppercase tracking-tighter text-stone-500 mb-8">Top savings category</p>
          <p className="mt-2 text-xl font-[450] tracking-tighter">
            {topSavingsCategory ? topSavingsCategory.category : "No data"}
          </p>
          <p className="mt-2 text-sm text-stone-500">
            {topSavingsCategory
              ? `${formatCurrency(topSavingsCategory.moneySaved)} saved across ${formatCount(topSavingsCategory.analyses)} analyses.`
              : "No money-saved records were found for this period."}
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
