// Must be the first import: patches history.pushState/replaceState so the
// proxy's routing params (e.g. ?app=<id>) survive client-side navigation,
// reloads, and back/forward.
import "@/lib/preserveProxyRouting";
import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
