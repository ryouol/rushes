import { Landing } from "@/components/landing";
import { pageMetadata } from "@/lib/metadata";
export const metadata = pageMetadata("Your footage. Organized by AI.", "Upload footage, let AI categorize what’s inside, and find what you need with natural-language search.", "/", true);
export default function Home() {
  return <Landing />;
}
