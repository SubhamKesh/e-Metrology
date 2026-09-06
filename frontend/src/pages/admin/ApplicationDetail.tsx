import { useParams } from "react-router-dom";
import { ApplicationOverview } from "@/components/domain/ApplicationOverview";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { useApplication } from "@/hooks/useData";
import { ApiError } from "@/lib/api";

export default function AdminApplicationDetail() {
  const { id } = useParams();
  const { data: application, isLoading, isError, error, refetch } = useApplication(id);

  if (isLoading) return <Skeleton className="h-64 w-full max-w-2xl" />;
  if (isError || !application) {
    return <ErrorState message={error instanceof ApiError ? error.message : "Application not found."} onRetry={refetch} />;
  }

  return <ApplicationOverview application={application} />;
}
