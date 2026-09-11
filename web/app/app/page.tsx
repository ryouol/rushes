import { Suspense } from "react";
import { Rushes, WorkspaceLoading } from "@/components/rushes";
import { pageMetadata } from "@/lib/metadata";

export const metadata = pageMetadata(
  "Your workspace",
  "Organize your footage, review moments, and keep your selects together in RUSHES.",
  "/app",
);

export default function AppPage() {
  return (
    <Suspense fallback={<WorkspaceLoading />}>
      <Rushes />
    </Suspense>
  );
}
