export type NumberValue = string | number | null;
export type Attribution = { url: string; publisher: string; license_url?: string | null; observed_at?: string; market_day?: string; name?: string };
export type Market = "TWSE" | "TPEX";
export type Security = { market: Market; code: string; name: string; kind: "ordinary" | "etf" };
export type Source = Attribution & { id: string; market: Market; kind: string; permitted: boolean; outcome?: string; attempted_at?: string; documentation: string };
export type Group = {
  id: string; label: string; market: Market | "ALL"; turnover: NumberValue; share_pct: NumberValue;
  coverage_count: number; members_count: number; breadth_pct: NumberValue; activity_pct: NumberValue;
  relative_day_pp: NumberValue; relative_period_pp?: NumberValue;
  flow: { foreign_net: NumberValue; trust_net: NumberValue; dealer_net: NumberValue; count: number };
  revenue: { month: string | null; yoy_pct: NumberValue; count: number; growing?: number; unchanged?: number; declining?: number; sources?: Attribution[]; observed_at?: string };
  members?: (Security & { turnover: NumberValue; close: NumberValue; change: NumberValue; role?: string; confidence?: string; evidence_url?: string; valid_from?: string; valid_to?: string })[];
  evidence?: (Evidence & {market:Market; code:string})[];
};
export type Radar = {
  day: string | null; market: string; market_complete: boolean; market_turnover: NumberValue;
  rows: Group[]; sources: Attribution[]; flow_sources: Attribution[];
};
export type Quote = Attribution & { day: string; close: NumberValue; change: NumberValue; turnover: NumberValue };
export type Revenue = Attribution & { month: string; export_day: string; revenue_thousand: NumberValue; yoy_pct: NumberValue; mom_pct: NumberValue };
export type Evidence = { id: number; metric: string; nature: string; direction: string; period: string; published_at: string; value: NumberValue; unit?: string; product?: string; evidence_url: string; note: string };
export type Scenario = { id: number; base_day: string; horizon: number; cutoff: string; target_day?: string; gross_price_return: NumberValue; body: { conclusion: string; bull: string; base: string; bear: string; invalidation: string } };
export type Benchmark = Attribution & {pe: NumberValue; day: string; method: string; sample_count?: number};
export type Stock = Security & {
  multiples: Partial<Record<"industry"|"company",Benchmark>>;
  quotes: Quote[]; revenue: Revenue[]; industry: string | null; evidence: Evidence[]; scenarios: Scenario[];
  revenue_3m_yoy_pct: NumberValue; moving_averages: Record<string, NumberValue>;
  expectation: { conclusion: string; invalidation: string; checks: { metric: string; label: string; state: string; evidence: Evidence[] }[] } | null;
};
export type Trade = { id: number; side: "buy" | "sell"; traded_on: string; quantity: number; price: NumberValue; fees: NumberValue };
export type Position = Security & { watched: boolean; quantity: number; average_cost: NumberValue; realized: NumberValue; unrealized: NumberValue; market_value: NumberValue; allocation_pct: NumberValue; mark: Quote | null; trades: Trade[] };
export type Portfolio = { positions: Position[]; total_market_value: NumberValue; valuation_day: string | null };
export type Report = { day: string; slot: string; cutoff: string; completed_at: string; status: string; body: { markets: { market: Market; status: string; data_day?: string; leaders?: Group[]; quotes_sources?: Attribution[] }[]; scenarios_created: number } };

export const MARKET = { ALL: "上市＋上櫃", TWSE: "上市", TPEX: "上櫃" };
export const NATURE: Record<string,string> = { actual: "實際揭露", guidance: "公司展望", estimate: "第三方估計", inference: "推論" };
export const DIRECTION: Record<string,string> = { supports:"支持", opposes:"反對", neutral:"中性", unknown:"待確認" };
export const METRICS: Record<string,string> = {
  orders:"訂單", demand:"產業需求", capacity:"產能", production:"產量", shipments:"出貨",
  inventory:"庫存", gross_margin:"毛利率", operating_margin:"營業利益率", eps:"EPS", roe:"ROE",
  valuation:"估值", etf_exposure:"成分與產業曝險", etf_concentration:"集中度", etf_tracking:"追蹤市場",
};

export function format(value: NumberValue | undefined, suffix = "", digits = 2) {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  return Number(value).toLocaleString("zh-TW", { maximumFractionDigits: digits }) + suffix;
}

export function billions(value: NumberValue | undefined) {
  return value == null ? "—" : format(Number(value) / 1e8, " 億");
}

export function timestamp(value?: string | null) {
  return value ? new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei", dateStyle: "short", timeStyle: "short", hourCycle: "h23",
  }).format(new Date(value)) : "—";
}

export async function api<T>(path: string, method = "GET", body?: object, signal?: AbortSignal): Promise<T> {
  const response = await fetch("/api/" + path, {
    method, cache: "no-store", signal, headers: { "Content-Type": "application/json" },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "資料未能載入，請檢查欄位後重試。");
  }
  return payload;
}
