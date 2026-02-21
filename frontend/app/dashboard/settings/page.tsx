"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { FiArrowLeft, FiTrash2 } from "react-icons/fi";

import type { CalendarResponse } from "@/lib/api-types";
import { addCalendar, deleteCalendar, listCalendars, toErrorMessage } from "@/lib/frontend-api";

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

        if (!isMounted) {
          return;
        }

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
        if (!isMounted) {
          return;
        }

        setError("Unable to reach the server.");
        setIsLoading(false);
      }
    };

    void loadCalendars();

    return () => {
      isMounted = false;
    };
  }, [router]);

  const handleAddCalendar = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (isSubmitting) {
      return;
    }

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
            <label htmlFor="calendarName" className="block text-sm font-medium text-stone-800">
              Name
            </label>
            <input
              id="calendarName"
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Work Calendar"
              className="w-full bg-white px-4 py-3 text-sm text-stone-900 outline-none ring-1 ring-stone-300 placeholder:text-stone-400 focus:ring-2 focus:ring-stone-500"
              required
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="calendarLink" className="block text-sm font-medium text-stone-800">
              iCal URL
            </label>
            <input
              id="calendarLink"
              type="url"
              value={icalUrl}
              onChange={(event) => setIcalUrl(event.target.value)}
              placeholder="https://calendar.google.com/calendar/ical/..."
              className="w-full bg-white px-4 py-3 text-sm text-stone-900 outline-none ring-1 ring-stone-300 placeholder:text-stone-400 focus:ring-2 focus:ring-stone-500"
              required
            />
          </div>

          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          {success ? <p className="text-sm text-green-700">{success}</p> : null}

          <button
            type="submit"
            disabled={isSubmitting}
            className="inline-flex h-10 items-center justify-center bg-[#1d1d1f] px-5 text-sm font-medium text-white disabled:opacity-60"
          >
            {isSubmitting ? "Adding..." : "Add Calendar"}
          </button>
        </form>

        <div className="mt-8">
          <h3 className="mb-3 text-base font-medium text-stone-900">Connected Calendars</h3>
          {isLoading ? <p className="text-sm text-stone-600">Loading calendars...</p> : null}

          {!isLoading && calendars.length === 0 ? (
            <p className="text-sm text-stone-600">No calendars connected yet.</p>
          ) : null}

          <ul className="space-y-2">
            {calendars.map((calendar) => (
              <li
                key={calendar.id}
                className="flex items-center justify-between gap-3 border border-stone-200 p-3"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-stone-900">{calendar.name}</p>
                  <p className="truncate text-xs text-stone-600">{calendar.ical_url}</p>
                </div>
                <button
                  type="button"
                  onClick={() => handleDeleteCalendar(calendar.id)}
                  className="inline-flex h-9 w-9 items-center justify-center bg-stone-100 text-stone-700 hover:bg-stone-200"
                  aria-label={`Delete ${calendar.name}`}
                >
                  <FiTrash2 size={16} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </main>
  );
}
