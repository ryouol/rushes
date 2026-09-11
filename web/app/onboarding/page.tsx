import { Onboarding } from "@/components/onboarding";
import { pageMetadata } from "@/lib/metadata";

export const metadata = pageMetadata(
  "Your first project",
  "Create your first RUSHES project and give your footage a home.",
  "/onboarding",
);

export default function OnboardingPage() {
  return <Onboarding />;
}
