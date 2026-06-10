import { Fragment, type ReactNode } from "react";

const PAGE_REF_PATTERN = /\{reference:\s*pageNumber:\s*([^}]+)\}/gi;

export function formatPageNumber(raw: string): string {
  const value = Number.parseFloat(raw.trim());
  if (Number.isNaN(value)) return raw.trim();
  return Number.isInteger(value) ? String(value) : String(value);
}

export function extractPageReferences(content: string): string[] {
  const seen = new Set<string>();
  const pages: string[] = [];

  for (const match of content.matchAll(PAGE_REF_PATTERN)) {
    const formatted = formatPageNumber(match[1]);
    if (seen.has(formatted)) continue;
    seen.add(formatted);
    pages.push(formatted);
  }

  return pages;
}

export function stripPageReferences(content: string): string {
  return content.replace(/\s*\{reference:\s*pageNumber:\s*[^}]+}\s*/gi, " ").replace(/  +/g, " ");
}

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let remaining = text;
  let key = 0;

  while (remaining.length > 0) {
    const boldMatch = remaining.match(/^\*\*([^*]+)\*\*/);
    if (boldMatch) {
      nodes.push(<strong key={key++}>{boldMatch[1]}</strong>);
      remaining = remaining.slice(boldMatch[0].length);
      continue;
    }

    const nextBold = remaining.search(/\*\*/);
    if (nextBold === -1) {
      nodes.push(<Fragment key={key++}>{remaining}</Fragment>);
      break;
    }

    if (nextBold > 0) {
      nodes.push(<Fragment key={key++}>{remaining.slice(0, nextBold)}</Fragment>);
      remaining = remaining.slice(nextBold);
      continue;
    }

    nodes.push(<Fragment key={key++}>{remaining[0]}</Fragment>);
    remaining = remaining.slice(1);
  }

  return nodes;
}

interface Props {
  content: string;
}

export function ChatMessageContent({ content }: Props) {
  const cleaned = stripPageReferences(content);
  const lines = cleaned.split("\n");
  const blocks: ReactNode[] = [];
  let listItems: ReactNode[] = [];

  const flushList = () => {
    if (listItems.length === 0) return;
    blocks.push(
      <ol key={`list-${blocks.length}`} className="chat-list">
        {listItems}
      </ol>,
    );
    listItems = [];
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      continue;
    }

    const listMatch = trimmed.match(/^\d+\.\s+(.*)$/);
    if (listMatch) {
      listItems.push(
        <li key={`item-${listItems.length}`}>{renderInline(listMatch[1])}</li>,
      );
      continue;
    }

    flushList();
    blocks.push(
      <p key={`p-${blocks.length}`} className="chat-paragraph">
        {renderInline(trimmed)}
      </p>,
    );
  }

  flushList();

  return <div className="chat-content">{blocks}</div>;
}
