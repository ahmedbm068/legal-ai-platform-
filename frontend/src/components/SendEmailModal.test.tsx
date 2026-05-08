import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SendEmailModal from "./SendEmailModal";

describe("SendEmailModal", () => {
  it("renders with the default subject prefilled", () => {
    render(
      <SendEmailModal
        defaultSubject="Letter of demand — case 42"
        onClose={() => {}}
        onSend={() => {}}
      />
    );
    expect(screen.getByLabelText(/Subject/i)).toHaveValue("Letter of demand — case 42");
  });

  it("disables Confirm send until a valid recipient and subject are present", () => {
    const onSend = vi.fn();
    render(<SendEmailModal defaultSubject="Hello" onClose={() => {}} onSend={onSend} />);

    const confirmBtn = screen.getByRole("button", { name: /confirm send/i });
    expect(confirmBtn).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/^To$/i), {
      target: { value: "missing-at-sign" },
    });
    expect(confirmBtn).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/^To$/i), {
      target: { value: "client@example.com" },
    });
    expect(confirmBtn).toBeEnabled();
  });

  it("emits a normalized payload with parsed CC list", async () => {
    const onSend = vi.fn();
    render(
      <SendEmailModal
        defaultSubject="Hi"
        onClose={() => {}}
        onSend={onSend}
      />
    );
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/^To$/i), "  client@example.com ");
    await user.type(
      screen.getByLabelText(/^CC$/i),
      "a@example.com, ,b@example.com"
    );
    await user.click(screen.getByRole("button", { name: /confirm send/i }));

    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith({
      to: "client@example.com",
      subject: "Hi",
      cc: ["a@example.com", "b@example.com"],
    });
  });

  it("invokes onClose when the user clicks the close button", async () => {
    const onClose = vi.fn();
    render(<SendEmailModal defaultSubject="Hi" onClose={onClose} onSend={() => {}} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
