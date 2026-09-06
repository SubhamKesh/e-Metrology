import { Link, useParams } from "react-router-dom";
import { ApplicationOverview } from "@/components/domain/ApplicationOverview";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { Button } from "@/components/ui/Button";
import { useApplication, useCertificates } from "@/hooks/useData";
import { ApiError } from "@/lib/api";

export default function OwnerApplicationDetail() {
  const { id } = useParams();
  const { data: application, isLoading, isError, error, refetch } = useApplication(id);
  const { data: certificates } = useCertificates();
  const certificate = certificates?.find((c) => c.application_id === id);

  if (isLoading) return <Skeleton className="h-64 w-full max-w-2xl" />;
  if (isError || !application) {
    return <ErrorState message={error instanceof ApiError ? error.message : "Application not found."} onRetry={refetch} />;
  }

  return (
    <ApplicationOverview
      application={application}
      actions={
        application.status === "certified" || application.status === "expiring" ? (
          <Link to={certificate ? `/app/owner/certificates/${certificate.id}` : "/app/owner/certificates"}>
            <Button size="sm">View certificate</Button>
          </Link>
        ) : undefined
      }
    />
  );
}
