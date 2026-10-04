/** FAQ shown on /how-it-works. The FAQPage JSON-LD is built from this same list, so markup always matches visible text. */
export interface FaqItem {
  question: string;
  answer: string;
}

export const HOW_IT_WORKS_FAQ: FaqItem[] = [
  {
    question: "Do I need an account to verify a legal metrology certificate?",
    answer:
      "No. Anyone can check a certificate on the MaapSetu verify page by entering the certificate ID or scanning the QR code printed on it. An account is only needed to register instruments and apply for verification.",
  },
  {
    question: "Who can register weighing and measuring instruments on MaapSetu?",
    answer:
      "Business owners create their own accounts and register their instruments. Legal Metrology Officers and approved test centres are added by an administrator, so their accounts are not open to self-registration.",
  },
  {
    question: "What happens after I submit an instrument for verification?",
    answer:
      "An officer or approved test centre claims the application, inspects the instrument and records the result with photo evidence. Each status change is saved, so you can follow the application from submission to outcome.",
  },
  {
    question: "How long is a digital verification certificate valid?",
    answer:
      "A MaapSetu certificate is valid for one year from the day it is issued, and it shows its own valid-until date. MaapSetu marks certificates as expiring soon and then expired, so you can apply for re-verification in time.",
  },
  {
    question: "Can I verify water, gas or energy meters as well as weighing machines?",
    answer:
      "Yes. Besides scales, weighbridges and fuel dispensing units, you can register water meters, gas meters, energy meters and flow meters, along with other measuring instruments such as tape measures and thermometers. The About page lists every instrument type currently available.",
  },
  {
    question: "How can I tell that a QR certificate is genuine?",
    answer:
      "Scanning the QR code opens the public verify page, which looks the certificate up live in the MaapSetu registry and shows the instrument, owner, verification date and validity. If no record is found, the certificate was not issued through MaapSetu.",
  },
];
