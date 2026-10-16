import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "@/routes/ProtectedRoute";
import { AppShell } from "@/components/layout/AppShell";

// Public + auth pages stay eager: prerender.mjs renders these routes at build time,
// and lazy components would prerender as empty fallbacks (bad for SEO).
import Login from "@/pages/auth/Login";
import Register from "@/pages/auth/Register";
import PendingApproval from "@/pages/auth/PendingApproval";
import ForgotPassword from "@/pages/auth/ForgotPassword";
import TwoFactor from "@/pages/auth/TwoFactor";
import ChangePassword from "@/pages/auth/ChangePassword";
import VerifyCertificate from "@/pages/public/VerifyCertificate";
import Landing from "@/pages/public/Landing";
import { Unauthorized, NotFound } from "@/pages/Misc";

// ---- Owner (lazy) ----
const OwnerDashboardPage = lazy(() => import("@/pages/owner/Dashboard"));
const OwnerInstruments = lazy(() => import("@/pages/owner/Instruments"));
const InstrumentDetail = lazy(() => import("@/pages/owner/InstrumentDetail"));
const RegisterInstrument = lazy(() => import("@/pages/owner/RegisterInstrument"));
const OwnerApplications = lazy(() => import("@/pages/owner/Applications"));
const OwnerApplicationDetail = lazy(() => import("@/pages/owner/ApplicationDetail"));
const NewApplication = lazy(() => import("@/pages/owner/NewApplication"));
const OwnerCertificates = lazy(() =>
  import("@/pages/owner/Certificates").then((m) => ({ default: m.OwnerCertificates })),
);
const OwnerCertificateDetail = lazy(() =>
  import("@/pages/owner/Certificates").then((m) => ({ default: m.OwnerCertificateDetail })),
);

// ---- Officer: LMO / GATC (lazy) ----
const OfficerDashboardPage = lazy(() => import("@/pages/officer/Dashboard"));
const OfficerQueue = lazy(() =>
  import("@/pages/officer/Queue").then((m) => ({ default: m.OfficerQueue })),
);
const OfficerAssignments = lazy(() =>
  import("@/pages/officer/Queue").then((m) => ({ default: m.OfficerAssignments })),
);
const OfficerApplicationDetail = lazy(() =>
  import("@/pages/officer/ApplicationDetail").then((m) => ({ default: m.OfficerApplicationDetail })),
);
const InspectionWorkflow = lazy(() =>
  import("@/pages/officer/Inspection").then((m) => ({ default: m.InspectionWorkflow })),
);
const OfficerCertificates = lazy(() =>
  import("@/pages/officer/Certificates").then((m) => ({ default: m.OfficerCertificates })),
);
const OfficerCertificateDetail = lazy(() =>
  import("@/pages/officer/Certificates").then((m) => ({ default: m.OfficerCertificateDetail })),
);

// ---- Admin (lazy) ----
const AdminDashboardPage = lazy(() => import("@/pages/admin/Dashboard"));
const AdminInstruments = lazy(() => import("@/pages/admin/AdminInstruments"));
const AdminApplications = lazy(() => import("@/pages/admin/Applications"));
const AdminApplicationDetail = lazy(() => import("@/pages/admin/ApplicationDetail"));
const AdminCertificates = lazy(() =>
  import("@/pages/admin/Certificates").then((m) => ({ default: m.AdminCertificates })),
);
const AdminCertificateDetail = lazy(() =>
  import("@/pages/admin/Certificates").then((m) => ({ default: m.AdminCertificateDetail })),
);
const AdminUsers = lazy(() => import("@/pages/admin/Users"));
const AdminAuditLog = lazy(() => import("@/pages/admin/AuditLog"));

function PageFallback() {
  return <div className="p-8 text-sm text-gray-500">Loading…</div>;
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
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/two-step" element={<TwoFactor />} />
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
              <Suspense fallback={<PageFallback />}>
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
              </Suspense>
            </AppShell>
          </ProtectedRoute>
        }
      />

      <Route
        path="/app/lmo/*"
        element={
          <ProtectedRoute roles={["lmo"]}>
            <AppShell>
              <Suspense fallback={<PageFallback />}>
                <OfficerRoutes role="lmo" />
              </Suspense>
            </AppShell>
          </ProtectedRoute>
        }
      />

      <Route
        path="/app/gatc/*"
        element={
          <ProtectedRoute roles={["gatc"]}>
            <AppShell>
              <Suspense fallback={<PageFallback />}>
                <OfficerRoutes role="gatc" />
              </Suspense>
            </AppShell>
          </ProtectedRoute>
        }
      />

      <Route
        path="/app/admin/*"
        element={
          <ProtectedRoute roles={["admin"]}>
            <AppShell>
              <Suspense fallback={<PageFallback />}>
                <Routes>
                  <Route index element={<AdminDashboardPage />} />
                  <Route path="users" element={<AdminUsers />} />
                  <Route path="instruments" element={<AdminInstruments />} />
                  <Route path="applications" element={<AdminApplications />} />
                  <Route path="applications/:id" element={<AdminApplicationDetail />} />
                  <Route path="certificates" element={<AdminCertificates />} />
                  <Route path="certificates/:id" element={<AdminCertificateDetail />} />
                  <Route path="audit-log" element={<AdminAuditLog />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </AppShell>
          </ProtectedRoute>
        }
      />

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}