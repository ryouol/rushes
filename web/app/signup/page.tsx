import { AuthPage } from "@/components/auth";
import { pageMetadata } from "@/lib/metadata";

const description =
  "Create your RUSHES account and start your first footage project.";

export const metadata = pageMetadata(
  "Create an account",
  description,
  "/signup",
);

export default function SignupPage() {
  return <AuthPage mode="signup" />;
}
