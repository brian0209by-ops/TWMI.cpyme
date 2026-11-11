"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api, billions, DIRECTION, format, MARKET, METRICS, NATURE, timestamp, type Benchmark, type NumberValue, type Portfolio, type Security, type Stock } from "./data";
import { Empty, SourceNote } from "./shared";

function field(data: FormData, name: string) { return String(data.get(name) ?? "").trim(); }

function MarketField() {
  return <label>市場<select name="market" defaultValue="TWSE"><option value="TWSE">上市</option><option value="TPEX">上櫃</option></select></label>;
}

function CodeField() {
  return <label>證券代號<input name="code" required pattern="[A-Za-z0-9]{2,12}" placeholder="輸入代號"/></label>;
}

function Message({ value }: { value: string }) {
  return value ? <p className="hint" role="status">{value}</p> : null;
}

function useAction(onUpdated?: () => void) {
  const [message,setMessage] = useState("");
  const [pending,setPending] = useState(false);
  async function run(task: () => Promise<unknown>, success = "已儲存") {
    setPending(true);
    setMessage("");
    try { await task(); setMessage(success); onUpdated?.(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "暫時無法儲存"); }
    finally { setPending(false); }
  }
  return { message,pending,run };
}

export function ThemeForm({ onUpdated }: { onUpdated: () => void }) {
  const [themes,setThemes] = useState<{slug:string;name:string}[]>([]);
  const action = useAction(onUpdated);
  useEffect(() => { api<typeof themes>("themes").then(setThemes).catch(()=>{}); },[]);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void action.run(()=>api("themes/members","POST",{
      market:field(data,"market"),code:field(data,"code").toUpperCase(),theme:field(data,"theme"),
      start:field(data,"start"),end:field(data,"end") || null,role:field(data,"role"),
      confidence:field(data,"confidence"),evidence_url:field(data,"evidence_url"),
    }));
  }
  return <section className="panel"><details><summary><strong>新增主題成分</strong></summary><form className="entry-form" onSubmit={submit}>
    <MarketField/><CodeField/>
    <label>主題<select name="theme" required>{themes.map(row=><option key={row.slug} value={row.slug}>{row.name}</option>)}</select></label>
    <label>生效日<input type="date" name="start" required/></label><label>終止日（不含）<input type="date" name="end"/></label>
    <label>供應鏈角色<input name="role" maxLength={100} required/></label>
    <label>證據可信度<select name="confidence"><option value="high">高</option><option value="medium">中</option><option value="low">低</option></select></label>
    <label>證據網址<input type="url" name="evidence_url" required placeholder="https://"/></label>
    <button className="primary" disabled={action.pending || themes.length===0}>儲存主題關聯</button>
  </form><Message value={action.message}/></details></section>;
}

function EvidenceForm({ stock, onUpdated }: { stock: Security; onUpdated: () => void }) {
  const action = useAction(onUpdated);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void action.run(()=>api("evidence","POST",{
      market:stock.market,code:stock.code,metric:field(data,"metric"),nature:field(data,"nature"),
      direction:field(data,"direction"),period:field(data,"period"),published_at:field(data,"published_at") + ":00+08:00",
      value:field(data,"value") || null,unit:field(data,"unit") || null,product:field(data,"product") || null,
      evidence_url:field(data,"evidence_url"),note:field(data,"note"),
    }));
  }
  return <details><summary><strong>新增營運證據</strong></summary><form className="entry-form" onSubmit={submit}>
    <label>指標<select name="metric">{Object.entries(METRICS).filter(([id])=>id.startsWith("etf_")===(stock.kind==="etf")).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
    <label>證據類別<select name="nature">{Object.entries(NATURE).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
    <label>證據方向<select name="direction" defaultValue="unknown">{Object.entries(DIRECTION).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
    <label>資料期間<input type="date" name="period" required/></label><label>發布時間（臺北）<input type="datetime-local" name="published_at" required/></label>
    <label>數值<input type="number" step="any" name="value"/></label><label>單位<input name="unit" maxLength={40}/></label>
    <label>產品或品項<input name="product" maxLength={120}/></label>
    <label>證據網址<input type="url" name="evidence_url" required placeholder="https://"/></label>
    <label className="wide">證據內容<textarea name="note" rows={3} maxLength={1500} required/></label>
    <button className="primary" disabled={action.pending}>新增證據</button>
  </form><Message value={action.message}/></details>;
}

function ValuationForm({ stock }: { stock: Stock }) {
  const action = useAction();
  const [result,setResult] = useState<{irr_pct:NumberValue;present_at_8_pct:NumberValue;terminal:NumberValue;benchmark:Benchmark} | null>(null);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const split = (s:string) => s.split(/[,，\s]+/).filter(Boolean);
    setResult(null);
    void action.run(async()=>{
      setResult(await api("valuation","POST",{
        eps_history:split(field(data,"eps")),dividends:split(field(data,"div")),nav:field(data,"nav"),
        entry:field(data,"entry"),market:stock.market,code:stock.code,benchmark:field(data,"benchmark"),
        financial_source:field(data,"financial_source"),allow_excess_payout:data.has("allow"),
      }));
    },"已完成情境試算");
  }
  return <section className="panel"><h2>八年 IRR 試算</h2>
    <p className="hint">輸入同口徑的財務資料並選擇已取得的本益比基準。</p>
    <form className="entry-form" onSubmit={submit}>
      <label className="wide">八年 EPS（最舊到最新，以逗號分隔）<input required name="eps"/></label>
      <label className="wide">八年每股現金股利（最舊到最新）<input required name="div"/></label>
      <label>最新每股淨值<input type="number" name="nav" min="0.000001" step="any" required/></label>
      <label>買進價格<input type="number" name="entry" min="0.000001" step="any" required/></label>
      <label>期末本益比基準<select name="benchmark" required defaultValue=""><option value="" disabled>選擇基準</option>
        <option value="industry" disabled={stock.multiples.industry?.pe==null}>產業正本益比等權平均 {format(stock.multiples.industry?.pe," 倍")}</option>
        <option value="company" disabled={stock.multiples.company?.pe==null}>個股公告本益比 {format(stock.multiples.company?.pe," 倍")}</option>
      </select></label>
      <label className="wide">財務原始來源<input type="url" name="financial_source" placeholder="https://" required/></label>
      <label className="inline wide"><input type="checkbox" name="allow"/>確認超額配息情境</label>
      <button className="primary" disabled={action.pending}>計算</button>
    </form><Message value={action.message}/>
    {result && <><p className="hint">{result.benchmark.method} · 資料日 {result.benchmark.day} {result.benchmark.sample_count ? `· ${result.benchmark.sample_count} 家樣本` : ""}</p><SourceNote sources={[result.benchmark]}/><div className="detail-strip"><span>年化 IRR <strong>{format(result.irr_pct,"%")}</strong></span><span>目標年化 8% 對應價格 <strong>{format(result.present_at_8_pct)}</strong></span><span>期末估值 <strong>{format(result.terminal)}</strong></span></div></>}
  </section>;
}

export function StockPanel({ selection }: { selection: Security }) {
  const [stock,setStock] = useState<Stock | null>(null);
  const [error,setError] = useState("");
  const [revision,setRevision] = useState(0);
  const [period,setPeriod] = useState(5);
  useEffect(()=>{
    const controller = new AbortController();
    api<Stock>("stocks/"+selection.market+"/"+selection.code,"GET",undefined,controller.signal)
      .then(data=>{if (!controller.signal.aborted) {setStock(data);setError("");}})
      .catch(error=>{if (!controller.signal.aborted) setError(error.message);});
    return ()=>controller.abort();
  },[selection,revision]);
  if (!stock) return <section className="panel"><Empty>{error || "載入個股研究中…"}</Empty></section>;
  const quote=stock.quotes[0];
  const revenue=stock.revenue[0];
  return <>
    <section className="panel"><div className="panel-title"><div><h2>{stock.code} {stock.name}</h2><p>{MARKET[stock.market]} · {stock.kind==="etf"?"ETF":"普通股"}</p></div>
      <label>行情期間<select value={period} onChange={e=>setPeriod(Number(e.target.value))}><option value={5}>5 交易日</option><option value={20}>20 交易日</option><option value={60}>60 交易日</option></select></label></div>
      {error && <Message value={error}/>}
      <div className="detail-strip"><span>最新收盤 <strong>{format(quote?.close)}</strong></span><span>行情日 <strong>{quote?.day || "—"}</strong></span><span>{period} 日均價 <strong>{format(stock.moving_averages[String(period)])}</strong></span></div>
      {stock.quotes.length ? <div className="table-wrap"><table><thead><tr><th>交易日</th><th>收盤</th><th>漲跌</th><th>成交值</th></tr></thead><tbody>{stock.quotes.slice(0,period).map(q=><tr key={q.day}><td>{q.day}</td><td>{format(q.close)}</td><td>{format(q.change)}</td><td>{billions(q.turnover)}</td></tr>)}</tbody></table></div> : <Empty>尚無行情。</Empty>}
      <SourceNote sources={quote ? [quote] : []}/>
    </section>
    {stock.kind==="ordinary" && <section className="panel"><h2>月營收</h2>
      {revenue ? <><div className="detail-strip"><span>資料月 <strong>{revenue.month.slice(0,7)}</strong></span><span>月營收（千元） <strong>{format(revenue.revenue_thousand)}</strong></span><span>年增率 <strong>{format(revenue.yoy_pct,"%")}</strong></span><span>月增率 <strong>{format(revenue.mom_pct,"%")}</strong></span><span>近三月累計年增率 <strong>{format(stock.revenue_3m_yoy_pct,"%")}</strong></span></div>
        <SourceNote sources={[revenue]}/></> : <Empty>尚無可用月營收。</Empty>}
    </section>}
    <section className="panel"><h2>{stock.kind==="etf"?"ETF 曝險與追蹤":"基本面證據"}</h2>
      {stock.expectation && <><div className="signal"><span>規則判斷</span><strong>{stock.expectation.conclusion}</strong><small>{stock.expectation.invalidation}</small></div>
        <div className="check-grid">{stock.expectation.checks.map(check=><div key={check.metric}><span>{check.label}</span><span className="badge">{DIRECTION[check.state]}</span></div>)}</div></>}
      {stock.evidence.length>0 ? <div className="table-wrap"><table><thead><tr><th>指標</th><th>類別／方向</th><th>期間</th><th>數值／產品</th><th>證據</th></tr></thead><tbody>{stock.evidence.map(row=><tr key={row.id}>
        <td>{METRICS[row.metric]}</td><td>{NATURE[row.nature]} · {DIRECTION[row.direction]}</td><td>{row.period}<small>發布 {timestamp(row.published_at)}</small></td><td>{format(row.value,row.unit?" "+row.unit:"")}<small>{row.product}</small></td><td className="wrap">{row.note}<small><a href={row.evidence_url} target="_blank" rel="noreferrer">原始來源 ↗</a></small></td>
      </tr>)}</tbody></table></div> : <Empty>尚未登錄研究證據。</Empty>}
      <EvidenceForm stock={stock} onUpdated={()=>setRevision(i=>i+1)}/>
    </section>
    {stock.kind==="ordinary" && <><ValuationForm stock={stock}/><section className="panel"><h2>5／20 交易日情境</h2>
      {stock.scenarios.length ? stock.scenarios.map(row=><details key={row.id}><summary><strong>{row.base_day} · {row.horizon} 日 · {row.body.conclusion}</strong></summary><p>多頭　{row.body.bull}</p><p>盤整　{row.body.base}</p><p>空頭　{row.body.bear}</p><p>失效條件　{row.body.invalidation}</p><p>到期價格報酬（未計成本） {format(row.gross_price_return,"%")}</p></details>) :
        <Empty>把證券加入關注清單，待 18:00 報告取得同日行情後建立情境。</Empty>}
    </section></>}
  </>;
}

export function PortfolioPanel({ data,onUpdated,onSelect }: { data?: Portfolio;onUpdated:()=>void;onSelect:(security:Security)=>void }) {
  const action = useAction(onUpdated);
  function submit(event: FormEvent<HTMLFormElement>, trade: boolean) {
    event.preventDefault();
    const form=event.currentTarget;
    const fields = new FormData(form);
    const instrument = {market:field(fields,"market"),code:field(fields,"code").toUpperCase()};
    void action.run(async()=>{
      if (trade) await api("portfolio/trades","POST",{...instrument,side:field(fields,"side"),
        traded_on:field(fields,"traded_on"),quantity:Number(field(fields,"quantity")),price:field(fields,"price"),fees:field(fields,"fees") || "0"});
      else await api("watchlist","POST",instrument);
      form.reset();
    });
  }
  return <>
    <section className="panel"><div className="panel-title"><div><h2>持股一覽</h2><p>庫存成本使用移動加權平均，納入你填寫的費用。</p></div>
      <span className="badge">總市值 {format(data?.total_market_value," 元")}</span></div>
      {data?.positions.length ? <div className="table-wrap"><table><thead><tr><th>標的</th><th>股數</th><th>平均成本</th><th>市值</th><th>配置</th><th>已實現</th><th>未實現</th><th>估值日</th><th>關注</th></tr></thead>
        <tbody>{data.positions.map(row=><tr key={row.market+row.code}><td><button className="text-link" onClick={()=>onSelect(row)}>{row.code} {row.name}</button></td><td>{row.quantity}</td><td>{format(row.average_cost)}</td><td>{format(row.market_value)}</td><td>{format(row.allocation_pct,"%")}</td><td>{format(row.realized)}</td><td>{format(row.unrealized)}</td><td>{row.mark?.day || "—"}<small>{row.mark?.url && <a href={row.mark.url} target="_blank" rel="noreferrer">行情來源</a>}</small></td>
          <td>{row.watched ? <button className="secondary" disabled={action.pending} onClick={()=>void action.run(()=>api("watchlist/"+row.market+"/"+row.code,"DELETE"),"已移除關注")}>移除</button> : "—"}</td></tr>)}</tbody></table></div> : <Empty>尚未加入持股或關注標的。</Empty>}
      <form className="entry-form" onSubmit={e=>submit(e,false)}><MarketField/><CodeField/><button className="secondary" disabled={action.pending}>加入關注</button></form>
      <Message value={action.message}/>
    </section>
    <section className="panel"><h2>交易紀錄</h2><form className="entry-form" onSubmit={e=>submit(e,true)}>
      <MarketField/><CodeField/><label>交易日期<input type="date" name="traded_on" required/></label>
      <label>方向<select name="side"><option value="buy">買進</option><option value="sell">賣出</option></select></label>
      <label>股數<input type="number" name="quantity" min="1" step="1" required/></label>
      <label>成交價格<input type="number" name="price" min="0.000001" step="any" required/></label>
      <label>總費用（含自行輸入稅費）<input type="number" name="fees" min="0" step="any"/></label>
      <button className="primary" disabled={action.pending}>新增交易</button>
    </form>
    {data?.positions.some(row=>row.trades.length>0) && <div className="table-wrap"><table><thead><tr><th>標的</th><th>交易日</th><th>方向</th><th>股數</th><th>成交價</th><th>費用</th><th>管理</th></tr></thead>
      <tbody>{data.positions.flatMap(row=>row.trades.map(trade=><tr key={trade.id}><td>{row.code} {row.name}</td><td>{trade.traded_on}</td><td>{trade.side==="buy"?"買進":"賣出"}</td><td>{trade.quantity}</td><td>{format(trade.price)}</td><td>{format(trade.fees)}</td>
        <td><button className="secondary" disabled={action.pending} onClick={()=>{if (window.confirm("要刪除這筆交易嗎？")) void action.run(()=>api("portfolio/trades/"+trade.id,"DELETE"),"已刪除交易");}}>刪除</button></td></tr>))}</tbody></table></div>}
    <Message value={action.message}/>
    </section>
  </>;
}
