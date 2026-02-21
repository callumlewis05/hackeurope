import Link from "next/link";

export default function DashboardLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="min-h-screen">
      <header>
        <div className="mx-auto flex w-full max-w-[1200px] items-center justify-end py-4">
          <Link
            href="/"
            className="bg-[#1d1d1f] px-5 h-10 flex items-center text-sm font-[500] text-[#f6f6f6]"
          >
            Log out
          </Link>
        </div>
      </header>
      {children}
    </div>
  );
}
