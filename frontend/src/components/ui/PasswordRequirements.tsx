import { PASSWORD_RULES } from "@/lib/validation";

/** Live checklist of the password policy. Shows nothing until the user
 *  starts typing so an empty form isn't a wall of red. */
export function PasswordRequirements({ password }: { password: string }) {
  if (!password) {
    return (
      <p className="text-xs text-slate-500">
        Use 8–64 characters with an uppercase letter, a lowercase letter, a number and a special character.
      </p>
    );
  }
  return (
    <ul aria-label="Password requirements" className="grid gap-1 text-xs sm:grid-cols-2">
      {PASSWORD_RULES.map((rule) => {
        const ok = rule.test(password);
        return (
          <li key={rule.id} className={ok ? "text-success" : "text-slate-500"}>
            <span aria-hidden="true">{ok ? "✓" : "○"}</span> {rule.label}
            <span className="sr-only">{ok ? " — met" : " — not met yet"}</span>
          </li>
        );
      })}
    </ul>
  );
}
