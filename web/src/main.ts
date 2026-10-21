import "@fontsource-variable/hubot-sans/standard.css";
import "@fontsource-variable/mona-sans/standard.css";
import "@fontsource-variable/martian-mono/standard.css";
import "./styles.css";
import { mountStory } from "./story";
import { mountTool } from "./tool";
import { engrave, mountSeal, type SealStatus } from "./seal";

const nav = document.querySelector<HTMLElement>(".nav")!;

let storyUpdate: (() => void) | null = null;
let queued = false;
function onScroll() {
  if (queued) return;
  queued = true;
  requestAnimationFrame(() => {
    queued = false;
    nav.dataset.scrolled = String(window.scrollY > 8);
    storyUpdate?.();
  });
}
window.addEventListener("scroll", onScroll, { passive: true });
window.addEventListener("resize", onScroll);

// The hero seal is the sample statement's own: drawn from the same audit the story walks through.
async function mountHeroSeal() {
  const canvas = document.getElementById("hero-seal") as HTMLCanvasElement | null;
  if (!canvas) return;
  const audit = await (await fetch("samples/story.audit.json")).json();
  const rows = (audit.rows as { balance: number | null; status: SealStatus }[]).map((r) => ({ balance: r.balance, status: r.status }));
  await document.fonts.ready;
  const seal = mountSeal(canvas, rows);
  engrave(seal, 1800);
  let t = 0, first = true;
  new ResizeObserver(() => {
    if (first) { first = false; return; }
    clearTimeout(t);
    t = window.setTimeout(() => { seal.resize(); seal.draw(1); }, 120);
  }).observe(canvas);
}

mountHeroSeal();
mountStory(document.getElementById("story-ledger")!).then((u) => {
  storyUpdate = u;
  u();
});
mountTool();
