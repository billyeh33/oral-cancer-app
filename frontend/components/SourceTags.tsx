import type { RagSource } from "../lib/types";

/** Short label for a source: "手冊 p.63" for the handbook, "處置流程" for the flowchart. */
export function sourceLabel(source: RagSource) {
  return source.source_title.includes("處置流程") ? "處置流程" : `手冊 p.${source.page}`;
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
