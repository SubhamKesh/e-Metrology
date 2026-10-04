import { Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { Seo } from "@/seo/Seo";
import OfficerDashboardPage from "@/pages/officer/Dashboard";
import { OfficerQueue, OfficerAssignments } from "@/pages/officer/Queue";
import { OfficerApplicationDetail } from "@/pages/officer/ApplicationDetail";
import { InspectionWorkflow } from "@/pages/officer/Inspection";
import { OfficerCertificates, OfficerCertificateDetail } from "@/pages/officer/Certificates";

/** Code-split: everything under /app/lmo/* and /app/gatc/* (loaded with React.lazy from App.tsx). */
export default function OfficerArea({ role }: { role: "lmo" | "gatc" }) {
  return (
    <AppShell>
      <Seo route="/app" />
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
    </AppShell>
  );
}
