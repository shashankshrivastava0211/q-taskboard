import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api-client";
import type { ApiComment } from "@/types";

type Props = {
  taskId: string;
  canPost: boolean;
};

export function TaskComments({ taskId, canPost }: Props) {
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["comments", taskId],
    queryFn: () => apiFetch<{ comments: ApiComment[] }>(`/api/tasks/${taskId}/comments`),
  });

  const postComment = useMutation({
    mutationFn: (text: string) =>
      apiFetch<{ comment: ApiComment }>(`/api/tasks/${taskId}/comments`, {
        method: "POST",
        body: JSON.stringify({ body: text }),
      }),
    onSuccess: () => {
      setBody("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["comments", taskId] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "post failed"),
  });

  const comments = data?.comments ?? [];

  return (
    <section className="mt-6 border-t border-border pt-4">
      <h3 className="text-sm font-medium mb-3">comments</h3>

      {isLoading && <p className="text-xs text-muted">loading comments…</p>}

      {!isLoading && comments.length === 0 && (
        <p className="text-xs text-muted italic">no comments yet</p>
      )}

      {comments.length > 0 && (
        <ul className="space-y-3 mb-4" data-testid="comment-list">
          {comments.map((c) => (
            <li key={c.id} className="text-sm">
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-medium">{c.author.name}</span>
                <time className="text-xs text-muted" dateTime={c.created_at}>
                  {new Date(c.created_at).toLocaleString()}
                </time>
              </div>
              <p className="text-muted mt-0.5 whitespace-pre-wrap">{c.body}</p>
            </li>
          ))}
        </ul>
      )}

      {canPost ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const text = body.trim();
            if (!text) return;
            setError(null);
            postComment.mutate(text);
          }}
          className="space-y-2"
        >
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="add a comment"
            rows={2}
            aria-label="comment body"
            className="block w-full rounded-md bg-bg border border-border px-3 py-2 text-sm focus:border-accent focus:outline-none"
          />
          {error && (
            <p className="text-sm text-red-400" role="alert">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={postComment.isPending || !body.trim()}
            className="text-sm px-3 py-1.5 rounded-md bg-accent text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {postComment.isPending ? "posting…" : "post comment"}
          </button>
        </form>
      ) : (
        <p className="text-xs text-muted">viewers can read comments but cannot post</p>
      )}
    </section>
  );
}
