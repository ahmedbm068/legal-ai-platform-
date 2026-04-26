import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import AppErrorBoundary from "./components/AppErrorBoundary";
import { RoutedWorkspaceProvider } from "./context/RoutedWorkspaceContext";
import AppRouter from "./router/AppRouter";
import "./styles.css";
import "./router-shell.css";
import { registerPwaServiceWorker } from "./registerPwa";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppErrorBoundary>
      <RoutedWorkspaceProvider>
        <BrowserRouter>
          <AppRouter />
        </BrowserRouter>
      </RoutedWorkspaceProvider>
    </AppErrorBoundary>
  </React.StrictMode>
);

registerPwaServiceWorker();
