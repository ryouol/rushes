import Link from "next/link";
import { pageMetadata } from "@/lib/metadata";
import { PublicHeader } from "@/components/public-header";
import { PublicFooter } from "@/components/public-footer";
import "@/components/landing.css";
import "@/components/legal.css";

export const metadata = pageMetadata(
  "Terms information — draft",
  "Current RUSHES product information and legal terms awaiting operator review.",
  "/terms",
);

export default function Terms() {
  return (
    <div className="public-document">
      <PublicHeader />
      <main id="main" className="document-main">
        <div className="document-heading">
          <span className="document-eyebrow">Terms</span>
          <h1>Using RUSHES.</h1>
          <p>Current product information. Legal terms are awaiting review.</p>
        </div>
        <div className="document-notice">
          <strong>Draft — not final legal terms.</strong>
          <p>
            The operating entity, reviewed agreement and support arrangements
            have not yet been provided.
          </p>
        </div>
        {/* <!-- TODO: provide legal entity name --> */}
        {/* <!-- TODO: provide reviewed Terms --> */}
        <section>
          <h2>What the product does</h2>
          <p>
            RUSHES organizes footage, creates searchable worklogs, helps you
            review source moments and saves selected ranges for export.
            Automatic descriptions, transcripts and event locations need human
            review.
          </p>
        </section>
        <section>
          <h2>Source footage and exports</h2>
          <p>
            Original footage is preserved; exports are written separately.
            Review selected ranges and the export preview before starting an
            export. Editor interchange formats carry an experimental disclosure
            in the export flow.
          </p>
        </section>
        <section>
          <h2>Processing and payments</h2>
          <p>
            Processing uses the workspace’s available allowance. This interface
            does not provide a payment checkout or sell a subscription plan.
          </p>
        </section>
        <section>
          <h2>Details still required</h2>
          <p>
            The operator needs to provide reviewed terms covering the legal
            entity, permitted use, content responsibilities, service and support
            arrangements, and applicable contractual terms. This product
            description does not replace that agreement.
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
