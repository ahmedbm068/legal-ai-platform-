import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AppErrorBoundary from "./AppErrorBoundary";

function Boom(): JSX.Element {
  throw new Error("forced render failure");
}

describe("AppErrorBoundary", () => {
  beforeEach(() => {
    // The boundary calls console.error in componentDidCatch — silence it
    // in tests so the output stays readable.
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("renders children when no error occurs", () => {
    render(
      <AppErrorBoundary>
        <p>healthy</p>
      </AppErrorBoundary>
    );
    expect(screen.getByText("healthy")).toBeInTheDocument();
  });

  it("renders the recovery shell when a child throws", () => {
    render(
      <AppErrorBoundary>
        <Boom />
      </AppErrorBoundary>
    );
    expect(
      screen.getByText(/The interface hit a bad cached response/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/forced render failure/)).toBeInTheDocument();
  });

  it('"Try again" clears the error and lets children re-mount', async () => {
    let shouldThrow = true;
    function Toggle() {
      if (shouldThrow) throw new Error("bad");
      return <p>recovered</p>;
    }

    const { rerender } = render(
      <AppErrorBoundary>
        <Toggle />
      </AppErrorBoundary>
    );
    expect(screen.getByText(/Workspace recovery/i)).toBeInTheDocument();

    shouldThrow = false;
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /try again/i }));
    rerender(
      <AppErrorBoundary>
        <Toggle />
      </AppErrorBoundary>
    );

    expect(screen.getByText("recovered")).toBeInTheDocument();
  });
});
