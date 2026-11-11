"use client";

import { useEffect, useState, type ReactNode } from "react";
import { api, billions, format, MARKET, METRICS, NATURE, timestamp, type Group, type Portfolio, type Radar, type Report, type Security, type Source } from "./data";
import { Empty, SourceNote } from "./shared";
import { PortfolioPanel, StockPanel, ThemeForm } from "./research-panels";

const tabs = [["dashboard","總覽","◈"],["radar","產業雷達","▥"],["stocks","個股研究","◎"],["portfolio","持股與關注","▤"],["reports","研究報告","◷"]] as const;
type Tab = typeof tabs[number][0];

function useData<T>(path: string, revision = 0) {
  const [result, setResult] = useState<{data?: T; error?: string; key?: string}>({});
  const key = path + "@" + revision;
  useEffect(() => {
    if (!path) return;
    const request = new AbortController();
    api<T>(path,"GET",undefined,request.signal).then(data => {
      if (!request.signal.aborted) setResult({data,key});
    }).catch(error => {
      if (!request.signal.aborted) setResult({error:error.message,key});
    });
    return () => request.abort();
  }, [path,key]);
  return result.key === key ? result : {};
}

function PanelTitle({ title, detail, children }: { title: string; detail?: string; children?: ReactNode }) {
  return <div className="panel-title"><div><h2>{title}</h2>{detail && <p>{detail}</p>}</div>{children}</div>;
}

function RadarBars({ rows, select }: { rows: Group[]; select: (id: string) => void }) {
  const visible = rows.filter(row => row.turnover != null).slice(0,7);
  const maximum = Math.max(...visible.map(row => Number(row.turnover)),1);
  if (!visible.length) return <Empty>目前無可用產業成交資料。</Empty>;
  return <div className="bars">{visible.map(row =>
    <button className="bar-row" key={row.id} onClick={() => select(row.id)}>
      <span className="bar-label">{row.label}<small>{MARKET[row.market]}</small></span>
      <span className="bar-track"><span style={{width: (Number(row.turnover) / maximum * 100) + "%"}} /></span>
      <strong>{billions(row.turnover)}</strong>
    </button>
  )}</div>;
}

function SourceList({ sources }: { sources?: Source[] }) {
  if (!sources?.length) return <Empty>來源登錄尚未載入。</Empty>;
  return <div className="source-list">{sources.map(source => {
    const label = !source.permitted ? "待授權" : source.outcome === "error" ? "擷取失敗" : source.market_day ? "已取得" : "待取得";
    return <div key={source.id} className="source-row"><div><a href={source.documentation} target="_blank" rel="noreferrer">{source.name}</a>
      <small>{source.market_day ? `資料期 ${source.market_day} · 擷取 ${timestamp(source.observed_at)}` : "尚無已匯入資料"}</small>
      {source.outcome === "error" && <small>最近嘗試 {timestamp(source.attempted_at)}</small>}</div>
      <span className={label === "已取得" ? "badge ok" : "badge"}>{label}</span></div>;
  })}</div>;
}

function RadarTable({ rows, select }: { rows: Group[]; select: (id: string) => void }) {
  if (!rows.length) return <Empty>此範圍目前無可用產業資料。</Empty>;
  return <div className="table-wrap"><table><thead><tr>
    <th>產業</th><th>成交值</th><th>占比</th><th>涵蓋</th><th>活躍度</th><th>上漲比例</th><th>相對報酬</th><th>外陸資淨買賣股數</th><th>營收年增</th>
  </tr></thead><tbody>{rows.map(row => <tr key={row.id}>
    <td><button className="text-link" onClick={() => select(row.id)}>{row.label}</button><small>{MARKET[row.market]}</small></td>
    <td>{billions(row.turnover)}</td><td>{format(row.share_pct,"%")}</td><td>{row.coverage_count}/{row.members_count}</td>
    <td>{format(row.activity_pct,"%")}</td><td>{format(row.breadth_pct,"%")}</td>
    <td>{format(row.relative_period_pp," 個百分點")}</td><td>{format(row.flow.foreign_net)}</td>
    <td>{format(row.revenue.yoy_pct,"%")}<small>{row.revenue.month?.slice(0,7) || "待取得"} · {row.revenue.count}/{row.members_count}</small></td>
  </tr>)}</tbody></table></div>;
}

function ReportList({ rows }: { rows?: Report[] }) {
  if (!rows?.length) return <Empty>尚無排程報告。交易日行事曆確認後，已執行的時段會顯示於此。</Empty>;
  return <div className="report-list">{rows.map(report => <details key={report.day+report.slot}>
    <summary><strong>{report.day} · {report.slot}</strong><span className="badge">{report.status==="complete"?"已彙整":"部分資料"}</span></summary>
    <p className="muted">資料截點 {timestamp(report.cutoff)} · 產出 {timestamp(report.completed_at)} · 新增 {report.body.scenarios_created} 筆情境</p>
    {report.body.markets.map(item => <div className="report-market" key={item.market}>
      <strong>{MARKET[item.market]}</strong> <span>{item.data_day || "—"}</span>
      <span className="badge">{({last_close:"最近收盤",complete:"已彙整",pending:"待更新",closed:"休市",calendar_pending:"行事曆待確認"} as Record<string,string>)[item.status]}</span>
      {item.leaders?.filter(row=>row.turnover!=null).map(row => <p key={row.id}>{row.label}　{billions(row.turnover)}</p>)}
      <SourceNote sources={item.quotes_sources}/>
    </div>)}
  </details>)}</div>;
}

export default function Workspace() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [market, setMarket] = useState<keyof typeof MARKET>("ALL");
  const [classification, setClassification] = useState("official");
  const [period, setPeriod] = useState("5");
  const [day, setDay] = useState("");
  const [group, setGroup] = useState("");
  const [search, setSearch] = useState("");
  const [security, setSecurity] = useState<Security | null>(null);
  const [revision, setRevision] = useState(0);

  const radarQuery = new URLSearchParams({market,classification,period});
  if (day) radarQuery.set("day",day);
  const radar = useData<Radar>(tab==="dashboard" ? "radar" : tab==="radar" ? "radar?"+radarQuery : "", revision);
  const detail = useData<Radar>(tab==="radar" && group ? "radar?"+radarQuery+"&group="+encodeURIComponent(group) : "", revision);
  const sources = useData<Source[]>(tab==="dashboard" || tab==="radar" ? "sources" : "", revision);
  const portfolio = useData<Portfolio>(tab==="dashboard" || tab==="portfolio" ? "portfolio" : "", revision);
  const securities = useData<Security[]>(tab==="stocks" && search.trim() ? "securities?q="+encodeURIComponent(search.trim()) : "");
  const reports = useData<Report[]>(tab==="reports" ? "reports" : "",revision);

  function selectGroup(id: string) {
    if (tab==="dashboard") { setMarket("ALL"); setClassification("official"); setDay(""); }
    setGroup(id);
    setTab("radar");
  }
  function selectStock(instrument: Security) {
    setSecurity(instrument);
    setTab("stocks");
  }
  const display = radar.data;
  const updated = () => setRevision(value=>value+1);
  const leaders = display?.rows || [];
  const coverage = leaders.reduce((acc,row) => acc + row.coverage_count,0);
  const members = leaders.reduce((acc,row) => acc + row.members_count,0);

  return <div className="shell">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="TWMI Signals 總覽"><span className="brand-icon"><i/><i/><i/></span><span><b>TWMI</b> Signals<small>臺股研究工作台</small></span></a>
      <nav aria-label="研究工作台">{tabs.map(([id,name,icon]) => <button type="button" key={id} className={tab===id?"nav active":"nav"} aria-current={tab===id?"page":undefined}
        onClick={()=>{setGroup("");setTab(id);}}><span aria-hidden>{icon}</span>{name}</button>)}</nav>
      <div className="side-footer"><span className="badge ok"><i className="dot"/>個人研究</span><small>TWMI SIGNALS V1.4</small></div>
    </aside>
    <main>
      <header className="top"><div className="top-kicker">TWMI / {tabs.find(([id])=>id===tab)?.[1]}</div>
        <span className="status-date"><i className="dot"/> {display?.day ? `行情資料日 ${display.day}` : "Asia/Taipei"}</span></header>
      <div className="workspace">
      {tab==="dashboard" && <>
        <section className="hero"><div><h1>市場總覽</h1><p>追蹤臺股盤後交易關注度與營運資料。</p></div><button className="primary" onClick={()=>setTab("radar")}>開啟產業雷達 <span aria-hidden>↗</span></button></section>
        {radar.error && <div className="error" role="alert">{radar.error}</div>}
        <div className="stat-grid">
          <div className="stat"><span>普通股成交值</span><strong>{billions(display?.market_turnover)}</strong><small>{display?.market_complete ? "上市與上櫃同日統計" : "待兩市場同日資料齊備"}</small></div>
          <div className="stat"><span>行情涵蓋</span><strong>{members ? `${coverage.toLocaleString()} / ${members.toLocaleString()}` : "—"}</strong><small>已取得行情／當日已分類證券</small></div>
          <div className="stat"><span>有交易紀錄的持股</span><strong>{portfolio.data ? portfolio.data.positions.filter(p=>p.quantity>0).length : "—"}</strong><small>{portfolio.data?.valuation_day ? "估值日 " + portfolio.data.valuation_day : "等待持股及同日行情"}</small></div>
        </div>
        <div className="dashboard-grid">
          <section className="panel"><PanelTitle title="產業成交值" detail="依成交金額排序，單位為新臺幣億元"><span className="badge">官方分類</span></PanelTitle>
            {display ? <RadarBars rows={leaders} select={selectGroup}/> : <Empty>{radar.error || "載入行情中…"}</Empty>}
            {!display?.market_complete && <p className="hint">目前顯示已到齊市場的資料，全市場占比待更新。</p>}
            <SourceNote sources={display?.sources}/>
          </section>
          <section className="panel"><PanelTitle title="資料更新" detail="交易日與擷取時間分別記錄"/><SourceList sources={sources.data}/></section>
        </div>
        <section className="panel"><PanelTitle title="關注清單"><button className="secondary" onClick={()=>setTab("portfolio")}>管理清單</button></PanelTitle>
          {portfolio.data?.positions.some(p=>p.watched) ? <div className="watch-row">{portfolio.data.positions.filter(p=>p.watched).map(p=><button className="secondary" key={p.market+p.code} onClick={()=>selectStock(p)}>{p.code} {p.name}</button>)}</div> : <Empty>加入要追蹤的公司或 ETF。</Empty>}
        </section>
      </>}
      {tab==="radar" && <>
        <section className="hero"><div><h1>產業雷達</h1><p>比較產業成交活躍度、法人買賣超與營收變化。</p></div></section>
        <section className="panel"><div className="controls">
          <label>市場<select value={market} onChange={e=>{setGroup("");setMarket(e.target.value as keyof typeof MARKET);}}>{Object.entries(MARKET).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
          <label>分類<select value={classification} onChange={e=>{setGroup("");setClassification(e.target.value);}}><option value="official">官方產業</option><option value="theme">主題產業</option></select></label>
          <label>比較期間<select value={period} onChange={e=>setPeriod(e.target.value)}><option value="5">5 交易日</option><option value="20">20 交易日</option></select></label>
          <label>行情日期<input type="date" value={day} onChange={e=>setDay(e.target.value)}/></label>
          {day && <button className="secondary" onClick={()=>setDay("")}>回到最近行情</button>}
        </div>
        <p className="hint">{display?.day ? `資料日 ${display.day} · ` : ""}{display?.market_complete ? "普通股成交占比可計算" : "市場資料或分類涵蓋不足，部分指標待更新"}</p>
        {radar.error ? <div className="error" role="alert">{radar.error}</div> : display ? <RadarTable rows={leaders} select={selectGroup}/> : <Empty>載入產業資料中…</Empty>}
        <SourceNote sources={display?.sources}/><SourceNote sources={display?.flow_sources} title="法人來源"/>
        </section>
        {classification==="theme" && <ThemeForm onUpdated={updated}/>}
        {group && <section className="panel"><PanelTitle title={detail.data?.rows[0]?.label || "產業明細"} detail="成分與當日行情">
          <button className="secondary" onClick={()=>setGroup("")}>關閉</button></PanelTitle>
          {detail.data?.rows[0] ? <>
            <div className="detail-strip"><span>投信淨買賣股數 <strong>{format(detail.data.rows[0].flow.trust_net)}</strong></span><span>自營商淨買賣股數 <strong>{format(detail.data.rows[0].flow.dealer_net)}</strong></span><span>法人資料涵蓋 <strong>{detail.data.rows[0].flow.count}/{detail.data.rows[0].members_count}</strong></span></div>
            <div className="table-wrap"><table><thead><tr><th>成分股</th><th>收盤價</th><th>漲跌</th><th>成交值</th></tr></thead><tbody>
              {detail.data.rows[0].members?.map(item=><tr key={item.market+item.code}><td><button className="text-link" onClick={()=>selectStock(item)}>{item.code} {item.name}</button>
              {item.role && <small>{item.role} · 證據可信度 {{high:"高",medium:"中",low:"低"}[item.confidence || ""]} · {item.valid_from}{item.valid_to ? " 至 "+item.valid_to : ""} · <a href={item.evidence_url} target="_blank" rel="noreferrer">關聯來源</a></small>}</td><td>{format(item.close)}</td><td>{format(item.change)}</td><td>{billions(item.turnover)}</td></tr>)}
            </tbody></table></div>
            <SourceNote sources={detail.data.sources}/><SourceNote sources={detail.data.rows[0].revenue.sources} title="營收來源"/>
            {detail.data.rows[0].revenue.count>0 && <p className="hint">可比較營收家數 · 成長 {detail.data.rows[0].revenue.growing} · 持平 {detail.data.rows[0].revenue.unchanged} · 衰退 {detail.data.rows[0].revenue.declining}</p>}
            <h3>成分股營運證據</h3>
            {detail.data.rows[0].evidence?.length ? <div className="source-list">{detail.data.rows[0].evidence.map(row=><div key={row.id} className="source-row">
              <div><strong>{row.code} · {METRICS[row.metric]} · {NATURE[row.nature]}</strong><small>{row.period} · {row.note}</small>
              <small>{format(row.value,row.unit ? " "+row.unit : "")} {row.product} · 發布 {timestamp(row.published_at)}</small></div>
              <a href={row.evidence_url} target="_blank" rel="noreferrer">證據來源</a>
            </div>)}</div> : <Empty>尚無成分股營運證據。</Empty>}
          </> : <Empty>{detail.error || (detail.data ? "此日無對應產業資料。" : "載入明細中…")}</Empty>}
        </section>}
      </>}
      {tab==="stocks" && <>
        <section className="hero"><div><h1>個股研究</h1><p>查看行情、營收、營運證據與研究情境。</p></div></section>
        <section className="panel"><label className="search-label">股票代號或名稱<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="輸入代號或公司名稱" maxLength={32}/></label>
          <div className="watch-row">{securities.data?.map(row=><button key={row.market+row.code} className="secondary" onClick={()=>selectStock(row)}>{row.code} {row.name}</button>)}</div>
          {securities.data?.length===0 && <p className="hint">查無符合的證券。</p>}
          {securities.error && <p className="error">{securities.error}</p>}
        </section>
        {security && <StockPanel key={security.market+security.code} selection={security}/>}
      </>}
      {tab==="portfolio" && <><section className="hero"><div><h1>持股與關注</h1><p>管理交易紀錄、持股成本及個人研究清單。</p></div></section>
        {portfolio.error && <p className="error">{portfolio.error}</p>}<PortfolioPanel data={portfolio.data} onUpdated={updated} onSelect={selectStock}/>
      </>}
      {tab==="reports" && <><section className="hero"><div><h1>研究報告</h1><p>檢視臺北時間 12:00、14:00 與 18:00 的研究紀錄。</p></div></section>
        <section className="panel"><PanelTitle title="報告紀錄"/>{reports.error ? <p className="error">{reports.error}</p> : <ReportList rows={reports.data}/>}</section></>}
      </div>
    </main>
  </div>;
}
