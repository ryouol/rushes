"use client";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main id="main" className="legal">
      <h1>Something interrupted this view.</h1>
      <p>Your saved footage and worklog remain on the local backend.</p>
      <button className="primary" onClick={reset}>
        Try again
      </button>
      <a href="/" className="secondary">
        Return to projects
      </a>
    </main>
  );
}
