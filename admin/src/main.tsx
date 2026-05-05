import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import ToastContainer from "./components/ToastContainer";
import { ToastProvider } from "./context/ToastContext";

createRoot(document.getElementById("root")!).render(
    <StrictMode>
        <AppErrorBoundary>
            <ToastProvider>
                <App />
                <ToastContainer />
            </ToastProvider>
        </AppErrorBoundary>
    </StrictMode>
);
