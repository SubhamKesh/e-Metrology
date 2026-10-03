import { type FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AdminUsersApi, type CreateOfficerPayload } from "@/lib/endpoints";
import { ApiError } from "@/lib/api";
import type { User } from "@/lib/types";
import { Panel } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { TextInput, SelectInput } from "@/components/ui/Field";
import { DataTable } from "@/components/ui/DataTable";
import { ErrorState } from "@/components/ui/States";
import { Badge } from "@/components/ui/StatusBadge";
import { JurisdictionText } from "@/components/ui/JurisdictionText";
import { useGeoDistricts, useGeoStates } from "@/hooks/useData";

const USER_STATUS_TONE = {
  active: "success",
  pending: "warning",
  rejected: "danger",
} as const;

function UserStatusBadge({ status }: { status: User["status"] }) {
  return <Badge tone={USER_STATUS_TONE[status]}>{status[0].toUpperCase() + status.slice(1)}</Badge>;
}

const ROLE_OPTIONS = [
  { value: "lmo", label: "Legal Metrology Officer" },
  { value: "gatc", label: "GATC" },
];

export default function AdminUsers() {
  const qc = useQueryClient();
  const { data: officers, isLoading, error, refetch } = useQuery<User[]>({
    queryKey: ["admin", "officers"],
    queryFn: () => AdminUsersApi.listOfficers(),
  });

  const [form, setForm] = useState({
    name: "",
    email: "",
    role: "lmo" as CreateOfficerPayload["role"],
    org_name: "",
    contact: "",
    state_code: "",
    district_code: "",
  });
  // Separate from district_code="" (nothing picked yet) — this is an
  // intentional choice to scope the officer to the whole state, matching
  // jurisdiction.district_code=null on the backend (the shape a
  // GATC/state-controller account uses; see middleware/auth.py's
  // jurisdiction_filter()).
  const [stateLevelOnly, setStateLevelOnly] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [created, setCreated] = useState<{ email: string; temp_password: string; emailed: boolean } | null>(
    null,
  );

  const { data: states, isLoading: statesLoading } = useGeoStates();
  const { data: districts, isLoading: districtsLoading } = useGeoDistricts(form.state_code || undefined);
  const stateOptions = useMemo(() => (states ?? []).map((s) => ({ value: s.code, label: s.name })), [states]);
  const districtOptions = useMemo(() => (districts ?? []).map((d) => ({ value: d.code, label: d.name })), [districts]);

  const createOfficer = useMutation({
    mutationFn: (body: CreateOfficerPayload) => AdminUsersApi.createOfficer(body),
    onSuccess: (res) => {
      setCreated({ email: res.user.email, temp_password: res.temp_password, emailed: res.emailed });
      setForm({ name: "", email: "", role: "lmo", org_name: "", contact: "", state_code: "", district_code: "" });
      setStateLevelOnly(false);
      qc.invalidateQueries({ queryKey: ["admin", "officers"] });
    },
    onError: (err) => {
      setFormError(err instanceof ApiError ? err.message : "Couldn't create that account. Try again.");
    },
  });

  // Admin-initiated password reset (officers can't self-reset). The temp
  // password comes back once, here, and is also emailed to the officer.
  const [reset, setReset] = useState<{ email: string; temp_password: string; emailed: boolean } | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);
  const resetPassword = useMutation({
    mutationFn: (id: string) => AdminUsersApi.resetPassword(id),
    onSuccess: (res) => {
      setResetError(null);
      setReset({ email: res.user.email, temp_password: res.temp_password, emailed: res.emailed });
    },
    onError: (err) => {
      setReset(null);
      setResetError(err instanceof ApiError ? err.message : "Couldn't reset that password. Try again.");
    },
  });

  function onResetPassword(u: User) {
    const ok = window.confirm(
      `Reset the password for ${u.name} (${u.email})?\n\nThey will be signed out everywhere and must set a new password at next sign-in.`,
    );
    if (ok) resetPassword.mutate(u.id);
  }

  // Admin-initiated two-step reset: for an officer who lost their phone or
  // used up their recovery codes. They're signed out and must enrol a new
  // authenticator at their next sign-in.
  const [mfaNotice, setMfaNotice] = useState<string | null>(null);
  const resetMfa = useMutation({
    mutationFn: (id: string) => AdminUsersApi.resetMfa(id),
    onSuccess: (res) => {
      setResetError(null);
      setMfaNotice(`Two-step verification cleared for ${res.email}. They'll set up a new authenticator at their next sign-in.`);
      qc.invalidateQueries({ queryKey: ["admin", "officers"] });
    },
    onError: (err) => {
      setMfaNotice(null);
      setResetError(err instanceof ApiError ? err.message : "Couldn't reset two-step verification. Try again.");
    },
  });

  function onResetMfa(u: User) {
    const ok = window.confirm(
      `Reset two-step verification for ${u.name} (${u.email})?\n\nTheir authenticator app and recovery codes stop working, and they're signed out everywhere. They'll set up a new one at next sign-in.`,
    );
    if (ok) resetMfa.mutate(u.id);
  }

  const toggleStatus = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "approve" | "reject" }) =>
      action === "approve" ? AdminUsersApi.approve(id) : AdminUsersApi.reject(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "officers"] }),
  });

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  // Changing the state clears any previously-selected district — it
  // belonged to a different state's list and is no longer valid.
  function setStateCode(stateCode: string) {
    setForm((f) => ({ ...f, state_code: stateCode, district_code: "" }));
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setCreated(null);
    if (!stateLevelOnly && !form.district_code) {
      setFormError("Pick a district, or check \"state-level officer\" if this account isn't scoped to one.");
      return;
    }
    const { state_code, district_code, ...rest } = form;
    createOfficer.mutate({
      ...rest,
      jurisdiction: { state_code, district_code: stateLevelOnly ? null : district_code },
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl text-ink">Officer accounts</h1>
        <p className="mt-1 text-sm text-slate-500">
          lmo and gatc accounts are invite-only. Create an account here to let a specific officer sign in — there's
          no public sign-up for these roles.
        </p>
      </div>

      <Panel className="p-5">
        <h2 className="font-display text-lg text-ink">Add an officer</h2>
        <form onSubmit={onSubmit} className="mt-4 grid gap-4 sm:grid-cols-2">
          <TextInput label="Full name" required value={form.name} onChange={(e) => set("name", e.target.value)} />
          <TextInput
            label="Email"
            type="email"
            required
            value={form.email}
            onChange={(e) => set("email", e.target.value)}
          />
          <SelectInput
            label="Role"
            required
            value={form.role}
            onChange={(e) => set("role", e.target.value as CreateOfficerPayload["role"])}
            options={ROLE_OPTIONS}
          />
          <TextInput
            label="Organisation name"
            value={form.org_name}
            onChange={(e) => set("org_name", e.target.value)}
          />
          <TextInput
            label="Contact number"
            type="tel"
            inputMode="numeric"
            value={form.contact}
            onChange={(e) => set("contact", e.target.value)}
          />
          <SelectInput
            label="State / UT"
            required
            placeholder={statesLoading ? "Loading states…" : "Select a state or UT"}
            options={stateOptions}
            value={form.state_code}
            onChange={(e) => setStateCode(e.target.value)}
          />
          <div>
            <SelectInput
              label="District"
              required={!stateLevelOnly}
              disabled={stateLevelOnly || !form.state_code}
              placeholder={
                !form.state_code ? "Select a state first" : districtsLoading ? "Loading districts…" : "Select a district"
              }
              options={districtOptions}
              value={form.district_code}
              onChange={(e) => set("district_code", e.target.value)}
            />
            <label className="mt-2 flex items-center gap-2 text-xs text-slate-500">
              <input
                type="checkbox"
                checked={stateLevelOnly}
                onChange={(e) => setStateLevelOnly(e.target.checked)}
              />
              State-level officer (e.g. GATC) — not scoped to one district
            </label>
          </div>
          <div className="flex items-end sm:col-span-2">
            <Button type="submit" loading={createOfficer.isPending} className="w-full sm:w-auto">
              Create account
            </Button>
          </div>
        </form>
        {formError && <p className="mt-3 text-sm text-danger">{formError}</p>}
        {created && (
          <div className="mt-4 rounded-md border border-teal/30 bg-teal/5 p-4 text-sm">
            <p className="font-medium text-ink">Account created for {created.email}</p>
            {created.emailed ? (
              <p className="mt-1 text-slate-600">
                Login credentials are being emailed to them directly. The temporary password is shown below only as
                a backup, in case the email doesn't arrive.
              </p>
            ) : (
              <p className="mt-1 text-slate-600">
                Couldn't send the credentials email (SMTP isn't configured or the send failed) — share the
                temporary password below with them yourself.
              </p>
            )}
            <p className="mt-2 text-slate-600">
              Temporary password: <code className="rounded bg-white px-1.5 py-0.5">{created.temp_password}</code>
            </p>
            <p className="mt-1 text-slate-500">
              It won't be shown again after you leave this page. They'll be required to set their own password the
              first time they sign in.
            </p>
          </div>
        )}
      </Panel>

      <Panel className="p-5">
        <h2 className="font-display text-lg text-ink">All officer accounts</h2>
        <p className="mt-1 text-xs text-slate-500">
          Officers can't reset their own password. If one is locked out or forgets it, use "Reset password" — they'll
          get a temporary password by email. Officers also sign in with a code from an authenticator app; if one loses
          their phone or runs out of recovery codes, use "Reset 2-step" so they can set up a new one. Suspending an
          officer signs them out immediately.
        </p>
        {resetError && <p className="mt-3 text-sm text-danger">{resetError}</p>}
        {mfaNotice && (
          <p role="status" className="mt-3 rounded-md bg-teal-50 px-3 py-2 text-sm text-teal-700">
            {mfaNotice}
          </p>
        )}
        {reset && (
          <div className="mt-4 rounded-md border border-teal/30 bg-teal/5 p-4 text-sm">
            <p className="font-medium text-ink">Password reset for {reset.email}</p>
            <p className="mt-1 text-slate-600">
              {reset.emailed
                ? "The temporary password is being emailed to them. It's shown below only as a backup."
                : "Couldn't send the email (SMTP isn't configured or the send failed) — share the temporary password below with them yourself."}
            </p>
            <p className="mt-2 text-slate-600">
              Temporary password: <code className="rounded bg-white px-1.5 py-0.5">{reset.temp_password}</code>
            </p>
            <p className="mt-1 text-slate-500">
              It won't be shown again after you leave this page. They'll be required to set their own password at
              next sign-in.
            </p>
          </div>
        )}
        <div className="mt-4">
          {error ? (
            <ErrorState message="Couldn't load officer accounts." onRetry={() => refetch()} />
          ) : (
            <DataTable
              columns={[
                { header: "Name", cell: (u: User) => u.name },
                { header: "Email", cell: (u: User) => u.email },
                { header: "Role", cell: (u: User) => u.role.toUpperCase() },
                { header: "Organisation", cell: (u: User) => u.org_name ?? "—" },
                { header: "Jurisdiction", cell: (u: User) => <JurisdictionText jurisdiction={u.jurisdiction} /> },
                { header: "Status", cell: (u: User) => <UserStatusBadge status={u.status} /> },
                {
                  header: "2-step",
                  cell: (u: User) =>
                    u.mfa_enabled ? (
                      <Badge tone="success">On</Badge>
                    ) : (
                      <span title="Not set up yet — they'll be asked at their next sign-in">
                        <Badge tone="warning">Not set up</Badge>
                      </span>
                    ),
                },
                {
                  header: "",
                  cell: (u: User) => (
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={resetPassword.isPending && resetPassword.variables === u.id}
                      onClick={() => onResetPassword(u)}
                    >
                      Reset password
                    </Button>
                  ),
                },
                {
                  header: "",
                  cell: (u: User) =>
                    u.mfa_enabled ? (
                      <Button
                        size="sm"
                        variant="secondary"
                        loading={resetMfa.isPending && resetMfa.variables === u.id}
                        onClick={() => onResetMfa(u)}
                      >
                        Reset 2-step
                      </Button>
                    ) : null,
                },
                {
                  header: "",
                  cell: (u: User) =>
                    u.status === "rejected" ? (
                      <Button
                        size="sm"
                        variant="secondary"
                        loading={toggleStatus.isPending}
                        onClick={() => toggleStatus.mutate({ id: u.id, action: "approve" })}
                      >
                        Reactivate
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="danger"
                        loading={toggleStatus.isPending}
                        onClick={() => toggleStatus.mutate({ id: u.id, action: "reject" })}
                      >
                        Suspend
                      </Button>
                    ),
                },
              ]}
              rows={officers ?? []}
              rowKey={(u) => u.id}
              isLoading={isLoading}
              emptyTitle="No officer accounts yet"
              emptyDescription="Create the first lmo or gatc account above."
            />
          )}
        </div>
      </Panel>
    </div>
  );
}
