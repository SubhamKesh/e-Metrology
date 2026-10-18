import { type FormEvent, useMemo, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { FilterBar } from "@/components/domain/FilterBar";
import { useGeoDistricts, useGeoStates } from "@/hooks/useData";
import { useFilters } from "@/hooks/useFilters";

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
  const officerFilters = useFilters({ q: "", role: "", status: "" });
  const { data: officers, isLoading, error, refetch } = useQuery<User[]>({
    queryKey: ["admin", "officers", officerFilters.query],
    queryFn: () => AdminUsersApi.listOfficers(officerFilters.query),
    placeholderData: keepPreviousData,
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

  const isLmo = form.role === "lmo";

  function setRole(role: CreateOfficerPayload["role"]) {
    // A GATC covers the whole state, so a district picked for an LMO is dropped.
    setForm((f) => ({ ...f, role, district_code: role === "gatc" ? "" : f.district_code }));
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setCreated(null);
    if (isLmo && !form.district_code) {
      setFormError("A Legal Metrology Officer is district-level. Pick the district they are assigned to.");
      return;
    }
    const { state_code, district_code, ...rest } = form;
    createOfficer.mutate({
      ...rest,
      jurisdiction: { state_code, district_code: isLmo ? district_code : null },
    });
  }

  // Re-assign scope (mainly: give older LMO accounts their district).
  const [editing, setEditing] = useState<User | null>(null);
  const [editState, setEditState] = useState("");
  const [editDistrict, setEditDistrict] = useState("");
  const [editError, setEditError] = useState<string | null>(null);
  const { data: editDistricts, isLoading: editDistrictsLoading } = useGeoDistricts(editState || undefined);
  const editDistrictOptions = useMemo(
    () => (editDistricts ?? []).map((d) => ({ value: d.code, label: d.name })),
    [editDistricts],
  );
  const changeJurisdiction = useMutation({
    mutationFn: ({ id, state_code, district_code }: { id: string; state_code: string; district_code: string | null }) =>
      AdminUsersApi.changeJurisdiction(id, { state_code, district_code }),
    onSuccess: (res) => {
      setEditing(null);
      setEditError(null);
      setMfaNotice(`Jurisdiction updated for ${res.email}. They've been signed out so the new scope applies at next sign-in.`);
      qc.invalidateQueries({ queryKey: ["admin", "officers"] });
    },
    onError: (err) => setEditError(err instanceof ApiError ? err.message : "Couldn't update the jurisdiction. Try again."),
  });

  function startEdit(u: User) {
    setEditing(u);
    setEditError(null);
    setEditState(u.jurisdiction?.state_code ?? "");
    setEditDistrict(u.jurisdiction?.district_code ?? "");
  }

  function saveEdit(e: FormEvent) {
    e.preventDefault();
    if (!editing) return;
    if (editing.role === "lmo" && !editDistrict) {
      setEditError("Pick the district this officer is assigned to.");
      return;
    }
    changeJurisdiction.mutate({
      id: editing.id,
      state_code: editState,
      district_code: editing.role === "lmo" ? editDistrict : null,
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl text-ink">Officer accounts</h1>
        <p className="mt-1 text-sm text-slate-500">
          LMO and GATC accounts are invite-only. An LMO is district-level and only sees their own district; a GATC is
          state-level and covers the whole state.
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
            onChange={(e) => setRole(e.target.value as CreateOfficerPayload["role"])}
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
          {isLmo ? (
            <SelectInput
              label="District"
              required
              disabled={!form.state_code}
              hint="An LMO only has access to this one district."
              placeholder={
                !form.state_code ? "Select a state first" : districtsLoading ? "Loading districts…" : "Select a district"
              }
              options={districtOptions}
              value={form.district_code}
              onChange={(e) => set("district_code", e.target.value)}
            />
          ) : (
            <div className="flex items-end">
              <p className="rounded-md bg-paper px-3 py-2.5 text-sm text-slate-600">
                GATC accounts are state-level: they cover every district in the selected state.
              </p>
            </div>
          )}
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
        {editing && (
          <form onSubmit={saveEdit} className="mt-4 rounded-md border border-line bg-paper/60 p-4">
            <p className="text-sm font-medium text-ink">
              {editing.role === "lmo" ? "Assign district" : "Change state"} for {editing.name}
            </p>
            <div className="mt-3 grid gap-4 sm:grid-cols-2">
              <SelectInput
                label="State / UT"
                required
                options={stateOptions}
                value={editState}
                onChange={(e) => {
                  setEditState(e.target.value);
                  setEditDistrict("");
                }}
              />
              {editing.role === "lmo" && (
                <SelectInput
                  label="District"
                  required
                  disabled={!editState}
                  placeholder={editDistrictsLoading ? "Loading districts…" : "Select a district"}
                  options={editDistrictOptions}
                  value={editDistrict}
                  onChange={(e) => setEditDistrict(e.target.value)}
                />
              )}
            </div>
            {editError && <p className="mt-3 text-sm text-danger">{editError}</p>}
            <div className="mt-4 flex gap-2">
              <Button type="submit" size="sm" loading={changeJurisdiction.isPending}>
                Save
              </Button>
              <Button type="button" size="sm" variant="secondary" onClick={() => setEditing(null)}>
                Cancel
              </Button>
            </div>
          </form>
        )}
        <div className="mt-4">
          <FilterBar
            search={officerFilters.values.q}
            onSearch={(v) => officerFilters.set("q", v)}
            searchLabel="Search officers"
            searchPlaceholder="Name, email or organisation"
            active={officerFilters.active}
            onClear={officerFilters.clear}
          >
            <SelectInput
              label="Role"
              value={officerFilters.values.role}
              onChange={(e) => officerFilters.set("role", e.target.value)}
              options={[{ value: "", label: "Any" }, ...ROLE_OPTIONS]}
            />
            <SelectInput
              label="Status"
              value={officerFilters.values.status}
              onChange={(e) => officerFilters.set("status", e.target.value)}
              options={[
                { value: "", label: "Any" },
                { value: "active", label: "Active" },
                { value: "pending", label: "Pending" },
                { value: "rejected", label: "Suspended" },
              ]}
            />
          </FilterBar>
          {error ? (
            <ErrorState message="Couldn't load officer accounts." onRetry={() => refetch()} />
          ) : (
            <DataTable
              columns={[
                {
                  header: "Officer",
                  cell: (u: User) => (
                    <div className="min-w-[10rem] leading-tight">
                      <p className="font-medium text-ink">{u.name}</p>
                      <p className="mt-0.5 break-all text-xs text-slate-500">{u.email}</p>
                    </div>
                  ),
                },
                {
                  header: "Role",
                  cell: (u: User) => <Badge tone="info">{u.role === "lmo" ? "LMO" : u.role.toUpperCase()}</Badge>,
                },
                { header: "Organisation", cell: (u: User) => <span className="break-words">{u.org_name ?? "—"}</span>, className: "max-w-[11rem]" },
                {
                  header: "Jurisdiction",
                  cell: (u: User) => <JurisdictionText jurisdiction={u.jurisdiction} role={u.role} />,
                },
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
                  header: "Actions",
                  cell: (u: User) => (
                    <div className="flex flex-wrap justify-end gap-2">
                      <Button size="sm" variant="secondary" onClick={() => startEdit(u)}>
                        {u.role === "lmo" ? "Change district" : "Change state"}
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        loading={resetPassword.isPending && resetPassword.variables === u.id}
                        onClick={() => onResetPassword(u)}
                      >
                        Reset password
                      </Button>
                      {u.mfa_enabled && (
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={resetMfa.isPending && resetMfa.variables === u.id}
                          onClick={() => onResetMfa(u)}
                        >
                          Reset 2-step
                        </Button>
                      )}
                      {u.status === "rejected" ? (
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
                      )}
                    </div>
                  ),
                  className: "min-w-[15rem]",
                },
              ]}
              rows={officers ?? []}
              rowKey={(u) => u.id}
              isLoading={isLoading}
              emptyTitle={officerFilters.active ? "No officers match" : "No officer accounts yet"}
              emptyDescription={officerFilters.active ? "Try a different search or clear the filters." : "Create the first LMO or GATC account above."}
            />
          )}
        </div>
      </Panel>
    </div>
  );
}
