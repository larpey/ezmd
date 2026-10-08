import DOMPurify from "dompurify";
import { Marked } from "marked";

const FRONTMATTER = /^---\r?\n[\s\S]*?\r?\n---\r?\n?/;

export function stripFrontmatter(md: string): string {
  return md.replace(FRONTMATTER, "");
}

export function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

const marked = new Marked({
  gfm: true,
  async: false,
  renderer: {
    // Raw HTML inside Markdown is shown escaped, never rendered (spec part4 4.1.2 step 6).
    html: ({ text }) => escapeHtml(text),
    // Remote images are not loaded: no request may leave the origin. Show a link instead.
    image: ({ href, text }) => `<a href="${escapeHtml(href)}" class="md-image">[image: ${escapeHtml(text || href)}]</a>`,
  },
});

let hooked = false;
function ensureHooks(): void {
  if (hooked) return;
  hooked = true;
  DOMPurify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName === "A") {
      node.setAttribute("rel", "noopener noreferrer nofollow");
      node.setAttribute("target", "_blank");
    }
  });
}

/** Renders Markdown (frontmatter stripped) to sanitized HTML. */
export function renderMarkdown(md: string): string {
  ensureHooks();
  const html = marked.parse(stripFrontmatter(md)) as string;
  return DOMPurify.sanitize(html, { USE_PROFILES: { html: true }, FORBID_TAGS: ["img", "style", "form", "iframe"] });
}
