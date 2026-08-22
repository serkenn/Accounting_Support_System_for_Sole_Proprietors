import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider, createBrowserRouter } from "react-router-dom";
import { AppShell } from "./components/ext/AppShell";
import "./index.css";
import { Detail } from "./screens/Detail";
import { Evidence } from "./screens/Evidence";
import { Overview } from "./screens/Overview";
import { Review } from "./screens/Review";

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Overview /> },
      { path: "transactions", element: <Detail /> },
      { path: "review", element: <Review /> },
      // ★URL に反映する。リンクを自分にメモできる（第3部 §7）
      { path: "evidence/:docId", element: <Evidence /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
