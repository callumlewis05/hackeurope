"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { createClient } from "@/lib/supabase/client";

export default function Home() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const howItWorksItems = [
    {
      title: "1. Connect Your Needs",
      description:
        "Tell us what you are buying, your budget range, and your non-negotiables.",
    },
    {
      title: "2. Get Smart Guidance",
      description:
        "We highlight risks, compare options, and surface the details people usually miss.",
    },
    {
      title: "3. Review With Confidence",
      description:
        "See a clear checklist before paying so you can validate quality, timing, and price.",
    },
    {
      title: "4. Purchase Without Guessing",
      description:
        "Move forward with clear recommendations and fewer costly purchase mistakes.",
    },
  ];

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (isSubmitting) {
      return;
    }

    if (mode === "signup" && !name.trim()) {
      setError("Name is required");
      return;
    }

    setError(null);
    setSuccess(null);
    setIsSubmitting(true);
    const supabase = createClient();

    try {
      if (mode === "login") {
        const { error: signInError } = await supabase.auth.signInWithPassword({
          email,
          password,
        });

        if (signInError) {
          setError(signInError.message);
          return;
        }

        router.push("/dashboard");
        router.refresh();
        return;
      }

      const { data, error: signUpError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: {
            name,
          },
        },
      });

      if (signUpError) {
        setError(signUpError.message);
        return;
      }

      if (!data.session) {
        setSuccess("Account created. Please check your email to confirm your account.");
        return;
      }

      router.push("/dashboard");
      router.refresh();
    } catch {
      setError("Unable to reach the server. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen">
      <main className="grid min-h-screen grid-cols-1 lg:grid-cols-[minmax(0,1fr)_500px]">
        <div className=" px-6 py-12 border-r border-stone-200/75">
          <div className="mx-auto flex w-full max-w-4xl flex-col gap-10">
            <div className="text-5xl tracking-tighter mt-14">Make Purchases Without Mistakes</div>
            <p className="max-w-3xl lg:text-lg leading-tight font-[450] text-stone-500">
              We help make better buying decisions by double-checking the payment details and
              purchase necessicity to avoid mistakes and impulse buying.
            </p>

            <div className="relative h-[300px] w-full overflow-hidden lg:h-[420px]">
              <Image
                src="/hero2.jpg"
                alt="Team collaborating at a desk"
                fill
                priority
                className="object-cover"
              />
            </div>

            <div className={"font-[450] text-xl mt-20"}>How Does it Work?</div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 mb-48">
              {howItWorksItems.map((item) => (
                <div key={item.title} className="bg-stone-100 p-8 py-10">
                  <div className="mb-2 text-base font-medium text-stone-900">{item.title}</div>
                  <p className="text-sm font-[450] text-stone-600">{item.description}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="flex items-center p-8 lg:sticky lg:top-0 lg:h-screen lg:p-12">
          <div className="w-full rounded-sm bg-white p-6 lg:p-8">
            <Image src="/icon2.svg" alt="App icon" width={60} height={60} className="mx-auto mb-4" />
            <div className="mb-2 text-center text-lg font-medium text-stone-900">Welcome Back!</div>
            <div className="mb-6 flex items-center justify-center gap-2 text-sm">
              <button
                type="button"
                onClick={() => {
                  setMode("login");
                  setError(null);
                  setSuccess(null);
                }}
                className={`px-3 py-1 ${mode === "login" ? "bg-stone-900 text-white" : "bg-stone-100"}`}
              >
                Login
              </button>
              <button
                type="button"
                onClick={() => {
                  setMode("signup");
                  setError(null);
                  setSuccess(null);
                }}
                className={`px-3 py-1 ${mode === "signup" ? "bg-stone-900 text-white" : "bg-stone-100"}`}
              >
                Sign up
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
              {mode === "signup" ? (
                <div className="space-y-2">
                  <label htmlFor="name" className="block text-xs font-medium text-stone-900">
                    Name
                  </label>
                  <input
                    id="name"
                    type="text"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    className="h-11 w-full rounded-xs bg-stone-100 px-3 text-[#111] outline-none"
                    required
                  />
                </div>
              ) : null}

              <div className="space-y-2">
                <label htmlFor="email" className="block text-xs font-medium text-stone-900">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="h-11 w-full rounded-xs bg-stone-100 px-3 text-[#111] outline-none"
                  required
                />
              </div>

              <div className="space-y-2">
                <label htmlFor="password" className="block text-xs font-medium text-stone-900">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="h-11 w-full rounded-xs bg-stone-100 px-3 text-[#111] outline-none"
                  required
                />
              </div>

              {error ? <p className="text-sm text-red-600">{error}</p> : null}
              {success ? <p className="text-sm text-green-700">{success}</p> : null}

              <button
                type="submit"
                disabled={isSubmitting}
                className="mt-10 h-11 w-full rounded-full bg-[#1d1d1f] text-sm font-medium text-[#f6f6f6] disabled:opacity-60"
              >
                {isSubmitting ? "Please wait..." : mode === "login" ? "Login" : "Create account"}
              </button>
            </form>
          </div>
        </div>
      </main>
    </div>
  );
}
