from dataclasses import dataclass

LICENSE = "https://data.gov.tw/license"


@dataclass(frozen=True)
class Source:
    id: str
    market: str
    kind: str
    name: str
    url: str
    documentation: str
    minimum: int
    permitted: bool = True

    @property
    def publisher(self):
        return "臺灣證券交易所" if self.market == "TWSE" else "證券櫃檯買賣中心"

    @property
    def license_url(self):
        return LICENSE if self.permitted else None


def official(market, kind, name, path, dataset, minimum):
    base = "https://openapi.twse.com.tw/v1" if market == "TWSE" else "https://www.tpex.org.tw/openapi/v1"
    return Source(f"{market.lower()}-{kind}", market, kind, name, base + path,
                  f"https://data.gov.tw/dataset/{dataset}", minimum)


SOURCES = {
    source.id: source for source in (
        official("TWSE", "master", "上市公司基本資料", "/opendata/t187ap03_L", 18419, 800),
        official("TPEX", "master", "上櫃公司基本資料", "/mopsfin_t187ap03_O", 25036, 650),
        official("TWSE", "quotes", "上市個股日成交資訊", "/exchangeReport/STOCK_DAY_ALL", 11549, 800),
        official("TPEX", "quotes", "上櫃股票行情", "/tpex_mainboard_daily_close_quotes", 11370, 650),
        official("TWSE", "revenue", "上市公司每月營業收入彙總表", "/opendata/t187ap05_L", 18420, 800),
        official("TPEX", "revenue", "上櫃公司每月營業收入彙總表", "/mopsfin_t187ap05_O", 56510, 650),
        official("TWSE", "multiples", "上市個股日本益比", "/exchangeReport/BWIBBU_ALL", 11547, 750),
        official("TPEX", "multiples", "上櫃個股本益比", "/tpex_mainboard_peratio_analysis", 11373, 600),
        official("TPEX", "flow", "上櫃股票三大法人買賣明細", "/tpex_3insti_daily_trading", 11856, 650),
        Source("twse-flow", "TWSE", "flow", "上市三大法人個股明細",
               "https://www.twse.com.tw/fund/T86", "https://www.twse.com.tw/fund/T86?response=html", 0, False),
        Source("twse-intraday", "TWSE", "intraday", "上市盤中行情",
               "https://www.twse.com.tw/zh/products/information/use.html",
               "https://www.twse.com.tw/zh/products/information/use.html", 0, False),
        Source("tpex-intraday", "TPEX", "intraday", "上櫃盤中行情",
               "https://www.tpex.org.tw/zh-tw/service/data/product/post.html",
               "https://www.tpex.org.tw/zh-tw/service/data/product/post.html", 0, False),
    )
}


def register_sources(db):
    for s in SOURCES.values():
        db.execute("""
            INSERT INTO source_registry
              (id,market,kind,name,publisher,url,documentation,license_url,checked_on,permitted,limits)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,DATE '2026-11-12',%s,%s)
            ON CONFLICT (id) DO NOTHING
        """, (s.id, s.market, s.kind, s.name, s.publisher, s.url, s.documentation,
              s.license_url, s.permitted,
              "官方頻率上限及發布時刻待確認" if s.permitted else "尚未確認正式自動取得與保存依據"))
