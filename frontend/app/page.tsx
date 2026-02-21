import Image from "next/image";

export default function Home() {
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

  return (
    <div className="min-h-screen">
      <main className="grid min-h-screen grid-cols-1 lg:grid-cols-[minmax(0,1fr)_500px]">
        <div className=" px-6 py-12 border-r border-stone-200/75">
          <div className="mx-auto flex w-full max-w-4xl flex-col gap-10">
            <div className="text-5xl tracking-tighter mt-14">
              Make Purchases Without Mistakes
            </div>
            <p className="max-w-3xl lg:text-lg leading-tight font-[450] text-stone-500">
              We help make better buying decisions by double-checking the payment details and purchase necessicity to avoid mistakes and impulse buying.
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
            <div className="mb-8 text-center text-lg font-medium text-stone-900">Welcome Back!</div>
            <form action="/dashboard" className="space-y-6">
              <div className="space-y-2">
                <label htmlFor="email" className="block text-xs font-medium text-stone-900">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  className="h-11 w-full rounded-xs bg-stone-100 px-3 text-[#111] outline-none"
                />
              </div>

              <div className="space-y-2">
                <label htmlFor="password" className="block text-xs font-medium text-stone-900">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  className="h-11 w-full rounded-xs bg-stone-100 px-3 text-[#111] outline-none"
                />
              </div>

              <button
                type="submit"
                className="mt-10 h-11 w-full rounded-full bg-[#1d1d1f] text-sm font-medium text-[#f6f6f6]"
              >
                Login
              </button>
            </form>
          </div>
        </div>
      </main>
    </div>
  );
}
