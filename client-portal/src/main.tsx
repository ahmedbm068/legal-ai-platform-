import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { PortalErrorBoundary } from "./components/PortalErrorBoundary";
import ToastContainer from "./components/ToastContainer";
import { PortalProvider } from "./context/PortalContext";
import { ToastProvider } from "./context/ToastContext";
import PortalRouter from "./router/PortalRouter";
import "./styles.css";
import { registerPwaServiceWorker } from "./registerPwa";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <PortalErrorBoundary>
      <ToastProvider>
        <BrowserRouter>
          <PortalProvider>
            <PortalRouter />
          </PortalProvider>
        </BrowserRouter>
        <ToastContainer />
      </ToastProvider>
    </PortalErrorBoundary>
  </React.StrictMode>
);

registerPwaServiceWorker();
