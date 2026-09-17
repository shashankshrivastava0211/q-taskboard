import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ExportTasksButton } from "@/components/ExportTasksButton";

function renderButton(canExport: boolean) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ExportTasksButton projectId="p_1" canExport={canExport} />
    </QueryClientProvider>,
  );
}

describe("<ExportTasksButton />", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        text: async () =>
          JSON.stringify({
            exported: 2,
            created: 2,
            updated: 0,
            failed: [],
          }),
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders nothing for viewers", () => {
    renderButton(false);
    expect(screen.queryByTestId("export-tasks")).not.toBeInTheDocument();
  });

  it("posts export and shows success for members", async () => {
    renderButton(true);
    fireEvent.click(screen.getByTestId("export-tasks"));
    await waitFor(() => {
      expect(screen.getByText("exported 2 task(s) to Airtable")).toBeInTheDocument();
    });
    expect(fetch).toHaveBeenCalledWith(
      "/api/projects/p_1/export",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
