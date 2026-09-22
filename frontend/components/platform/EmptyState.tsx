export default function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="app-panel border-dashed p-8 text-center">
      <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-accent/10 text-xl text-accent">
        !
      </div>
      <h3 className="mt-3 text-base font-semibold text-primary">{title}</h3>
      <p className="mt-2 text-sm text-secondary">{body}</p>
    </div>
  );
}
