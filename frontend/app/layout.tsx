import type { Metadata } from "next";
import "./style.css";

export const metadata: Metadata = {
  title: "TWMI Signals｜臺股研究",
  description: "臺股產業行情與基本面研究工作台",
  robots: { index: false, follow: false },
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-Hant-TW"><body>{children}</body></html>;
}
