import { AuthPage } from "@/components/auth";
import { pageMetadata } from "@/lib/metadata";

const description =
  "Sign in to your AI-organized footage library.";

export const metadata = pageMetadata("Sign in", description, "/login");

export default function LoginPage() {
  return <AuthPage mode="login" />;
}
