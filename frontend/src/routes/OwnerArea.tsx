import { Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { Seo } from "@/seo/Seo";
import { NotFound } from "@/pages/Misc";
import OwnerDashboardPage from "@/pages/owner/Dashboard";
import OwnerInstruments from "@/pages/owner/Instruments";
import InstrumentDetail from "@/pages/owner/InstrumentDetail";
import RegisterInstrument from "@/pages/owner/RegisterInstrument";
import OwnerApplications from "@/pages/owner/Applications";
import OwnerApplicationDetail from "@/pages/owner/ApplicationDetail";
import NewApplication from "@/pages/owner/NewApplication";
import { OwnerCertificates, OwnerCertificateDetail } from "@/pages/owner/Certificates";

/** Code-split: everything under /app/owner/* (loaded with React.lazy from App.tsx). */
export default function OwnerArea() {
  return (
    <AppShell>
      <Seo route="/app" />
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
  );
}
