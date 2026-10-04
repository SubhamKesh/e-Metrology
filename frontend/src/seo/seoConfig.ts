/**
 * Single source of truth for SEO.
 *
 * Read by: the <Seo/> component (client), the build-time prerender script
 * (static HTML heads, sitemap.xml, robots.txt, 404.html) and the JSON-LD builders.
 * Keep this file free of DOM / Node APIs so it works in all three places.
 */
import { HOW_IT_WORKS_FAQ } from "@/content/faq";

export const SITE = {
  name: "MaapSetu",
  /** Other names the product is known by. Must also appear in visible page text (footer, /about). */
  alternateNames: ["e-Metrology", "MaapSetu e-Metrology"],
  locale: "en-IN",
  /** Path (relative to the site origin) of the default social preview, 1200x630. */
  defaultOgImage: "/og-image.png",
  ogImageWidth: 1200,
  ogImageHeight: 630,
  ogImageAlt: "MaapSetu – digital Legal Metrology verification for weighing and measuring instruments in India",
  logoPath: "/apple-touch-icon.png",
  themeColor: "#1F5F5B",
  twitterCard: "summary_large_image",
} as const;

export type ChangeFreq = "daily" | "weekly" | "monthly" | "yearly";

export interface RouteSeo {
  /** Final <title>. Keep <= 60 chars, brand at the end (home leads with the brand). */
  title: string;
  /** Meta description. Keep 120-160 chars. */
  description: string;
  /** false => `noindex, nofollow`, and excluded from the sitemap. */
  indexable: boolean;
  ogType: "website" | "article";
  /** Canonical path. Only meaningful for indexable routes. */
  path?: string;
  /** Sitemap hints (indexable routes only). */
  changefreq?: ChangeFreq;
  priority?: number;
  /** YYYY-MM-DD. Bump when the page content meaningfully changes. */
  lastmod?: string;
  /** Structured data; must describe content that is visible on the page. */
  jsonLd?: (origin: string) => Record<string, unknown>[];
}

export const SEO_ROUTES = {
  "/": {
    title: "MaapSetu e-Metrology – Legal Metrology Verification, India",
    description:
      "MaapSetu (e-Metrology) helps Indian businesses register scales and meters, apply for Legal Metrology verification online and get QR-verifiable certificates.",
    indexable: true,
    ogType: "website",
    path: "/",
    changefreq: "weekly",
    priority: 1.0,
    lastmod: "2026-09-30",
    jsonLd: (origin) => [
      {
        "@context": "https://schema.org",
        "@type": "Organization",
        name: SITE.name,
        alternateName: [...SITE.alternateNames],
        url: `${origin}/`,
        logo: `${origin}${SITE.logoPath}`,
      },
      {
        "@context": "https://schema.org",
        "@type": "WebSite",
        name: SITE.name,
        alternateName: [...SITE.alternateNames],
        url: `${origin}/`,
        inLanguage: SITE.locale,
      },
    ],
  },
  "/verify": {
    title: "Verify a Legal Metrology Certificate | MaapSetu",
    description:
      "Check if a Legal Metrology certificate is genuine. Enter the certificate ID or scan its QR code to see the instrument, owner and validity. No account needed.",
    indexable: true,
    ogType: "website",
    path: "/verify",
    changefreq: "monthly",
    priority: 0.9,
    lastmod: "2026-09-30",
  },
  "/register": {
    title: "Register for Instrument Verification | MaapSetu",
    description:
      "Create a MaapSetu account to register weighing and measuring instruments, request Legal Metrology verification online and track each application to its outcome.",
    indexable: true,
    ogType: "website",
    path: "/register",
    changefreq: "yearly",
    priority: 0.7,
    lastmod: "2026-09-30",
  },
  "/how-it-works": {
    title: "How Legal Metrology Verification Works | MaapSetu",
    description:
      "See the five steps from registering a weighing machine or meter to a QR-verifiable digital certificate, plus answers to common verification questions.",
    indexable: true,
    ogType: "article",
    path: "/how-it-works",
    changefreq: "monthly",
    priority: 0.8,
    lastmod: "2026-09-30",
    jsonLd: () => [
      {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        mainEntity: HOW_IT_WORKS_FAQ.map((f) => ({
          "@type": "Question",
          name: f.question,
          acceptedAnswer: { "@type": "Answer", text: f.answer },
        })),
      },
    ],
  },
  "/about": {
    title: "About MaapSetu e-Metrology and Legal Metrology India",
    description:
      "MaapSetu (e-Metrology) is a digital platform for Legal Metrology verification of weighing machines, fuel dispensers and meters used in trade across India.",
    indexable: true,
    ogType: "website",
    path: "/about",
    changefreq: "yearly",
    priority: 0.6,
    lastmod: "2026-09-30",
  },

  // ---- noindex routes ----------------------------------------------------
  "/login": {
    title: "Sign In | MaapSetu",
    description: "Sign in to your MaapSetu account to manage Legal Metrology instruments, applications and certificates.",
    indexable: false,
    ogType: "website",
  },
  "/forgot-password": {
    title: "Reset Your Password | MaapSetu",
    description: "Reset the password of your MaapSetu account with a one-time code sent to your email.",
    indexable: false,
    ogType: "website",
  },
  "/two-step": {
    title: "Two-Step Verification | MaapSetu",
    description: "Complete two-step verification to sign in to your MaapSetu officer or administrator account.",
    indexable: false,
    ogType: "website",
  },
  "/pending": {
    title: "Account Pending Approval | MaapSetu",
    description: "Your MaapSetu account is waiting for administrator approval before you can sign in.",
    indexable: false,
    ogType: "website",
  },
  "/change-password": {
    title: "Change Password | MaapSetu",
    description: "Set a new password for your MaapSetu account.",
    indexable: false,
    ogType: "website",
  },
  "/unauthorized": {
    title: "Access Denied | MaapSetu",
    description: "This section of MaapSetu is not available for your account role.",
    indexable: false,
    ogType: "website",
  },
  "/verify/:certId": {
    title: "Certificate Verification Result | MaapSetu",
    description: "Live verification result for a MaapSetu Legal Metrology certificate.",
    indexable: false,
    ogType: "website",
  },
  shell: {
    title: "MaapSetu",
    description: "MaapSetu – digital Legal Metrology verification and certification for weighing and measuring instruments in India.",
    indexable: false,
    ogType: "website",
  },
  "/app": {
    title: "Dashboard | MaapSetu",
    description: "Signed-in area of MaapSetu for instrument owners, officers and administrators.",
    indexable: false,
    ogType: "website",
  },
  notFound: {
    title: "Page Not Found | MaapSetu",
    description: "The page you were looking for does not exist or has moved.",
    indexable: false,
    ogType: "website",
  },
} as const satisfies Record<string, RouteSeo>;

export type SeoRouteKey = keyof typeof SEO_ROUTES;

/** Routes that are prerendered to full static HTML (content included). */
export const PRERENDER_ROUTES = ["/", "/verify", "/register", "/how-it-works", "/about"] as const satisfies readonly SeoRouteKey[];

/**
 * Static client-only routes. These get a static HTML file with the correct noindex <head>
 * and an empty root (the app renders on the client), so raw HTML never carries home-page metadata.
 */
export const SHELL_ROUTES = [
  "/login",
  "/forgot-password",
  "/two-step",
  "/pending",
  "/change-password",
  "/unauthorized",
] as const satisfies readonly SeoRouteKey[];

export function indexableRoutes(): { key: SeoRouteKey; seo: RouteSeo }[] {
  return (Object.keys(SEO_ROUTES) as SeoRouteKey[])
    .map((key) => ({ key, seo: SEO_ROUTES[key] as RouteSeo }))
    .filter((r) => r.seo.indexable && r.seo.path);
}
