import { statusTone, zhStatus } from "@/services/format";

export default function StatusBadge({ value }: { value?: string | null }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${statusTone(value)}`}>
      {zhStatus(value)}
    </span>
  );
}
