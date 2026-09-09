import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { roleHome } from "@/lib/roleHome";
import { ProtectedRoute } from "@/routes/ProtectedRoute";
import { AppShell } from "@/components/layout/AppShell";

import Login from "@/pages/auth/Login";
import Register from "@/pages/auth/Register";
import PendingApproval from "@/pages/auth/PendingApproval";
import ChangePassword from "@/pages/auth/ChangePassword";
import VerifyCertificate from "@/pages/public/VerifyCertificate";
import { Unauthorized, NotFound } from "@/pages/Misc";

import OwnerDashboardPage from "@/pages/owner/Dashboard";
import OwnerInstruments from "@/pages/owner/Instruments";
import InstrumentDetail from "@/pages/owner/InstrumentDetail";
import RegisterInstrument from "@/pages/owner/RegisterInstrument";
import OwnerApplications from "@/pages/owner/Applications";
import OwnerApplicationDetail from "@/pages/owner/ApplicationDetail";
import NewApplication from "@/pages/owner/NewApplication";
import { OwnerCertificates, OwnerCertificateDetail } from "@/pages/owner/Certificates";

import OfficerDashboardPage from "@/pages/officer/Dashboard";
import { OfficerQueue, OfficerAssignments } from "@/pages/officer/Queue";
import { OfficerApplicationDetail } from "@/pages/officer/ApplicationDetail";
import { InspectionWorkflow } from "@/pages/officer/Inspection";
import { OfficerCertificates, OfficerCertificateDetail } from "@/pages/officer/Certificates";

import AdminDashboardPage from "@/pages/admin/Dashboard";
import AdminInstruments from "@/pages/admin/AdminInstruments";
import AdminApplications from "@/pages/admin/Applications";
import AdminApplicationDetail from "@/pages/admin/ApplicationDetail";
import { AdminCertificates, AdminCertificateDetail } from "@/pages/admin/Certificates";
import AdminUsers from "@/pages/admin/Users";

function RootRedirect() {
  const { user, status } = useAuth();
  if (status === "loading") return null;
  return <Navigate to={user ? roleHome(user.role) : "/login"} replace />;
}

function OfficerRoutes({ role }: { role: "lmo" | "gatc" }) {
  return (
    <Routes>
      <Route index element={<OfficerDashboardPage role={role} />} />
      <Route path="queue" element={<OfficerQueue role={role} />} />
      <Route path="queue/:id" element={<OfficerApplicationDetail role={role} />} />
      <Route path="assignments" element={<OfficerAssignments role={role} />} />
      <Route path="assignments/:id" element={<OfficerApplicationDetail role={role} />} />
      <Route path="applications/:id" element={<OfficerApplicationDetail role={role} />} />
      <Route path="applications/:id/inspect" element={<InspectionWorkflow role={role} />} />
      <Route path="certificates" element={<OfficerCertificates role={role} />} />
      <Route path="certificates/:id" element={<OfficerCertificateDetail />} />
    </Routes>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/pending" element={<PendingApproval />} />
      <Route path="/change-password" element={<ChangePassword />} />
      <Route path="/verify" element={<VerifyCertificate />} />
      <Route path="/verify/:certId" element={<VerifyCertificate />} />
      <Route path="/unauthorized" element={<Unauthorized />} />

      <Route
        path="/app/owner/*"
        element={
          <ProtectedRoute roles={["owner"]}>
            <AppShell>
              <Routes>
                <Route index element={<OwnerDashboardPage />} />
                <Route path="instruments" element={<OwnerInstruments />} />
                <Route path="instruments/new" element={<RegisterInstrument />} />
                <Route path="instruments/:id" element={<InstrumentDetail />} />
                <Route path="applications" element={<OwnerApplications />} />
                <Route path="applications/new" element={<NewApplication />} />
                <Route path="applications/:id" element={<OwnerApplicationDetail />} />
                <Route path="certificates" element={<OwnerCertificates />} />
                <Route path="certificates/:id" element={<OwnerCertificateDetail />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </AppShell>
          </ProtectedRoute>
        }
      />

      <Route
        path="/app/lmo/*"
        element={
          <ProtectedRoute roles={["lmo"]}>
            <AppShell>
              <OfficerRoutes role="lmo" />
            </AppShell>
          </ProtectedRoute>
        }
      />

      <Route
        path="/app/gatc/*"
        element={
          <ProtectedRoute roles={["gatc"]}>
            <AppShell>
              <OfficerRoutes role="gatc" />
            </AppShell>
          </ProtectedRoute>
        }
      />

      <Route
        path="/app/admin/*"
        element={
          <ProtectedRoute roles={["admin"]}>
            <AppShell>
              <Routes>
                <Route index element={<AdminDashboardPage />} />
                <Route path="users" element={<AdminUsers />} />
                <Route path="instruments" element={<AdminInstruments />} />
                <Route path="applications" element={<AdminApplications />} />
                <Route path="applications/:id" element={<AdminApplicationDetail />} />
                <Route path="certificates" element={<AdminCertificates />} />
                <Route path="certificates/:id" element={<AdminCertificateDetail />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </AppShell>
          </ProtectedRoute>
        }
      />

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
