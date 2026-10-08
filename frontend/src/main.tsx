import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { FeedbackProvider } from "./components/feedback";
import Layout from "./components/Layout";
import { LoadingBlock } from "./components/ui";
import "./index.css";
import AlertsPage from "./pages/Alerts";
import DashboardPage from "./pages/Dashboard";
import EmailLogsPage from "./pages/EmailLogs";
import LoginPage from "./pages/Login";
import LogsPage from "./pages/Logs";
import SchedulerPage from "./pages/Scheduler";
import SettingsPage from "./pages/Settings";
import UsersPage from "./pages/Users";
import WebsiteDetailPage from "./pages/WebsiteDetail";
import WebsitesPage from "./pages/Websites";

function Guarded() {
  const { user, loading, isAdmin } = useAuth();
  if (loading) return <LoadingBlock label="Loading..." />;
  if (!user) return <LoginPage />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="websites" element={<WebsitesPage />} />
        <Route path="websites/:id" element={<WebsiteDetailPage />} />
        <Route path="logs" element={<LogsPage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="emails" element={<EmailLogsPage />} />
        <Route path="scheduler" element={<SchedulerPage />} />
        <Route path="settings" element={<SettingsPage />} />
        {isAdmin && <Route path="users" element={<UsersPage />} />}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <FeedbackProvider>
        <AuthProvider>
          <Guarded />
        </AuthProvider>
      </FeedbackProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
