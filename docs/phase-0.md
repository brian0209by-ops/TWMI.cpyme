# Phase 0｜資料接入與驗收

## 本機稽核

使用 Python 3.12。在儲存庫根目錄執行下列命令。第一項命令使用合成測試資料，第二項讀取使用者自行提供的舊版 SQLite。稽核程式只輸出完整性與筆數。

```sh
python -m unittest discover -s tests -v
python audit_legacy.py /path/to/legacy.sqlite
```

## 資料接入順序

1. 先登錄上市及上櫃公司主檔、官方產業分類和來源授權。保留產業分類有效期間，ETF 自產業統計排除。
2. 從官方盤後行情開始，保存資料交易日、擷取時間及來源。驗證重跑去重和資料覆蓋率，再計算產業成交值及占比。
3. 接入月營收與法人資料前，逐資料集確認機器介接、保存和衍生使用依據。缺漏欄位顯示待取得。
4. 以 FastAPI 和 PostgreSQL 提供查詢，Next.js 提供 Dashboard 與 Industry Radar。CI 須驗證空庫遷移及資料庫約束。

官方文件：[政府資料開放授權](https://data.gov.tw/license) · [證交所 OpenAPI](https://openapi.twse.com.tw/) · [櫃買中心 OpenAPI](https://www.tpex.org.tw/openapi/)。
