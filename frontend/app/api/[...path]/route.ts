import { NextRequest } from "next/server";

const allowed = [
  /^health$/, /^sources$/, /^radar$/, /^securities$/, /^stocks\/(TWSE|TPEX)\/[A-Z0-9]{2,12}$/,
  /^portfolio$/, /^portfolio\/trades(?:\/[0-9]+)?$/, /^reports$/, /^evidence$/, /^valuation$/,
  /^themes(?:\/members)?$/, /^watchlist(?:\/(TWSE|TPEX)\/[A-Z0-9]{2,12})?$/,
];

type Context = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, context: Context) {
  const path = (await context.params).path.join("/");
  if (!allowed.some((route) => route.test(path))) return new Response(null, { status: 404 });
  if (request.method !== "GET") {
    const site = request.headers.get("sec-fetch-site");
    const origin = request.headers.get("origin");
    const host = request.headers.get("host");
    if (site !== "same-origin" || !origin || URL.canParse(origin) === false || new URL(origin).host !== host) {
      return Response.json({ detail: "請從網站內送出表單" }, { status: 403 });
    }
    if (request.method === "POST" && !request.headers.get("content-type")?.startsWith("application/json")) {
      return Response.json({ detail: "僅接受 JSON" }, { status: 415 });
    }
  }
  try {
    let body: string | undefined;
    if (request.method === "POST") {
      if (Number(request.headers.get("content-length")) > 16_384) return new Response(null, { status: 413 });
      const reader = request.body?.getReader();
      if (reader) {
        const decoder = new TextDecoder();
        let total = 0;
        body = "";
        while (true) {
          const part = await reader.read();
          if (part.done) break;
          total += part.value.length;
          if (total > 16_384) {
            await reader.cancel();
            return new Response(null, { status: 413 });
          }
          body += decoder.decode(part.value, { stream: true });
        }
        body += decoder.decode();
      }
    }
    const endpoint = new URL(path + request.nextUrl.search, process.env.TWMI_BACKEND_URL || "http://127.0.0.1:8000/");
    const upstream = await fetch(endpoint, {
      method: request.method,
      headers: { "Content-Type": "application/json" },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(12000),
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("Content-Type") || "application/json", "Cache-Control": "private, no-store" },
    });
  } catch {
    return Response.json({ detail: "資料服務暫時無法連線" }, { status: 503 });
  }
}

export const GET = forward;
export const POST = forward;
export const DELETE = forward;
