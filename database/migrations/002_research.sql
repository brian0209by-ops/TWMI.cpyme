CREATE TABLE operating_evidence (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    market text NOT NULL,
    code text NOT NULL,
    metric text NOT NULL CHECK (metric IN ('orders','demand','capacity','production','shipments','inventory','gross_margin','operating_margin','eps','roe','valuation','etf_exposure','etf_concentration','etf_tracking')),
    nature text NOT NULL CHECK (nature IN ('actual','guidance','estimate','inference')),
    direction text NOT NULL CHECK (direction IN ('supports','opposes','neutral','unknown')),
    period date NOT NULL,
    published_at timestamptz NOT NULL,
    observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    value numeric,
    unit text,
    product text,
    evidence_url text NOT NULL,
    note text NOT NULL,
    FOREIGN KEY (market, code) REFERENCES security,
    CHECK ((value IS NULL) = (unit IS NULL))
);

CREATE TABLE watchlist (
    market text NOT NULL,
    code text NOT NULL,
    PRIMARY KEY (market, code),
    FOREIGN KEY (market, code) REFERENCES security
);

CREATE TABLE portfolio_trade (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    market text NOT NULL,
    code text NOT NULL,
    traded_on date NOT NULL,
    side text NOT NULL CHECK (side IN ('buy','sell')),
    quantity bigint NOT NULL CHECK (quantity > 0),
    price numeric NOT NULL CHECK (price > 0),
    fees numeric NOT NULL CHECK (fees >= 0),
    FOREIGN KEY (market, code) REFERENCES security
);

CREATE TABLE research_report (
    day date NOT NULL,
    slot text NOT NULL CHECK (slot IN ('12:00','14:00','18:00')),
    cutoff timestamptz NOT NULL,
    completed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    status text NOT NULL CHECK (status IN ('complete','partial')),
    body jsonb NOT NULL,
    PRIMARY KEY (day, slot)
);

CREATE TABLE research_scenario (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    market text NOT NULL,
    code text NOT NULL,
    base_day date NOT NULL,
    cutoff timestamptz NOT NULL,
    horizon integer NOT NULL CHECK (horizon IN (5,20)),
    base_price numeric NOT NULL CHECK (base_price > 0),
    body jsonb NOT NULL,
    FOREIGN KEY (market,code) REFERENCES security,
    UNIQUE (market,code,base_day,cutoff,horizon)
);

CREATE TABLE scenario_outcome (
    scenario_id bigint PRIMARY KEY REFERENCES research_scenario,
    target_day date NOT NULL,
    close numeric NOT NULL CHECK (close > 0),
    quote_batch_id bigint NOT NULL REFERENCES import_batch,
    gross_price_return numeric NOT NULL,
    evaluated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE FUNCTION protect_research_record() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Research records are append-only';
END;
$$;
CREATE TRIGGER scenarios_append_only BEFORE UPDATE OR DELETE ON research_scenario
    FOR EACH ROW EXECUTE FUNCTION protect_research_record();
CREATE TRIGGER reports_append_only BEFORE UPDATE OR DELETE ON research_report
    FOR EACH ROW EXECUTE FUNCTION protect_research_record();
