"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type ApexSeries = {
  name: string;
  type?: "line" | "bar" | "area";
  data: Array<number | null>;
};

interface ApexChartProps {
  options: Record<string, unknown>;
  series: ApexSeries[];
  height?: number;
  className?: string;
}

type ApexChartConfig = Record<string, unknown> & {
  series: ApexSeries[];
  chart?: Record<string, unknown>;
};

interface ApexChartInstance {
  render: () => Promise<void>;
  destroy: () => void;
}

interface ApexChartConstructor {
  new (element: HTMLElement, options: ApexChartConfig): ApexChartInstance;
}

declare global {
  interface Window {
    ApexCharts?: ApexChartConstructor;
  }
}

let apexScriptLoader: Promise<void> | null = null;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function loadApexCharts() {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("ApexCharts can only be loaded in the browser."));
  }

  if (window.ApexCharts) {
    return Promise.resolve();
  }

  if (apexScriptLoader) {
    return apexScriptLoader;
  }

  apexScriptLoader = new Promise<void>((resolve, reject) => {
    const existingScript = document.getElementById("apexcharts-cdn-script") as HTMLScriptElement | null;

    if (existingScript) {
      existingScript.addEventListener("load", () => resolve(), { once: true });
      existingScript.addEventListener("error", () => reject(new Error("Failed to load ApexCharts.")), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.id = "apexcharts-cdn-script";
    script.src = "https://cdn.jsdelivr.net/npm/apexcharts@4.5.0/dist/apexcharts.min.js";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load ApexCharts."));
    document.head.appendChild(script);
  });

  return apexScriptLoader;
}

export function ApexChart({
  options,
  series,
  height = 360,
  className = "",
}: ApexChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [hasLoadedScript, setHasLoadedScript] = useState(false);
  const [hasLoadError, setHasLoadError] = useState(false);

  const optionsKey = useMemo(() => JSON.stringify(options), [options]);
  const seriesKey = useMemo(() => JSON.stringify(series), [series]);

  useEffect(() => {
    let isMounted = true;

    loadApexCharts()
      .then(() => {
        if (!isMounted) {
          return;
        }
        setHasLoadedScript(true);
      })
      .catch(() => {
        if (!isMounted) {
          return;
        }
        setHasLoadError(true);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!hasLoadedScript || hasLoadError || !containerRef.current || !window.ApexCharts) {
      return;
    }

    const chartOptions = isRecord(options.chart) ? options.chart : {};
    const config: ApexChartConfig = {
      ...options,
      series,
      chart: {
        ...chartOptions,
        height,
      },
    };

    const instance = new window.ApexCharts(containerRef.current, config);
    void instance.render();

    return () => {
      instance.destroy();
    };
  }, [hasLoadedScript, hasLoadError, height, options, optionsKey, series, seriesKey]);

  if (hasLoadError) {
    return (
      <div
        className={`flex h-full min-h-[220px] items-center justify-center  border border-stone-200 bg-stone-50 text-sm text-stone-500 ${className}`}
      >
        Unable to load chart library.
      </div>
    );
  }

  if (!hasLoadedScript) {
    return (
      <div
        className={`h-full min-h-[220px] animate-pulse r bg-stone-100 ${className}`}
        aria-hidden="true"
      />
    );
  }

  return <div ref={containerRef} className={className} />;
}
