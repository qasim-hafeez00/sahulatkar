export default function DashboardSectionLoading() {
  return (
    <section className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-900/50" />
        ))}
      </div>
      <div className="h-64 animate-pulse rounded-[2rem] bg-slate-900/50" />
    </section>
  );
}
