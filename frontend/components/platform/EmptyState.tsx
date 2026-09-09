export default function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="app-panel border-dashed p-8 text-center">
      <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-pink-50 text-xl text-[#ff2442]">
        !
      </div>
      <h3 className="mt-3 text-base font-semibold text-slate-900">{title}</h3>
      <p className="mt-2 text-sm text-slate-500">{body}</p>
    </div>
  );
}
