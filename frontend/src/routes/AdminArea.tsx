import { Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { Seo } from "@/seo/Seo";
import { NotFound } from "@/pages/Misc";
import AdminDashboardPage from "@/pages/admin/Dashboard";
import AdminInstruments from "@/pages/admin/AdminInstruments";
import AdminApplications from "@/pages/admin/Applications";
import AdminApplicationDetail from "@/pages/admin/ApplicationDetail";
import { AdminCertificates, AdminCertificateDetail } from "@/pages/admin/Certificates";
import AdminUsers from "@/pages/admin/Users";

/** Code-split: everything under /app/admin/* (loaded with React.lazy from App.tsx). */
export default function AdminArea() {
  return (
    <AppShell>
      <Seo route="/app" />
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
  );
}
