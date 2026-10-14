import { useInstallPrompt } from "@/lib/pwa";

/** Dismissible "install the app" banner for signed-in users. */
export function InstallBanner() {
  const { canInstall, showIosHint, install, dismiss } = useInstallPrompt();
  if (!canInstall && !showIosHint) return null;

  return (
    <div
      role="region"
      aria-label="Install app"
      className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-line bg-white px-4 py-3 text-sm shadow-sm"
    >
      <p className="text-ink">
        {canInstall
          ? "Install MaapSetu on your device for quick access."
          : "To install: tap the Share button, then “Add to Home Screen”."}
      </p>
      <div className="flex shrink-0 items-center gap-2">
        {canInstall && (
          <button
            type="button"
            onClick={install}
            className="rounded-md bg-teal px-3 py-1.5 font-medium text-white hover:bg-teal-600"
          >
            Install
          </button>
        )}
        <button type="button" onClick={dismiss} className="px-2 py-1.5 text-slate-500 hover:text-ink" aria-label="Dismiss">
          Not now
        </button>
      </div>
    </div>
  );
}
