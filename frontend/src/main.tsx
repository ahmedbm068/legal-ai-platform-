import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import AppErrorBoundary from "./components/AppErrorBoundary";
import ToastContainer from "./components/ToastContainer";
import { ToastProvider } from "./context/ToastContext";
import { RoutedWorkspaceProvider } from "./context/RoutedWorkspaceContext";
import AppRouter from "./router/AppRouter";
import "./styles.css";
import "./router-shell.css";
import "./tailwind.css";
import "./toast.css";
import { registerPwaServiceWorker } from "./registerPwa";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppErrorBoundary>
      <ToastProvider>
        <RoutedWorkspaceProvider>
          <BrowserRouter>
            <AppRouter />
          </BrowserRouter>
        </RoutedWorkspaceProvider>
        <ToastContainer />
      </ToastProvider>
    </AppErrorBoundary>
  </React.StrictMode>
);

registerPwaServiceWorker();
