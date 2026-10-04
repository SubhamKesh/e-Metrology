import { Link } from "react-router-dom";
import { PublicLayout } from "@/components/layout/PublicLayout";
import { ButtonLink } from "@/components/ui/Button";
import { INSTRUMENT_GROUPS } from "@/content/instruments";
import { Seo } from "@/seo/Seo";

const AUDIENCES = [
  {
    title: "Business owners",
    body: "Shops, manufacturers and service providers that use weighing or measuring instruments for trade register them, apply for verification and keep track of when each certificate expires.",
  },
  {
    title: "Legal Metrology Officers and test centres",
    body: "Officers and approved test centres see the applications in their own jurisdiction, record inspection results with photo evidence and issue certificates from the same system.",
  },
  {
    title: "Administrators",
    body: "Administrators approve accounts, set up officer access and get a system-wide view of applications and certificates.",
  },
  {
    title: "Consumers and auditors",
    body: "Anyone can check a certificate by ID or QR code, without an account, to confirm that an instrument has been verified and is still within its validity period.",
  },
];

export default function About() {
  return (
    <PublicLayout>
      <Seo route="/about" />

      <section className="border-b border-line">
        <div className="container-page py-12 sm:py-16">
          <p className="eyebrow">About</p>
          <h1 className="mt-4 max-w-3xl font-display text-4xl font-semibold leading-tight tracking-tight text-ink sm:text-5xl">
            About MaapSetu: digital Legal Metrology verification
          </h1>
          <p className="mt-5 max-w-prose text-base text-slate-600 sm:text-lg">
            MaapSetu (e-Metrology) joins the Hindi words <em>maap</em> (measure) and <em>setu</em> (bridge). It is a web
            platform that connects the people who own weighing and measuring instruments, the officers who inspect them and the
            public who rely on them, through one verifiable record.
          </p>
        </div>
      </section>

      <section aria-labelledby="what-heading" className="py-14 sm:py-16">
        <div className="container-page max-w-3xl">
          <h2 id="what-heading" className="font-display text-3xl font-semibold tracking-tight text-ink">
            What MaapSetu does
          </h2>
          <p className="mt-4 text-base text-slate-600">
            MaapSetu replaces paperwork and in-person queues with an online workflow. Owners register instruments and
            request verification, officers or approved test centres inspect them and record the result, and a passed
            inspection produces a digital verification certificate. Every certificate carries a unique ID and a QR code
            that opens a public verification page, and every application keeps a status history from submission to
            outcome.
          </p>
          <p className="mt-4 text-base text-slate-600">
            Want the details? See{" "}
            <Link to="/how-it-works" className="font-medium text-teal underline underline-offset-2">
              how the five-step verification process works
            </Link>
            .
          </p>
        </div>
      </section>

      <section aria-labelledby="who-heading" className="border-y border-line bg-paper2/60 py-14 sm:py-16">
        <div className="container-page">
          <h2 id="who-heading" className="font-display text-3xl font-semibold tracking-tight text-ink">
            Who MaapSetu is for
          </h2>
          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            {AUDIENCES.map((a) => (
              <div key={a.title} className="rounded-xl border border-line bg-white p-5 shadow-panel sm:p-6">
                <h3 className="font-display text-lg text-ink">{a.title}</h3>
                <p className="mt-2 text-sm text-slate-600">{a.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section aria-labelledby="instruments-heading" className="py-14 sm:py-16">
        <div className="container-page">
          <h2 id="instruments-heading" className="font-display text-3xl font-semibold tracking-tight text-ink">
            Weighing machines, meters and other instruments you can register
          </h2>
          <p className="mt-4 max-w-3xl text-base text-slate-600">
            These are the instrument types currently available for Legal Metrology verification on MaapSetu.
          </p>
          <div className="mt-8 grid gap-4 md:grid-cols-3">
            {INSTRUMENT_GROUPS.map((g) => (
              <div key={g.title} className="rounded-xl border border-line bg-white p-5 shadow-panel sm:p-6">
                <h3 className="font-display text-lg text-ink">{g.title}</h3>
                <ul className="mt-3 space-y-1.5 text-sm text-slate-600">
                  {g.items.map((i) => (
                    <li key={i}>{i}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section aria-labelledby="context-heading" className="border-t border-line bg-paper2/60 py-14 sm:py-16">
        <div className="container-page max-w-3xl">
          <h2 id="context-heading" className="font-display text-3xl font-semibold tracking-tight text-ink">
            Legal Metrology in India
          </h2>
          <p className="mt-4 text-base text-slate-600">
            Legal Metrology is the part of weights and measures law that protects buyers and sellers when goods are
            sold by weight, volume or length. In India it is governed by the Legal Metrology Act, 2009 and the rules
            made under it. At the national level the subject sits with the Department of Consumer Affairs, Government of
            India, and the Act is enforced by the Legal Metrology departments of the state and union territory
            governments.
          </p>
          <p className="mt-4 text-base text-slate-600">
            In practice this means weighing and measuring instruments used in trade, such as shop scales, weighbridges
            and fuel dispensers, must be verified and stamped, and verified again at regular intervals. Verification is
            carried out by Legal Metrology Officers or by government-approved test centres.
          </p>
          <p className="mt-4 text-base text-slate-600">
            MaapSetu is a digital workflow for this process. The legal requirements themselves, including which
            instruments need verification and how often, come from the Act, its rules and your state Legal Metrology
            department.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <ButtonLink to="/register">Create an account</ButtonLink>
            <ButtonLink to="/verify" variant="secondary">
              Verify a certificate
            </ButtonLink>
          </div>
        </div>
      </section>
    </PublicLayout>
  );
}
