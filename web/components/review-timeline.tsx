"use client";

import { useEffect, useState } from "react";
import { elapsed } from "@/lib/api";

/** Preview frames come from the authenticated proxy. Export timing stays source-relative. */
export function ReviewTimeline({
  src,
  duration,
  current,
  start,
  end,
  onSeek,
}: {
  src: string;
  duration: number;
  current: number;
  start: number;
  end: number;
  onSeek: (value: number) => void;
}) {
  const [frames, setFrames] = useState<string[]>([]);
  useEffect(() => {
    if (!duration) return;
    let disposed = false;
    const media = document.createElement("video");
    const canvas = document.createElement("canvas");
    canvas.width = 160;
    canvas.height = 90;
    const context = canvas.getContext("2d");
    if (!context) return;
    const images: string[] = [];
    media.muted = true;
    media.preload = "metadata";
    media.playsInline = true;
    function capture() {
      if (disposed || !context) return;
      try {
        const scale = Math.max(
          canvas.width / media.videoWidth,
          canvas.height / media.videoHeight,
        );
        const width = media.videoWidth * scale;
        const height = media.videoHeight * scale;
        context.drawImage(
          media,
          (canvas.width - width) / 2,
          (canvas.height - height) / 2,
          width,
          height,
        );
        images.push(canvas.toDataURL("image/jpeg", 0.65));
        if (images.length === 10) {
          setFrames(images);
          media.removeAttribute("src");
          media.load();
        } else {
          media.currentTime = (duration / 1e6) * ((images.length + 0.5) / 10);
        }
      } catch {
        // Native video controls and the labeled seek slider remain usable.
        media.removeAttribute("src");
        media.load();
      }
    }
    media.onloadedmetadata = () => {
      media.currentTime = duration / 1e6 / 20;
    };
    media.onseeked = capture;
    media.src = src;
    return () => {
      disposed = true;
      media.onloadedmetadata = null;
      media.onseeked = null;
      media.removeAttribute("src");
      media.load();
    };
  }, [src, duration]);
  const valid = start >= 0 && end > start && end <= duration;
  return (
    <div className="review-timeline">
      <div className="review-filmstrip" aria-hidden="true">
        {frames.map((frame, index) => (
          <img key={index} src={frame} alt="" />
        ))}
        <div
          className="review-playhead"
          style={{
            left: `${Math.min(100, Math.max(0, (current / duration) * 100))}%`,
          }}
        />
        {valid && (
          <div
            className="review-range"
            style={{
              left: `${(start / duration) * 100}%`,
              width: `${((end - start) / duration) * 100}%`,
            }}
          />
        )}
      </div>
      <input
        className="review-seek"
        type="range"
        min={0}
        max={duration}
        step={1000}
        value={Math.min(current, duration)}
        onChange={(event) => onSeek(Number(event.target.value))}
        aria-label="Seek footage"
        aria-valuetext={elapsed(current)}
      />
      <div className="review-ruler" aria-hidden="true">
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => (
          <span key={fraction}>{elapsed(Math.round(duration * fraction))}</span>
        ))}
      </div>
    </div>
  );
}
