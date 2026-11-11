"use client";

import type { ReactNode } from "react";
import { timestamp, type Attribution } from "./data";

export function SourceNote({ sources, title = "資料來源" }: { sources?: Attribution[]; title?: string }) {
  if (!sources?.length) return null;
  return <div className="source-note"><span>{title}</span>{sources.map((source, index) =>
    <span key={source.url + index}><a href={source.url} target="_blank" rel="noreferrer">{source.publisher}{source.name ? "／" + source.name : ""}</a>
      {source.observed_at && " · 擷取 " + timestamp(source.observed_at)}
      {source.license_url && <> · <a href={source.license_url} target="_blank" rel="noreferrer">政府資料開放授權第 1 版</a></>}
    </span>
  )}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}
