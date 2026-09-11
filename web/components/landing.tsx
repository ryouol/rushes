"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, Pause, Play } from "lucide-react";
import { PublicHeader } from "@/components/public-header";
import { PublicFooter } from "@/components/public-footer";
import { startScrollMotion } from "@/lib/scroll-motion";
import "./landing.css";

const subjects = [
  {
    name: "Scenes",
    poster: "coast",
    description: "Sunlit cliffs and sea stacks along a rugged coastline",
  },
  {
    name: "Details",
    poster: "waves",
    description: "White surf breaking around dark rocks",
  },
  {
    name: "Perspectives",
    poster: "aerial",
    description: "An aerial view of the coastline, grassy cliffs and ocean",
  },
];

export function Landing() {
  const page = useRef<HTMLDivElement>(null);
  const hero = useRef<HTMLElement>(null);
  const [motionPaused, setMotionPaused] = useState(false);
  const [motionAllowed, setMotionAllowed] = useState(false);
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setMotionAllowed(!preference.matches);
    update();
    preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (!page.current || !motionAllowed || motionPaused) return;
    return startScrollMotion(page.current);
  }, [motionAllowed, motionPaused]);
  const [showStickyCta, setShowStickyCta] = useState(false);
  useEffect(() => {
    if (!hero.current) return;
    const observer = new IntersectionObserver(([entry]) =>
      setShowStickyCta(!entry.isIntersecting),
    );
    observer.observe(hero.current);
    return () => observer.disconnect();
  }, []);
  return (
    <div ref={page} className="landing-page">
      <PublicHeader />
      <main id="main" className="landing-main">
        <section
          ref={hero}
          className="landing-hero"
          aria-labelledby="hero-title"
        >
          <div>
            <h1 id="hero-title">
              Your footage.
              <br />
              Organized by AI.
            </h1>
            <p>Drop in your footage. Find it by what’s inside.</p>
          </div>
          <div className="hero-actions">
            <Link className="primary" href="/signup">
              Organize your footage <ArrowRight size={19} />
            </Link>
            <Link className="text-link" href="#workflow">
              See how it works
            </Link>
          </div>
        </section>
        <section
          className="landing-showcase"
          aria-label="A clearer view of your footage"
        >
          <figure className="showcase-viewer" data-parallax="0.07">
            <picture className="showcase-poster" data-motion-image>
              <source
                type="image/webp"
                srcSet="/demo/coast-640.webp 640w, /demo/coast-960.webp 960w, /demo/coast-1440.webp 1440w, /demo/coast-1672.webp 1672w"
                sizes="(max-width: 700px) 100vw, 90vw"
              />
              <img
                src="/demo/coast-1440.webp"
                alt={subjects[0].description}
                width={1672}
                height={941}
                fetchPriority="high"
              />
            </picture>
          </figure>
          <div className="showcase-caption">
            <span>See the whole shoot. Find the right shot.</span>
            {motionAllowed && (
              <button
                className="motion-control"
                onClick={() => setMotionPaused((paused) => !paused)}
                aria-pressed={motionPaused}
              >
                {motionPaused ? <Play size={14} /> : <Pause size={14} />}
                {motionPaused ? "Resume motion" : "Pause motion"}
              </button>
            )}
          </div>
          <div className="showcase-heading">
            <h2>
              All those moments.
              <br />
              Right where you need them.
            </h2>
            <p>
              AI groups your footage by what’s in it. Browse scenes, subjects,
              and details, then search in your own words.
            </p>
          </div>
          <div className="showcase-subjects">
            {subjects.map((subject) => (
              <figure key={subject.poster} className="showcase-subject">
                <div className="showcase-crop" data-parallax="0.04">
                  <img
                    data-motion-image
                    src={`/demo/${subject.poster}-640.webp`}
                    alt={subject.description}
                    width={640}
                    height={360}
                    loading="lazy"
                  />
                </div>
                <figcaption>{subject.name}</figcaption>
              </figure>
            ))}
          </div>
        </section>
        <section
          id="workflow"
          className="landing-workflow"
          aria-labelledby="workflow-title"
        >
          <h2 id="workflow-title">Less sorting. More finding.</h2>
          <div className="workflow-steps">
            <article>
              <span>01</span>
              <h3>Drop in your footage.</h3>
              <p>
                Upload video files or a whole folder. Keep your originals
                intact.
              </p>
            </article>
            <article>
              <span>02</span>
              <h3>Let AI organize it.</h3>
              <p>
                RUSHES analyzes what’s in each shot and groups footage by its
                content.
              </p>
            </article>
            <article>
              <span>03</span>
              <h3>Find what you need.</h3>
              <p>
                Browse categories, search in plain English, and export the
                footage you want.
              </p>
            </article>
          </div>
        </section>
      </main>
      <PublicFooter />
      {showStickyCta && (
        <div className="landing-mobile-cta">
          <Link href="/signup" className="primary">
            Organize your footage <ArrowRight size={18} />
          </Link>
        </div>
      )}
    </div>
  );
}
