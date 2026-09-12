import { pageMetadata } from "@/lib/metadata";
import { PublicHeader } from "@/components/public-header";
import { PublicFooter } from "@/components/public-footer";
import "@/components/landing.css";
import "@/components/legal.css";

export const metadata = pageMetadata(
  "Contact information",
  "Contact details for the operator of this RUSHES instance.",
  "/contact",
);

function publicText(value: string | undefined, maxLength: number) {
  const text = value?.trim();
  return text &&
    text.length <= maxLength &&
    !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(text)
    ? text
    : null;
}

export default async function Contact() {
  // Optional public contact values are read only on the server. Invalid values
  // remain visibly unconfigured and never become unusable mailto/tel links.
  const configuredEmail = publicText(process.env.RUSHES_CONTACT_EMAIL, 254);
  const email =
    configuredEmail &&
    /^[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}$/.test(configuredEmail)
      ? configuredEmail
      : null;
  const configuredPhone = publicText(process.env.RUSHES_CONTACT_PHONE, 40);
  const phoneNumber = configuredPhone?.replace(/[() .-]/g, "");
  const phone =
    phoneNumber && /^\+?[0-9]{7,15}$/.test(phoneNumber)
      ? { display: configuredPhone, href: `tel:${phoneNumber}` }
      : null;
  const address = publicText(process.env.RUSHES_CONTACT_ADDRESS, 600);
  const entity = publicText(process.env.RUSHES_LEGAL_ENTITY, 200);
  const incomplete = !email || !phone || !address || !entity;
  return (
    <div className="public-document">
      <PublicHeader />
      <main id="main" className="document-main">
        <div className="document-heading">
          <span className="document-eyebrow">Contact</span>
          <h1>Get in touch.</h1>
          <p>Contact information for the operator of this instance.</p>
        </div>
        {incomplete && (
          <div className="document-notice">
            <strong>Contact details are incomplete.</strong>
            <p>The operator has not provided all of the details below.</p>
          </div>
        )}
        <dl className="contact-details">
          {/* <!-- TODO: provide legal entity name --> */}
          <div>
            <dt>Operator</dt>
            <dd>
              {entity || (
                <span className="contact-missing">
                  Legal entity name has not been provided.
                </span>
              )}
            </dd>
          </div>
          {/* <!-- TODO: provide contact email --> */}
          <div>
            <dt>Email</dt>
            <dd>
              {email ? (
                <a href={`mailto:${email}`}>{email}</a>
              ) : (
                <span className="contact-missing">
                  Contact email has not been provided.
                </span>
              )}
            </dd>
          </div>
          {/* <!-- TODO: provide contact phone number --> */}
          <div>
            <dt>Phone</dt>
            <dd>
              {phone ? (
                <a href={phone.href}>{phone.display}</a>
              ) : (
                <span className="contact-missing">
                  Contact phone number has not been provided.
                </span>
              )}
            </dd>
          </div>
          {/* <!-- TODO: provide physical contact address --> */}
          <div>
            <dt>Address</dt>
            <dd>
              {address ? (
                <address>{address}</address>
              ) : (
                <span className="contact-missing">
                  Physical contact address has not been provided.
                </span>
              )}
            </dd>
          </div>
        </dl>
      </main>
      <PublicFooter />
    </div>
  );
}
