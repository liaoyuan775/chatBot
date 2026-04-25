import type { PropsWithChildren, ReactNode } from "react";

export function PageShell({
  title,
  subtitle,
  actions,
  children
}: PropsWithChildren<{ title: string; subtitle: string; actions?: ReactNode }>) {
  return (
    <section className="fade-up">
      <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-[1.65rem] text-[var(--ink)]">{title}</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--muted)]">{subtitle}</p>
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </header>
      {children}
    </section>
  );
}
