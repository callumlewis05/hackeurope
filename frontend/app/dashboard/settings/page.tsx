"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { FiArrowLeft, FiCalendar, FiCopy, FiTrash2 } from "react-icons/fi";

import type { CalendarResponse } from "@/lib/api-types";
import { addCalendar, deleteCalendar, listCalendars, toErrorMessage } from "@/lib/frontend-api";

type CalendarProvider = "google" | "apple" | "outlook" | null;

const CALENDAR_PROVIDER_ICONS: Record<Exclude<CalendarProvider, null>, { alt: string; src: string }> = {
  google: {
    alt: "Google Calendar",
    src: "/google-calendar.png",
  },
  apple: {
    alt: "Apple Calendar",
    src: "/apple-calendar.png",
  },
  outlook: {
    alt: "Outlook Calendar",
    src: "/outlook-calendar.png",
  },
};

function detectCalendarProviderFromUrl(link: string): CalendarProvider {
  const normalizedLink = link.toLowerCase();

  if (normalizedLink.includes("google")) {
    return "google";
  }

  if (normalizedLink.includes("apple") || normalizedLink.includes("icloud")) {
    return "apple";
  }

  if (
    normalizedLink.includes("outlook")
    || normalizedLink.includes("microsoft")
    || normalizedLink.includes("office365")
    || normalizedLink.includes("live.com")
  ) {
    return "outlook";
  }

  return null;
}

export default function DashboardSettingsPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [icalUrl, setIcalUrl] = useState("");
  const [calendars, setCalendars] = useState<CalendarResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    const loadCalendars = async () => {
      try {
        const response = await listCalendars();

        if (!isMounted) return;
        if (!response.ok) {
          if (response.status === 401) {
            router.replace("/");
            return;
          }
          setError(toErrorMessage(response.data, "Unable to load calendars."));
          setIsLoading(false);
          return;
        }
        setCalendars((response.data as CalendarResponse[]) ?? []);
        setIsLoading(false);
      } catch {
        if (!isMounted) return;
        setError("Unable to reach the server.");
        setIsLoading(false);
      }
    };
    void loadCalendars();
    return () => isMounted = false;
  }, [router]);

  const handleAddCalendar = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (isSubmitting) return;
    setError(null);
    setSuccess(null);
    setIsSubmitting(true);

    try {
      const response = await addCalendar(name, icalUrl);
      if (!response.ok) {
        if (response.status === 401) {
          router.replace("/");
          return;
        }
        setError(toErrorMessage(response.data, "Unable to add calendar."));
        return;
      }
      const newCalendar = response.data as CalendarResponse;
      setCalendars((currentCalendars) => [newCalendar, ...currentCalendars]);
      setName("");
      setIcalUrl("");
      setSuccess("Calendar added.");
    } catch {
      setError("Unable to reach the server.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteCalendar = async (calendarId: string) => {
    setError(null);
    setSuccess(null);

    try {
      const response = await deleteCalendar(calendarId);

      if (!response.ok) {
        if (response.status === 401) {
          router.replace("/");
          return;
        }
        setError(toErrorMessage(response.data, "Unable to delete calendar."));
        return;
      }

      setCalendars((currentCalendars) =>
        currentCalendars.filter((calendar) => calendar.id !== calendarId),
      );
      setSuccess("Calendar deleted.");
    } catch {
      setError("Unable to reach the server.");
    }
  };

  const handleCopyCalendarLink = async (calendarName: string, link: string) => {
    setError(null);
    setSuccess(null);

    try {
      if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
        setError("Clipboard is not available in this browser.");
        return;
      }

      await navigator.clipboard.writeText(link);
      setSuccess(`${calendarName} link copied.`);
    } catch {
      setError("Unable to copy the calendar link.");
    }
  };

  return (
    <main className="mx-auto w-full max-w-xl py-12">
      <section className="w-full">
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1 text-sm font-medium text-stone-700 transition-colors hover:text-stone-900"
        >
          <FiArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back
        </Link>
        <h1 className={"text-center text-4xl font-[450] tracking-tighter mb-16"}>Settings</h1>
        <h2 className="text-xl tracking-tighter font-[500] mb-4">Connect Calendar</h2>

        <form onSubmit={handleAddCalendar} className="space-y-4 bg-stone-100 p-6">
          <div className="space-y-2">
            <label htmlFor="calendarName" className="block text-xs font-medium text-stone-800">
              Name
            </label>
            <input
              id="calendarName"
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Work Calendar"
              className="w-full bg-white px-3 h-9 text-sm text-stone-900 outline-none ring-1 ring-stone-200 placeholder:text-stone-400 focus:ring-2 focus:ring-stone-500"
              required
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="calendarLink" className="block text-xs font-medium text-stone-800">
              iCal URL
            </label>
            <input
              id="calendarLink"
              type="url"
              value={icalUrl}
              onChange={(event) => setIcalUrl(event.target.value)}
              placeholder="https://calendar.google.com/calendar/ical/..."
              className="w-full bg-white px-3 h-9 text-sm text-stone-900 outline-none ring-1 ring-stone-200 placeholder:text-stone-400 focus:ring-stone-500"
              required
            />
          </div>

          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          {/*{success ? <p className="text-sm text-green-700">{success}</p> : null}*/}

          <button
            type="submit"
            disabled={isSubmitting}
            className="inline-flex h-9 items-center justify-center bg-[#1d1d1f] px-4 text-sm font-medium text-white disabled:opacity-60"
          >
            {isSubmitting ? "Adding..." : "Add Calendar"}
          </button>
        </form>

        <div className="mt-12 mb-32">
          <h3 className="mb-3 text-stone-900 text-xl tracking-tighter font-[500]">Connected Calendars</h3>
          {isLoading ? <p className="text-sm text-stone-600">Loading calendars...</p> : null}

          {!isLoading && calendars.length === 0 ? (
            <p className="text-sm text-stone-400/80 bg-stone-100 text-center py-16">No calendars connected yet.</p>
          ) : null}

          <ul className="space-y-2">
            {calendars.map((calendar) => {
              const provider = detectCalendarProviderFromUrl(calendar.ical_url);
              const icon = provider ? CALENDAR_PROVIDER_ICONS[provider] : null;

              return (
                <li
                  key={calendar.id}
                  className="flex items-center justify-between gap-2 border border-stone-200 p-4"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    {icon ? (
                      <Image
                        src={icon.src}
                        alt={icon.alt}
                        width={24}
                        height={24}
                        className="h-6 w-6 shrink-0 object-contain"
                      />
                    ) : (
                      <span
                        className="inline-flex h-6 w-6 shrink-0 items-center justify-center text-stone-500"
                        aria-hidden="true"
                      >
                        <FiCalendar size={16} />
                      </span>
                    )}
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-stone-900">{calendar.name}</p>
                      <p className="truncate text-xs text-stone-400">{calendar.ical_url}</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleCopyCalendarLink(calendar.name, calendar.ical_url)}
                    className="inline-flex h-9 aspect-square items-center cursor-pointer justify-center bg-stone-100 text-stone-700 hover:bg-stone-200/65"
                    aria-label={`Copy ${calendar.name} link`}
                  >
                    <FiCopy size={14} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDeleteCalendar(calendar.id)}
                    className="inline-flex h-9 aspect-square items-center cursor-pointer justify-center bg-stone-100 text-stone-700 hover:bg-stone-200/65"
                    aria-label={`Delete ${calendar.name}`}
                  >
                    <FiTrash2 size={14} aria-hidden="true" />
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      </section>
    </main>
  );
}
