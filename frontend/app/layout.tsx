import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "MediShield — Document Intake",
  description: "Multi-agent insurance document intake and adjudication",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
            <Link href="/" className="flex items-center gap-2">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-slate-900 text-sm font-bold text-white">
                M
              </span>
              <div>
                <div className="text-sm font-semibold leading-tight">
                  MediShield
                </div>
                <div className="text-xs leading-tight text-slate-500">
                  Document Intake
                </div>
              </div>
            </Link>
            <nav className="flex items-center gap-1 text-sm">
              <Link
                href="/"
                className="rounded-md px-3 py-2 font-medium text-slate-600 hover:bg-slate-100"
              >
                Cases
              </Link>
              <Link
                href="/review"
                className="rounded-md px-3 py-2 font-medium text-slate-600 hover:bg-slate-100"
              >
                Review Queue
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
