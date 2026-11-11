CREATE TABLE valuation_multiple (
    batch_id bigint NOT NULL REFERENCES import_batch,
    market text NOT NULL,
    code text NOT NULL,
    day date NOT NULL,
    pe numeric,
    pb numeric,
    yield_pct numeric,
    PRIMARY KEY (batch_id,code)
);
CREATE INDEX valuation_lookup ON valuation_multiple(market,code,day DESC);
