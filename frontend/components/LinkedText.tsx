import { Fragment } from "react";
import type { LookupLink } from "../lib/types";

function escapeRegExp(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Plain text in which every name of an official lookup site (from the API's
 * `links`) becomes a hyperlink that opens in a new tab.
 */
export function LinkedText({ text, links }: { text: string; links?: LookupLink[] }) {
  if (!links || links.length === 0) {
    return <>{text}</>;
  }

  // Longest names first, so a longer name is not split by a shorter one inside it.
  const sorted = [...links].sort((a, b) => b.text.length - a.text.length);
  const byText = new Map(sorted.map((link) => [link.text, link]));
  const pattern = new RegExp(`(${sorted.map((link) => escapeRegExp(link.text)).join("|")})`, "g");

  return (
    <>
      {text.split(pattern).map((part, index) => {
        const link = byText.get(part);
        if (!link) {
          return <Fragment key={index}>{part}</Fragment>;
        }
        return (
          <a
            className="lookup-link"
            href={link.url}
            key={index}
            rel="noopener noreferrer"
            target="_blank"
            title={`${link.label}（另開新視窗）`}
          >
            {part}
          </a>
        );
      })}
    </>
  );
}
