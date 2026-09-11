"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { PublicHeader } from "@/components/public-header";
import { PublicFooter } from "@/components/public-footer";
import "./landing.css";

const examples = [
  {
    name: "Coastline",
    poster: "coast",
    description: "Sunlit cliffs and sea stacks along a rugged coastline",
  },
  {
    name: "Waves",
    poster: "waves",
    description: "White surf breaking around dark rocks",
  },
  {
    name: "Aerials",
    poster: "aerial",
    description: "An aerial view of the coastline, grassy cliffs and ocean",
  },
];

export function Landing() {
  const hero = useRef<HTMLElement>(null);
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
    <div className="landing-page">
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
            <a className="text-link" href="#workflow">
              See how it works
            </a>
          </div>
        </section>
        <section
          className="landing-demo"
          aria-label="Example organized footage library"
        >
          <div className="demo-heading">
            <div>
              <p className="demo-example-label">
                An example of an organized library
              </p>
              <h2>Coastal shoot</h2>
            </div>
            <p className="demo-static-note">
              Static illustration · sample imagery
            </p>
          </div>
          <figure className="demo-viewer">
            <picture className="demo-poster">
              <source
                type="image/webp"
                srcSet="/demo/coast-640.webp 640w, /demo/coast-960.webp 960w, /demo/coast-1440.webp 1440w, /demo/coast-1672.webp 1672w"
                sizes="(max-width: 700px) 100vw, 90vw"
              />
              <img
                src="/demo/coast-1440.webp"
                alt={examples[0].description}
                width={1672}
                height={941}
                fetchPriority="high"
              />
            </picture>
          </figure>
          <div className="demo-results-heading">
            <h3>From one shoot to useful categories.</h3>
          </div>
          <div className="demo-library">
            {examples.map((example) => (
              <figure key={example.poster} className="demo-clip">
                <img
                  src={`/demo/${example.poster}-640.webp`}
                  alt={example.description}
                  width={640}
                  height={360}
                  loading="lazy"
                />
                <figcaption>{example.name}</figcaption>
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
