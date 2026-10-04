import { Suspense, lazy } from "react";
import { Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "@/routes/ProtectedRoute";

import Login from "@/pages/auth/Login";
import Register from "@/pages/auth/Register";
import PendingApproval from "@/pages/auth/PendingApproval";
import ForgotPassword from "@/pages/auth/ForgotPassword";
import TwoFactor from "@/pages/auth/TwoFactor";
import ChangePassword from "@/pages/auth/ChangePassword";
import VerifyCertificate from "@/pages/public/VerifyCertificate";
import Landing from "@/pages/public/Landing";
import HowItWorks from "@/pages/public/HowItWorks";
import About from "@/pages/public/About";
import { Unauthorized, NotFound } from "@/pages/Misc";

// Signed-in areas are code-split so the public bundle (what crawlers and first-time
// visitors download) does not include dashboards, tables and inspection workflows.
const OwnerArea = lazy(() => import("@/routes/OwnerArea"));
const OfficerArea = lazy(() => import("@/routes/OfficerArea"));
const AdminArea = lazy(() => import("@/routes/AdminArea"));

function PageSpinner() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-paper">
      <span className="h-6 w-6 animate-spin rounded-full border-2 border-teal border-t-transparent" />
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<PageSpinner />}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/how-it-works" element={<HowItWorks />} />
        <Route path="/about" element={<About />} />
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
              <OwnerArea />
            </ProtectedRoute>
          }
        />

        <Route
          path="/app/lmo/*"
          element={
            <ProtectedRoute roles={["lmo"]}>
              <OfficerArea role="lmo" />
            </ProtectedRoute>
          }
        />

        <Route
          path="/app/gatc/*"
          element={
            <ProtectedRoute roles={["gatc"]}>
              <OfficerArea role="gatc" />
            </ProtectedRoute>
          }
        />

        <Route
          path="/app/admin/*"
          element={
            <ProtectedRoute roles={["admin"]}>
              <AdminArea />
            </ProtectedRoute>
          }
        />

        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
}
