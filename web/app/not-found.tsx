import Link from "next/link";
export default function NotFound() {
  return (
    <main id="main" className="legal">
      <span className="eyebrow">404 · NOT FOUND</span>
      <h1>This page isn’t in the library.</h1>
      <p>The link may be incomplete or the page may have moved.</p>
      <Link href="/" className="primary">
        Return to projects
      </Link>
    </main>
  );
}
