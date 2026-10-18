import "./fonts.css";
import "./styles.css";
import { mountStory } from "./story";
import { mountTool } from "./tool";

const reduced = matchMedia("(prefers-reduced-motion: reduce)");
const nav = document.querySelector<HTMLElement>(".nav")!;
const book = document.querySelector<HTMLElement>(".book")!;
const cover = document.querySelector<HTMLElement>(".cover")!;

// The cover hinges open on its spine as the first screen scrolls away.
function openCover() {
  const span = book.offsetHeight - window.innerHeight;
  const c = Math.min(1, Math.max(0, window.scrollY / Math.max(span * 0.62, 1)));
  if (!reduced.matches) {
    const eased = c < 0.5 ? 2 * c * c : 1 - Math.pow(-2 * c + 2, 2) / 2;
    cover.style.transform = `rotateY(${-104 * eased}deg)`;
    cover.style.visibility = c >= 1 ? "hidden" : "visible";
  }
  cover.inert = c > 0.55;
  nav.dataset.solid = String(c > 0.5 || reduced.matches && window.scrollY > window.innerHeight * 0.9);
}

let storyUpdate: (() => void) | null = null;
let queued = false;
function onScroll() {
  if (queued) return;
  queued = true;
  requestAnimationFrame(() => {
    queued = false;
    openCover();
    storyUpdate?.();
  });
}

openCover();
window.addEventListener("scroll", onScroll, { passive: true });
window.addEventListener("resize", onScroll);
reduced.addEventListener("change", () => { cover.style.transform = ""; onScroll(); });

mountStory(document.getElementById("story-ledger")!).then((u) => {
  storyUpdate = u;
  u();
});
mountTool();
