import { createHash, timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

function digest(value: string) {
  return createHash("sha256").update(value).digest();
}

export function proxy(request: NextRequest) {
  const password = process.env.TWMI_ACCESS_PASSWORD;
  if (!password || password.length < 16) {
    if (process.env.NODE_ENV === "development" && process.env.TWMI_LOCAL_DEV === "1") {
      return NextResponse.next();
    }
    return new NextResponse("存取設定尚未完成", { status: 503 });
  }
  const username = process.env.TWMI_ACCESS_USER || "owner";
  const expected = Buffer.from(username + ":" + password).toString("base64");
  const actual = request.headers.get("authorization") || "";
  if (!timingSafeEqual(digest(actual), digest("Basic " + expected))) {
    return new NextResponse("請登入 TWMI Signals", {
      status: 401,
      headers: { "WWW-Authenticate": 'Basic realm="TWMI Signals", charset="UTF-8"', "Cache-Control": "no-store" },
    });
  }
  return NextResponse.next();
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
