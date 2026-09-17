import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api-client";

type ExportResult = {
  exported: number;
  created: number;
  updated: number;
  failed: { task_id: string; error: string }[];
};

type Props = {
  projectId: string;
  canExport: boolean;
};

export function ExportTasksButton({ projectId, canExport }: Props) {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const exportTasks = useMutation({
    mutationFn: () =>
      apiFetch<ExportResult>(`/api/projects/${projectId}/export`, { method: "POST" }),
    onSuccess: (data) => {
      setError(null);
      const failedCount = data.failed?.length ?? 0;
      setMessage(
        failedCount > 0
          ? `exported ${data.exported} task(s); ${failedCount} failed`
          : `exported ${data.exported} task(s) to Airtable`,
      );
    },
    onError: (err) => {
      setMessage(null);
      setError(err instanceof Error ? err.message : "export failed");
    },
  });

  if (!canExport) return null;

  return (
    <div className="text-right">
      <button
        type="button"
        data-testid="export-tasks"
        onClick={() => {
          setMessage(null);
          setError(null);
          exportTasks.mutate();
        }}
        disabled={exportTasks.isPending}
        className="text-sm px-4 py-2 rounded-md border border-border hover:border-accent disabled:opacity-50"
      >
        {exportTasks.isPending ? "exporting…" : "export to Airtable"}
      </button>
      {message && <p className="text-xs text-muted mt-2">{message}</p>}
      {error && (
        <p className="text-xs text-red-400 mt-2" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
