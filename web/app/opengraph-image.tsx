import { ImageResponse } from "next/og";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

export const alt = "RUSHES — Your footage. Organized by AI.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// The public raster mark is shared with the real header. ImageResponse does not
// accept the site's WOFF2 font or WebP preview. The regular sans composition
// keeps the public social image compatible with its supported asset formats.
const logo = `data:image/png;base64,${await readFile(join(process.cwd(), "public/brand/mark.png"), "base64")}`;

export default function Image() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        background: "#faf9f6",
        color: "#15171c",
        padding: "62px 76px",
        fontFamily: "sans-serif",
        fontWeight: 400,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <img src={logo} alt="" width={46} height={46} />
        <span style={{ fontSize: 42, fontWeight: 600, letterSpacing: -2 }}>
          rushes
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", marginTop: 78 }}>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            fontSize: 78,
            lineHeight: 1.06,
            letterSpacing: -5,
          }}
        >
          <span>Your footage.</span><span>Organized by AI.</span>
        </div>
        <div
          style={{
            display: "flex",
            marginTop: 26,
            color: "#666d78",
            fontSize: 31,
            letterSpacing: -1,
          }}
        >
          Drop in your footage. Find it by what’s inside.
        </div>
      </div>
    </div>,
    size,
  );
}
