import { Button } from "@/components/ui/Button";

interface LogoutConfirmationDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export function LogoutConfirmationDialog({ open, onClose, onConfirm }: LogoutConfirmationDialogProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/45 p-4 sm:items-center" onClick={onClose} onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <div
        className="w-full max-w-sm overflow-hidden rounded-xl border border-line bg-white shadow-xl"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="logout-confirm-title"
      >
        <div className="flex flex-col items-center justify-center gap-3 p-6 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-teal-50 text-xl font-bold text-teal">
            ?
          </div>
          <h2 id="logout-confirm-title" className="text-base font-semibold text-ink">
            Sign out of MaapSetu?
          </h2>
          <p className="text-sm font-medium text-slate-500">
            You can sign back in at any time.
          </p>
        </div>

        <div className="grid w-full grid-cols-2 divide-x divide-line border-t border-line">
          <Button variant="ghost" className="h-12 flex-1 rounded-none border-0 p-0" onClick={onClose} autoFocus>
            Stay signed in
          </Button>
          <Button variant="ghost" className="h-12 flex-1 rounded-none border-0 p-0" onClick={onConfirm}>
            Sign out
          </Button>
        </div>
      </div>
    </div>
  );
}
