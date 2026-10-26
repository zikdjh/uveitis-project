import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ConfigProvider } from "antd";
import { RouterProvider } from "react-router-dom";

import router from "@/router";
import "@/styles/global.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element not found");
}

createRoot(rootElement).render(
  <StrictMode>
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: "#17614d",
          colorInfo: "#17614d",
          colorSuccess: "#2f765d",
          colorWarning: "#9b6b18",
          colorError: "#a63f3b",
          borderRadius: 5,
          fontFamily: '"Noto Sans SC", "Microsoft YaHei", sans-serif',
          controlHeight: 38,
        },
        components: {
          Button: {
            fontWeight: 600,
          },
          Card: {
            headerBg: "#fcfdfd",
          },
          Form: {
            labelColor: "#4c655e",
          },
        },
      }}
    >
      <RouterProvider router={router} />
    </ConfigProvider>
  </StrictMode>,
);
