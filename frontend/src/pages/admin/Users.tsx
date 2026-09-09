import { type FormEvent, useState } from "react";
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

  const [form, setForm] = useState<CreateOfficerPayload>({
    name: "",
    email: "",
    role: "lmo",
    org_name: "",
    contact: "",
  });
  const [formError, setFormError] = useState<string | null>(null);
  const [created, setCreated] = useState<{ email: string; temp_password: string; emailed: boolean } | null>(
    null,
  );

  const createOfficer = useMutation({
    mutationFn: (body: CreateOfficerPayload) => AdminUsersApi.createOfficer(body),
    onSuccess: (res) => {
      setCreated({ email: res.user.email, temp_password: res.temp_password, emailed: res.emailed });
      setForm({ name: "", email: "", role: "lmo", org_name: "", contact: "" });
      qc.invalidateQueries({ queryKey: ["admin", "officers"] });
    },
    onError: (err) => {
      setFormError(err instanceof ApiError ? err.message : "Couldn't create that account. Try again.");
    },
  });

  const toggleStatus = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "approve" | "reject" }) =>
      action === "approve" ? AdminUsersApi.approve(id) : AdminUsersApi.reject(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "officers"] }),
  });

  function set<K extends keyof CreateOfficerPayload>(key: K, value: CreateOfficerPayload[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setCreated(null);
    createOfficer.mutate(form);
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
          <div className="flex items-end">
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
                Login credentials have been emailed to them directly. The temporary password is shown below only as
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
                { header: "Status", cell: (u: User) => <UserStatusBadge status={u.status} /> },
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
