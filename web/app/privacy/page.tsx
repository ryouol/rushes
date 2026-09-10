export const metadata = { title: "Privacy — draft" };
export default function Privacy() {
  return (
    <main id="main" className="legal">
      <a href="/">← RUSHES</a>
      <h1>Privacy information</h1>
      <p>
        <strong>Draft — not a final legal policy.</strong>
      </p>
      <p>
        RUSHES stores accounts, uploaded footage, footage references, previews,
        transcripts, worklogs and exports on the server running this instance. A
        hosted instance uses cloud storage and processing. Gemini analysis sends
        derived video and bounded transcript context to Google. When Modal
        compute is enabled, derived audio, worklog text and search queries are
        sent to private Modal functions. Temporary audio is removed after each
        function completes.
      </p>
      <p>
        No analytics integration is active. Session cookies keep you signed in.
      </p>
      <p>
        TODO: provide reviewed privacy terms, operator identity, retention
        policy, and applicable provider disclosures before a hosted commercial
        release.
      </p>
    </main>
  );
}
