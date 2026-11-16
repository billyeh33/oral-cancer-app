import type { RagSource } from "../lib/types";

/** Short label: "手冊 p.63" for the handbook, "處置流程" for the flowchart, the site name for web sources. */
export function sourceLabel(source: RagSource) {
  if (source.source_title.includes("處置流程")) {
    return "處置流程";
  }
  if (!source.page) {
    return source.section || "官方衛教";
  }
  return `手冊 p.${source.page}`;
}

/** Small page tags; hovering shows the full citation. */
export function SourceTags({ sources }: { sources: RagSource[] }) {
  const unique = Array.from(new Map(sources.map((s) => [sourceLabel(s), s])).values());
  if (unique.length === 0) {
    return null;
  }

  return (
    <span className="source-tags">
      {unique.map((source) => (
        <span className="source-tag" key={source.chunk_id} title={source.citation}>
          {sourceLabel(source)}
        </span>
      ))}
    </span>
  );
}
