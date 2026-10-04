/** The five-step process. `body` is the short landing-page copy, `detail` the fuller /how-it-works copy. */
export interface Step {
  title: string;
  body: string;
  detail: string;
}

export const STEPS: Step[] = [
  {
    title: "Register instrument",
    body: "Business owners add instrument details and location.",
    detail:
      "A business owner creates an account and registers each weighing or measuring instrument: the instrument type, manufacturer, model, serial number and where it is installed. MaapSetu gives every instrument a unique instrument ID (UIID), so the same record is used for every later verification and renewal.",
  },
  {
    title: "Submit verification",
    body: "Request verification for a registered instrument.",
    detail:
      "The owner picks a registered instrument and submits a verification request online. The application is tied to the state and district of the instrument, so it reaches the officers responsible for that area instead of a general queue.",
  },
  {
    title: "Inspection",
    body: "An officer or approved test centre inspects it and records the result.",
    detail:
      "A Legal Metrology Officer or an approved test centre in that jurisdiction claims the application, looks up the instrument by its QR code or UIID, inspects it and records the outcome together with photo evidence. Every status change is saved in the application history.",
  },
  {
    title: "Certification",
    body: "A passed inspection produces a digital certificate.",
    detail:
      "When an instrument passes, the system generates the digital verification certificate as a PDF with a unique certificate ID and a QR code. The owner can view or download it at any time, and certificates are not edited by hand.",
  },
  {
    title: "Public verification",
    body: "Anyone can confirm the certificate by ID or QR code.",
    detail:
      "Scanning the QR code, or entering the certificate ID on the verify page, looks the certificate up live in the MaapSetu registry. No account is needed, and the result shows whether the certificate is valid, expiring or expired so renewals can be planned ahead.",
  },
];
