import Link from "next/link";

export function Brand({ compact = false, className = "" }: { compact?: boolean; className?: string }) {
  return <Link href="/" className={`brand ${className}`} aria-label="RUSHES home">
    <img src="/brand/mark.png" alt="" width={32} height={32} className="brand-symbol" />
    {!compact && <span>rushes</span>}
  </Link>;
}
