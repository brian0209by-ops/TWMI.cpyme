# TWMI Signals V1.4

臺灣上市及上櫃市場的個人研究工具。網站提供市場總覽、官方及主題產業雷達、個股研究、持股與關注清單、研究報告。

## 部署至自用主機

需要 Docker Compose、可持久化的磁碟與從主機連到臺灣交易所官方 API 的網路。前端對外使用 HTTPS，後端及 PostgreSQL 留在 Compose 網路。

1. 複製 `.env.example` 至 `.env`，設定 URL 安全字元的資料庫密碼，以及至少 16 字元的網站密碼。
2. 在儲存庫根目錄啟動服務並匯入開放資料。
   ```sh
   docker compose up -d --build --wait
   docker compose exec -T backend python -m backend.cli collect
   ```
3. 本機開啟 `http://127.0.0.1:3000`，使用設定的帳密登入。遠端使用時，將 HTTPS 反向代理指向主機的迴路埠，保留原始 Host 標頭。健康路徑為 `/api/health`，需登入。
4. 匯入已與 TWSE、TPEx 公告核對的行事曆。CSV 欄位為 `market,day,status,evidence_url`，狀態為 `open` 或 `closed`。涵蓋每個市場每天，包括週末與例外休市。
   ```sh
   docker compose cp ./private/calendar.csv backend:/tmp/twmi-calendar.csv
   docker compose exec -T backend python -m backend.cli calendar /tmp/twmi-calendar.csv
   ```
5. 在主機以臺北時間排程，在儲存庫目錄執行下列命令，將時段換成 12:00、14:00、18:00。若使用 GitHub Actions 報告排程，設定 `TWMI_ENABLE_REPORTS=true` 以及 `production-reports` 環境的 `DATABASE_URL`，資料庫須能由該執行器安全存取。兩種排程選一種即可。
   ```sh
   docker compose exec -T backend python -m backend.cli run-slot 18:00 --date "$(TZ=Asia/Taipei date +%F)"
   ```

## 資料和研究口徑

- 資料日、出表日、擷取時間分開記錄。行情採同一交易日的上市與上櫃普通股，缺市場或涵蓋不足時，市場占比保留空值。產業活躍度比較當日成交額和前 5／20 個已核對交易日均值。相對報酬採同日等權參考價報酬複利後與市場基準比較。
- 官方產業以交易所及代碼分組，歷史分類以首次已知的官方快照日期開始。主題可重疊，並記錄個別成分的證據、可信度與有效期間。ETF 可持有及研究，普通股產業統計排除 ETF。
- 已開放的資料集包含兩市場主檔、行情、月營收、個股本益比，以及上櫃逐檔法人。上市逐檔法人與盤中行情待確認授權及取得方式。上櫃法人外陸資欄位採官方排除外資自營商口徑，單位為股。
- 訂單、產能、產量、出貨與 ETF 曝險可附來源人工登錄。保留產品、單位、揭露類型、發布時間及有效證據，並以規則產出可追溯的結論。這一版採固定報告模板與確定性規則。
- 八年 IRR 使用有來源的手動財務輸入，套用公告個股 P/E 或同市場同產業正 P/E 等權平均。後者是本系統衍生統計，顯示樣本數與資料日。配息率超過 100% 須明確確認才試算。
- 5／20 日情境在 18:00 有當日收盤及關注或持股資料時建立。原始情境追加保存，到期使用對應交易日收盤核對價格變化。到期價格報酬不含交易成本，尚未建置完整策略回測或機率校準。
- 12:00 使用最近可得收盤。14:00、18:00 顯示資料是否已到齊。未知交易日暫停該市場報告。主機自行保留資料庫備份，市場快照、交易、個人研究及憑證存放於 Git 之外。

[政府資料開放授權](https://data.gov.tw/license) · [證交所 OpenAPI](https://openapi.twse.com.tw/) · [櫃買中心 OpenAPI](https://www.tpex.org.tw/openapi/) · [證交所行事曆](https://accessibility.twse.com.tw/zh/trading/holiday.html) · [櫃買中心 115 年開休市表](https://www.tpex.org.tw/storage/eb_data/11411/114007545811-1.pdf)

## 開發驗證

```sh
python -m pip install -r backend/requirements.txt pytest==9.2.0
python -m pytest -q
cd frontend
npm ci
npm run build
```

設定 `TWMI_TEST_DATABASE_URL` 指向獨立測試服務，以執行 PostgreSQL 整合測試。測試使用新建的隨機命名資料庫並自動清理。開發模式可用 `TWMI_LOCAL_DEV=1 npm run dev`，預設 API 為 `http://127.0.0.1:8000/`，正式建置必須設定存取密碼。
