import Link from "next/link";
import { Archive, BarChart3, FileSearch, GitFork, ShieldCheck, ClipboardList, LockKeyhole, UserCog } from "lucide-react";

const nav = [
  { href: "/", label: "Buscador", icon: FileSearch },
  { href: "/report", label: "Reporte", icon: ClipboardList },
  { href: "/admin", label: "Admin", icon: ShieldCheck },
  { href: "/cases", label: "Casos", icon: Archive },
  { href: "/users", label: "Usuarios", icon: UserCog },
  { href: "/graph", label: "Grafo", icon: GitFork },
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/login", label: "Login", icon: LockKeyhole }
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#070b12]">
      <header className="border-b border-border bg-[#0a111d]/95">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <Link href="/" className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-md border border-signal bg-[#09251f] text-sm font-bold text-signal">
              VG
            </div>
            <div>
              <p className="text-base font-semibold tracking-normal text-white">VERIGRAPH</p>
              <p className="text-xs text-slate-400">Fraude digital, evidencia y grafos</p>
            </div>
          </Link>
          <nav className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 sm:mx-0 sm:flex-wrap sm:px-0 sm:pb-0">
            {nav.map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className="focus-ring inline-flex h-10 shrink-0 items-center gap-2 rounded-md border border-border bg-panel px-3 text-sm text-slate-200 transition hover:border-slate-500 hover:bg-[#172236]"
                >
                  <Icon aria-hidden="true" size={16} />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-5 py-8">{children}</main>
    </div>
  );
}
