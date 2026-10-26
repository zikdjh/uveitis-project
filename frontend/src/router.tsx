import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import PatientShell from "@/components/PatientShell";
import RouteGuard from "@/components/RouteGuard";
import WorkspaceShell from "@/components/WorkspaceShell";
import AdminPage from "@/pages/AdminPage";
import AdminLoginPage from "@/pages/AdminLoginPage";
import HomePage from "@/pages/HomePage";
import LoginPage from "@/pages/LoginPage";
import PrivacyPage from "@/pages/PrivacyPage";
import SecurityPage from "@/pages/SecurityPage";
import { ForbiddenPage, NotFoundPage } from "@/pages/StatusPages";
import AdminCaseDetailPage from "@/pages/admin/CaseDetailPage";
import AccessPage from "@/pages/admin/AccessPage";
import AdminCasesPage from "@/pages/admin/CasesPage";
import AdminKnowledgePage from "@/pages/admin/KnowledgePage";
import CaseLayout from "@/pages/doctor/CaseLayout";
import CaseListPage from "@/pages/doctor/CaseListPage";
import {
  CaseAnalysisPage,
  CaseImagesPage,
  CaseReportPage,
  CaseReviewPage,
  CaseSummaryPage,
  NewCasePage,
} from "@/pages/doctor/CasePanels";
import KnowledgePage from "@/pages/doctor/KnowledgePage";
import ReviewQueuePage from "@/pages/doctor/ReviewQueuePage";
import WorkbenchPage from "@/pages/doctor/WorkbenchPage";

const ServicesPage = lazy(() => import("@/pages/admin/ServicesPage"));

const router = createBrowserRouter([
  {
    element: <PatientShell />,
    children: [
      { path: "/", element: <HomePage /> },
      { path: "/privacy", element: <PrivacyPage /> },
    ],
  },
  { path: "/login", element: <LoginPage /> },
  { path: "/admin/login", element: <AdminLoginPage /> },
  { path: "/forbidden", element: <ForbiddenPage /> },
  {
    element: <RouteGuard roles={["doctor"]} />,
    children: [
      {
        path: "/doctor",
        element: <WorkspaceShell mode="doctor" />,
        children: [
          { index: true, element: <Navigate to="/doctor/workbench" replace /> },
          { path: "workbench", element: <WorkbenchPage /> },
          { path: "cases", element: <CaseListPage /> },
          { path: "cases/new", element: <NewCasePage /> },
          {
            path: "cases/:caseId",
            element: <CaseLayout />,
            children: [
              { index: true, element: <Navigate to="summary" replace /> },
              { path: "summary", element: <CaseSummaryPage /> },
              { path: "images", element: <CaseImagesPage /> },
              { path: "analysis", element: <CaseAnalysisPage /> },
              { path: "review", element: <CaseReviewPage /> },
              { path: "report", element: <CaseReportPage /> },
            ],
          },
          { path: "reviews", element: <ReviewQueuePage /> },
          { path: "knowledge", element: <KnowledgePage /> },
          { path: "security", element: <SecurityPage /> },
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
          { index: true, element: <AdminPage /> },
          { path: "cases", element: <AdminCasesPage /> },
          { path: "cases/:caseId", element: <AdminCaseDetailPage /> },
          { path: "knowledge", element: <AdminKnowledgePage /> },
          { path: "services", element: <Suspense fallback={<div className="page-loading" />}><ServicesPage /></Suspense> },
          { path: "access", element: <AccessPage /> },
          { path: "security", element: <SecurityPage /> },
        ],
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
]);

export default router;
