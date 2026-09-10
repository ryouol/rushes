import { ImageResponse } from "next/og";
export const alt = "RUSHES — Your footage, in focus";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export default function Image() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        background: "#111315",
        color: "#f3f0e8",
        padding: 90,
      }}
    >
      <div
        style={{
          display: "flex",
          fontSize: 28,
          color: "#efb35c",
          letterSpacing: 8,
        }}
      >
        RUSHES
      </div>
      <div
        style={{ display: "flex", fontSize: 76, marginTop: 36, maxWidth: 850 }}
      >
        Your footage, in focus.
      </div>
      <div
        style={{
          display: "flex",
          fontSize: 28,
          marginTop: 34,
          color: "#a8aaa8",
        }}
      >
        Local footage library · Worklog · Selects
      </div>
    </div>,
    size,
  );
}
