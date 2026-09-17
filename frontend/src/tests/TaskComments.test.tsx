import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TaskComments } from "@/components/TaskComments";
import type { ApiComment } from "@/types";

const comments: ApiComment[] = [
  {
    id: "c1",
    body: "First note",
    created_at: "2026-09-17T10:00:00.000Z",
    author: { id: "u1", name: "Meera Iyer", email: "meera@taskboard.dev" },
  },
  {
    id: "c2",
    body: "Second note",
    created_at: "2026-09-17T11:00:00.000Z",
    author: { id: "u2", name: "Arjun Rao", email: "arjun@taskboard.dev" },
  },
];

vi.mock("@/lib/api-client", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api-client";

const mockedFetch = vi.mocked(apiFetch);

function renderComments(canPost: boolean) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TaskComments taskId="t_1" canPost={canPost} />
    </QueryClientProvider>,
  );
}

describe("<TaskComments />", () => {
  beforeEach(() => {
    mockedFetch.mockReset();
  });

  it("lists comments chronologically with author and body", async () => {
    mockedFetch.mockResolvedValueOnce({ comments });
    renderComments(true);

    await waitFor(() => {
      expect(screen.getByText("First note")).toBeInTheDocument();
    });
    expect(screen.getByText("Second note")).toBeInTheDocument();
    expect(screen.getByText("Meera Iyer")).toBeInTheDocument();
    expect(screen.getByText("Arjun Rao")).toBeInTheDocument();

    const items = screen.getByTestId("comment-list").querySelectorAll("li");
    expect(items[0]).toHaveTextContent("First note");
    expect(items[1]).toHaveTextContent("Second note");
  });

  it("shows the post form for members and submits a comment", async () => {
    mockedFetch
      .mockResolvedValueOnce({ comments: [] })
      .mockResolvedValueOnce({
        comment: {
          id: "c3",
          body: "Hello team",
          created_at: "2026-09-17T12:00:00.000Z",
          author: { id: "u1", name: "Meera Iyer", email: "meera@taskboard.dev" },
        },
      })
      .mockResolvedValueOnce({
        comments: [
          {
            id: "c3",
            body: "Hello team",
            created_at: "2026-09-17T12:00:00.000Z",
            author: { id: "u1", name: "Meera Iyer", email: "meera@taskboard.dev" },
          },
        ],
      });

    renderComments(true);

    await waitFor(() => {
      expect(screen.getByLabelText("comment body")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("comment body"), {
      target: { value: "Hello team" },
    });
    fireEvent.click(screen.getByRole("button", { name: /post comment/i }));

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith("/api/tasks/t_1/comments", {
        method: "POST",
        body: JSON.stringify({ body: "Hello team" }),
      });
    });
  });

  it("hides the post form for viewers", async () => {
    mockedFetch.mockResolvedValueOnce({ comments });
    renderComments(false);

    await waitFor(() => {
      expect(screen.getByText("First note")).toBeInTheDocument();
    });
    expect(screen.queryByLabelText("comment body")).not.toBeInTheDocument();
    expect(
      screen.getByText(/viewers can read comments but cannot post/i),
    ).toBeInTheDocument();
  });
});
