import { applicationOrigin } from "@/lib/server-config";

export const dynamic = "force-static";

// Only values already published in page markup belong in this build/runtime check.
export function GET() {
  return Response.json({
    origin: applicationOrigin().origin,
    contact_email: process.env.RUSHES_CONTACT_EMAIL ?? "",
    contact_phone: process.env.RUSHES_CONTACT_PHONE ?? "",
    contact_address: process.env.RUSHES_CONTACT_ADDRESS ?? "",
    legal_entity: process.env.RUSHES_LEGAL_ENTITY ?? "",
    ga_measurement_id: process.env.RUSHES_GA_MEASUREMENT_ID ?? "",
  });
}
