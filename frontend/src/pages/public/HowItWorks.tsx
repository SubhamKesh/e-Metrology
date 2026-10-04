import { Link } from "react-router-dom";
import { PublicLayout } from "@/components/layout/PublicLayout";
import { ButtonLink } from "@/components/ui/Button";
import { STEPS } from "@/content/steps";
import { HOW_IT_WORKS_FAQ } from "@/content/faq";
import { Seo } from "@/seo/Seo";

export default function HowItWorks() {
  return (
    <PublicLayout>
      <Seo route="/how-it-works" />

      <section className="border-b border-line">
        <div className="container-page py-12 sm:py-16">
          <p className="eyebrow">Legal Metrology · Process</p>
          <h1 className="mt-4 max-w-3xl font-display text-4xl font-semibold leading-tight tracking-tight text-ink sm:text-5xl">
            How Legal Metrology verification works on MaapSetu
          </h1>
          <p className="mt-5 max-w-prose text-base text-slate-600 sm:text-lg">
            Weighing and measuring instruments used in trade have to be verified, and that proof has to be easy to
            check. MaapSetu moves the whole process online: from registering an instrument to a digital verification
            certificate that anyone in India can confirm with its QR code.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <ButtonLink to="/register" size="lg">
              Register your business
            </ButtonLink>
            <ButtonLink to="/verify" size="lg" variant="secondary">
              Verify a certificate
            </ButtonLink>
          </div>
        </div>
      </section>

      <section aria-labelledby="steps-heading" className="py-14 sm:py-20">
        <div className="container-page">
          <h2 id="steps-heading" className="font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
            From instrument to verified certificate in five steps
          </h2>
          <ol className="mt-10 max-w-3xl space-y-6">
            {STEPS.map((s, i) => (
              <li key={s.title} className="flex gap-4 rounded-xl border border-line bg-white p-5 shadow-panel sm:p-6">
                <span
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink font-display text-base text-paper"
                  aria-hidden="true"
                >
                  {i + 1}
                </span>
                <div>
                  <h3 className="font-display text-xl text-ink">
                    <span className="sr-only">Step {i + 1}: </span>
                    {s.title}
                  </h3>
                  <p className="mt-2 text-sm text-slate-600 sm:text-base">{s.detail}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section aria-labelledby="faq-heading" className="border-t border-line bg-paper2/60 py-14 sm:py-20">
        <div className="container-page">
          <h2 id="faq-heading" className="font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
            Frequently asked questions
          </h2>
          <div className="mt-8 max-w-3xl space-y-4">
            {HOW_IT_WORKS_FAQ.map((f) => (
              <div key={f.question} className="rounded-xl border border-line bg-white p-5 shadow-panel sm:p-6">
                <h3 className="font-display text-lg text-ink">{f.question}</h3>
                <p className="mt-2 text-sm text-slate-600 sm:text-base">{f.answer}</p>
              </div>
            ))}
          </div>
          <p className="mt-8 text-sm text-slate-600">
            New to Legal Metrology? Read{" "}
            <Link to="/about" className="font-medium text-teal underline underline-offset-2">
              about MaapSetu and Legal Metrology in India
            </Link>
            , or go straight to{" "}
            <Link to="/verify" className="font-medium text-teal underline underline-offset-2">
              certificate verification
            </Link>
            .
          </p>
        </div>
      </section>
    </PublicLayout>
  );
}
