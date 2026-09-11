import Link from "next/link";
import { pageMetadata } from "@/lib/metadata";
import { PublicHeader } from "@/components/public-header";
import { PublicFooter } from "@/components/public-footer";
import "@/components/landing.css";
import "@/components/legal.css";

export const metadata = pageMetadata(
  "Privacy information — draft",
  "How RUSHES handles footage and account data, with operator policy details awaiting review.",
  "/privacy",
);

export default function Privacy() {
  return (
    <div className="public-document">
      <PublicHeader />
      <main id="main" className="document-main">
        <div className="document-heading">
          <span className="document-eyebrow">Privacy</span>
          <h1>Your footage and data.</h1>
          <p>Product information, with policy details still to come.</p>
        </div>
        <div className="document-notice">
          <strong>Draft — not a final privacy policy.</strong>
          <p>
            The operator’s identity, reviewed policy, retention periods and
            privacy contact have not yet been provided.
          </p>
        </div>
        {/* <!-- TODO: provide legal entity name --> */}
        {/* <!-- TODO: provide reviewed privacy policy --> */}
        <section>
          <h2>What the service stores</h2>
          <p>
            RUSHES stores account details, project records, uploaded footage or
            source references, derived previews, transcripts, worklogs, saved
            selects and exports on the server running this instance. Workspace
            membership controls access to project data. Media and export
            downloads use authenticated routes.
          </p>
        </section>
        <section>
          <h2>How processing works</h2>
          <p>
            When Gemini analysis is used, derived video and bounded transcript
            context are sent to Google. When Modal compute is enabled, derived
            audio, worklog text and search queries are sent to private Modal
            functions for transcription and embeddings. Temporary transcription
            audio is removed when its function finishes.
          </p>
          <p>
            Server storage does not mean that all processing happens offline.
            The operator still needs to publish the applicable provider
            disclosures and storage locations.
          </p>
        </section>
        <section>
          <h2>Cookies and browser storage</h2>
          <p>
            Session cookies keep you signed in. Browser storage remembers your
            appearance preference and can keep unfinished project setup in the
            current tab.
          </p>
          <p>
            Optional analytics run only when configured and you allow them in
            Analytics choices. The operator still needs to publish the tracking
            details and applicable cookie information.
          </p>
        </section>
        <section>
          <h2>Retention and privacy requests</h2>
          <p>
            Retention periods, deletion arrangements, the responsible legal
            entity and a privacy contact are awaiting the operator’s reviewed
            policy. No final retention or rights-request process is published
            here yet.
          </p>
          <Link className="document-text-link" href="/contact">
            Contact information
          </Link>
        </section>
      </main>
      <PublicFooter />
    </div>
  );
}
