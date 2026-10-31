import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import PatientShell from "@/components/PatientShell";
import RouteGuard from "@/components/RouteGuard";
import WorkspaceShell from "@/components/WorkspaceShell";
import type { ComponentType } from "react";

function lazyElement(loader: () => Promise<{ default: ComponentType }>) {
  const Page = lazy(loader);
  return (
    <Suspense fallback={<div className="page-loading" />}>
      <Page />
    </Suspense>
  );
}

function namedLazyElement(
  loader: () => Promise<Record<string, unknown>>,
  exportName: string,
) {
  return lazyElement(async () => {
    const module = await loader();
    return { default: module[exportName] as ComponentType };
  });
}

const router = createBrowserRouter([
  {
    element: <PatientShell />,
    children: [
      {
        path: "/",
        element: lazyElement(() => import("@/pages/HomePage")),
      },
      {
        path: "/privacy",
        element: lazyElement(() => import("@/pages/PrivacyPage")),
      },
    ],
  },
  {
    path: "/login",
    element: lazyElement(() => import("@/pages/LoginPage")),
  },
  {
    path: "/admin/login",
    element: lazyElement(() => import("@/pages/AdminLoginPage")),
  },
  {
    path: "/forbidden",
    element: namedLazyElement(
      () => import("@/pages/StatusPages"),
      "ForbiddenPage",
    ),
  },
  {
    element: <RouteGuard roles={["doctor"]} />,
    children: [
      {
        path: "/doctor",
        element: <WorkspaceShell mode="doctor" />,
        children: [
          { index: true, element: <Navigate to="/doctor/workbench" replace /> },
          {
            path: "workbench",
            element: lazyElement(() => import("@/pages/doctor/WorkbenchPage")),
          },
          {
            path: "cases",
            element: lazyElement(() => import("@/pages/doctor/CaseListPage")),
          },
          {
            path: "cases/new",
            element: namedLazyElement(
              () => import("@/pages/doctor/CasePanels"),
              "NewCasePage",
            ),
          },
          {
            path: "cases/:caseId",
            element: lazyElement(() => import("@/pages/doctor/CaseLayout")),
            children: [
              { index: true, element: <Navigate to="summary" replace /> },
              {
                path: "summary",
                element: namedLazyElement(
                  () => import("@/pages/doctor/CasePanels"),
                  "CaseSummaryPage",
                ),
              },
              {
                path: "images",
                element: namedLazyElement(
                  () => import("@/pages/doctor/CasePanels"),
                  "CaseImagesPage",
                ),
              },
              {
                path: "analysis",
                element: namedLazyElement(
                  () => import("@/pages/doctor/CasePanels"),
                  "CaseAnalysisPage",
                ),
              },
              {
                path: "review",
                element: namedLazyElement(
                  () => import("@/pages/doctor/CasePanels"),
                  "CaseReviewPage",
                ),
              },
              {
                path: "report",
                element: namedLazyElement(
                  () => import("@/pages/doctor/CasePanels"),
                  "CaseReportPage",
                ),
              },
            ],
          },
          { path: "reviews", element: <Navigate to="/doctor/cases?status=awaiting_review" replace /> },
          {
            path: "knowledge",
            element: lazyElement(() => import("@/pages/doctor/KnowledgePage")),
          },
          {
            path: "security",
            element: lazyElement(() => import("@/pages/SecurityPage")),
          },
        ],
      },
    ],
  },
  {
    element: <RouteGuard roles={["admin"]} />,
    children: [
      {
        path: "/admin",
        element: <WorkspaceShell mode="admin" />,
        children: [
          {
            index: true,
            element: lazyElement(() => import("@/pages/AdminPage")),
          },
          {
            path: "cases",
            element: lazyElement(() => import("@/pages/admin/CasesPage")),
          },
          {
            path: "cases/:caseId",
            element: lazyElement(() => import("@/pages/admin/CaseDetailPage")),
          },
          {
            path: "knowledge",
            element: lazyElement(() => import("@/pages/admin/KnowledgePage")),
          },
          {
            path: "services",
            element: lazyElement(() => import("@/pages/admin/ServicesPage")),
          },
          {
            path: "data-dictionary",
            element: lazyElement(() => import("@/pages/admin/DataDictionaryPage")),
          },
          {
            path: "access",
            element: lazyElement(() => import("@/pages/admin/AccessPage")),
          },
          {
            path: "security",
            element: lazyElement(() => import("@/pages/SecurityPage")),
          },
        ],
      },
    ],
  },
  {
    path: "*",
    element: namedLazyElement(
      () => import("@/pages/StatusPages"),
      "NotFoundPage",
    ),
  },
]);

export default router;
