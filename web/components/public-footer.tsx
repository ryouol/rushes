import Link from "next/link";
import { AnalyticsChoices } from "@/components/analytics-consent";

export function PublicFooter() {
  return <footer className="public-footer"><span>© {new Date().getFullYear()} RUSHES</span><nav aria-label="Legal and contact"><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link><Link href="/contact">Contact</Link><AnalyticsChoices /></nav></footer>;
}
