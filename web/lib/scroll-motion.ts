type Layer = {
  frame: HTMLElement;
  image: HTMLElement;
  speed: number;
  center: number;
  current: number;
  transform: string;
};

export function startScrollMotion(root: HTMLElement) {
  const layers: Layer[] = Array.from(
    root.querySelectorAll<HTMLElement>("[data-parallax]"),
  ).flatMap((frame) => {
    const image = frame.querySelector<HTMLElement>("[data-motion-image]");
    return image
      ? [
          {
            frame,
            image,
            speed: Number(frame.dataset.parallax),
            center: 0,
            current: new DOMMatrixReadOnly(getComputedStyle(image).transform)
              .m42,
            transform: "",
          },
        ]
      : [];
  });
  let frameId = 0;
  let previousTime = 0;

  function draw(time: number) {
    frameId = 0;
    const elapsed = previousTime
      ? Math.min((time - previousTime) / 1000, 0.1)
      : 1 / 60;
    previousTime = time;
    const damping = 1 - Math.exp(-elapsed * 9);
    const center = window.scrollY + window.innerHeight / 2;
    let moving = false;
    for (const layer of layers) {
      const target = Math.max(
        -60,
        Math.min(60, (center - layer.center) * layer.speed),
      );
      const difference = target - layer.current;
      if (Math.abs(difference) > 0.05) {
        layer.current += difference * damping;
        moving = true;
      } else {
        layer.current = target;
      }
      const transform = `translate3d(0, ${layer.current.toFixed(3)}px, 0)`;
      if (layer.transform !== transform) {
        layer.image.style.transform = transform;
        layer.transform = transform;
      }
    }
    if (moving) frameId = requestAnimationFrame(draw);
    else previousTime = 0;
  }

  function schedule() {
    if (!frameId && !document.hidden) frameId = requestAnimationFrame(draw);
  }

  function measure() {
    for (const layer of layers) {
      const rect = layer.frame.getBoundingClientRect();
      layer.center = rect.top + window.scrollY + rect.height / 2;
    }
    schedule();
  }

  function visibilityChanged() {
    if (document.hidden) {
      cancelAnimationFrame(frameId);
      frameId = 0;
      previousTime = 0;
    } else measure();
  }

  const resize = new ResizeObserver(measure);
  resize.observe(root);
  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", measure);
  document.addEventListener("visibilitychange", visibilityChanged);
  measure();

  return () => {
    cancelAnimationFrame(frameId);
    resize.disconnect();
    window.removeEventListener("scroll", schedule);
    window.removeEventListener("resize", measure);
    document.removeEventListener("visibilitychange", visibilityChanged);
  };
}
