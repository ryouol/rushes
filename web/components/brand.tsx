import Link from "next/link";

export function Brand({
  compact = false,
  className = "",
  href = "/",
  label,
}: {
  compact?: boolean;
  className?: string;
  href?: string;
  label?: string;
}) {
  return (
    <Link
      href={href}
      className={`brand ${className}`}
      aria-label={label || (href === "/" ? "RUSHES home" : "RUSHES dashboard")}
    >
      <img
        src="/brand/mark.png"
        alt=""
        width={32}
        height={32}
        className="brand-symbol"
      />
      {!compact && <span>rushes</span>}
    </Link>
  );
}
