import { useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/layout/AppShell";
import { Panel } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/Field";
import { Avatar } from "@/components/ui/Avatar";
import { useAuth } from "@/context/AuthContext";
import { AuthApi } from "@/lib/endpoints";
import { ApiError } from "@/lib/api";
import { compressImage } from "@/lib/imageCompress";
import { ROLE_LABEL } from "@/lib/types";

const PHONE = /^[6-9]\d{9}$/;

/** Edit your own name, phone number and (owners) organisation, and set a profile picture. */
export default function Profile() {
  const { user, updateUser } = useAuth();
  const fileRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState(user?.name ?? "");
  const [contact, setContact] = useState(user?.contact ?? "");
  const [orgName, setOrgName] = useState(user?.org_name ?? "");
  const [saving, setSaving] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);

  if (!user) return null;
  const isOwner = user.role === "owner";
  const contactError = contact && !PHONE.test(contact) ? "Enter a 10-digit mobile number starting with 6-9." : undefined;
  const nameError = name.trim() === "" ? "Name cannot be empty." : undefined;
  const changed =
    name.trim() !== user.name || contact !== (user.contact ?? "") || (isOwner && orgName.trim() !== (user.org_name ?? ""));

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!user || contactError || nameError || !changed) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const body: { name: string; contact: string; org_name?: string } = { name: name.trim(), contact };
      if (isOwner) body.org_name = orgName.trim();
      const next = await AuthApi.updateProfile(body);
      updateUser(next);
      setName(next.name);
      setContact(next.contact ?? "");
      setOrgName(next.org_name ?? "");
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Your changes could not be saved. Try again.");
    } finally {
      setSaving(false);
    }
  }

  async function pickPhoto(files: FileList | null) {
    const original = files?.[0];
    if (fileRef.current) fileRef.current.value = "";
    if (!original) return;
    setPhotoError(null);
    setPhotoBusy(true);
    try {
      const file = await compressImage(original);
      updateUser(await AuthApi.uploadAvatar(file));
    } catch (err) {
      setPhotoError(err instanceof ApiError ? err.message : "The picture could not be uploaded. Try again.");
    } finally {
      setPhotoBusy(false);
    }
  }

  async function removePhoto() {
    setPhotoError(null);
    setPhotoBusy(true);
    try {
      updateUser(await AuthApi.removeAvatar());
    } catch (err) {
      setPhotoError(err instanceof ApiError ? err.message : "The picture could not be removed. Try again.");
    } finally {
      setPhotoBusy(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <PageHeader title="My profile" description={`${ROLE_LABEL[user.role]} · ${user.email}`} />

      <Panel className="mb-6 p-4 sm:p-5">
        <h2 className="mb-3 text-sm font-medium text-ink">Profile picture</h2>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          <Avatar name={user.name} src={user.avatar_url} className="h-24 w-24 text-3xl" />
          <div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="secondary" size="sm" onClick={() => fileRef.current?.click()} loading={photoBusy}>
                {user.avatar_url ? "Change picture" : "Add picture"}
              </Button>
              {user.avatar_url && (
                <Button type="button" variant="ghost" size="sm" onClick={removePhoto} disabled={photoBusy}>
                  Remove
                </Button>
              )}
            </div>
            <p className="mt-2 text-xs text-slate-500">JPG, PNG or WebP, up to 2 MB.</p>
            {photoError && (
              <p role="alert" className="mt-2 text-sm text-danger">
                {photoError}
              </p>
            )}
          </div>
          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="hidden"
            onChange={(e) => pickPhoto(e.target.files)}
          />
        </div>
      </Panel>

      <Panel className="p-4 sm:p-5">
        <form onSubmit={save} className="flex flex-col gap-4" noValidate>
          <TextInput label="Full name" value={name} onChange={(e) => setName(e.target.value)} error={nameError} maxLength={100} required />
          <TextInput label="Email" value={user.email} disabled hint="Your email address can't be changed here." readOnly />
          <TextInput
            label="Mobile number"
            inputMode="numeric"
            value={contact}
            onChange={(e) => setContact(e.target.value.replace(/\D/g, "").slice(0, 10))}
            error={contactError}
            hint={contact && contact !== (user.contact ?? "") ? "A new number needs to be verified again." : undefined}
          />
          {isOwner ? (
            <TextInput label="Organisation" value={orgName} onChange={(e) => setOrgName(e.target.value)} maxLength={200} />
          ) : (
            user.org_name && (
              <TextInput label="Organisation" value={user.org_name} disabled readOnly hint="Set by the administrator." />
            )
          )}

          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          {saved && !changed && (
            <p role="status" className="text-sm text-success">
              Profile saved.
            </p>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" loading={saving} disabled={!changed || !!contactError || !!nameError}>
              Save changes
            </Button>
            <Link to="/change-password" className="text-sm font-medium text-teal hover:underline">
              Change password
            </Link>
          </div>
        </form>
      </Panel>
    </div>
  );
}
