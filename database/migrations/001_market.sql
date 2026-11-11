CREATE TABLE source_registry (
    id text PRIMARY KEY,
    market text CHECK (market IN ('TWSE', 'TPEX')),
    kind text NOT NULL,
    name text NOT NULL,
    publisher text NOT NULL,
    url text NOT NULL,
    documentation text NOT NULL,
    license_url text,
    checked_on date NOT NULL,
    permitted boolean NOT NULL,
    limits text NOT NULL
);

CREATE TABLE import_batch (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id text NOT NULL REFERENCES source_registry,
    market_day date,
    observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    content_sha256 text NOT NULL CHECK (length(content_sha256) = 64),
    row_count integer NOT NULL CHECK (row_count > 0),
    UNIQUE (source_id, content_sha256)
);

CREATE TABLE import_attempt (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id text NOT NULL REFERENCES source_registry,
    attempted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    outcome text NOT NULL CHECK (outcome IN ('updated', 'unchanged', 'error')),
    detail text
);

CREATE TABLE security (
    market text NOT NULL CHECK (market IN ('TWSE', 'TPEX')),
    code text NOT NULL CHECK (code ~ '^[A-Z0-9]{2,12}$'),
    name text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('ordinary', 'etf')),
    PRIMARY KEY (market, code)
);

CREATE TABLE official_membership (
    market text NOT NULL,
    code text NOT NULL,
    industry text NOT NULL,
    valid_during daterange NOT NULL CHECK (NOT isempty(valid_during)),
    batch_id bigint NOT NULL REFERENCES import_batch,
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    FOREIGN KEY (market, code) REFERENCES security
);
CREATE INDEX official_membership_lookup ON official_membership(market,code);

CREATE TABLE theme (slug text PRIMARY KEY, name text NOT NULL);
INSERT INTO theme VALUES
    ('semiconductor','半導體供應鏈'), ('ai','AI 與資料中心'),
    ('components','電子零組件'), ('energy','電力與能源'),
    ('finance','金融與支付'), ('consumer','消費與傳統產業');

CREATE TABLE theme_membership (
    market text NOT NULL,
    code text NOT NULL,
    theme_slug text NOT NULL REFERENCES theme,
    valid_during daterange NOT NULL CHECK (NOT isempty(valid_during)),
    role text NOT NULL,
    evidence_url text NOT NULL,
    confidence text NOT NULL CHECK (confidence IN ('high', 'medium', 'low')),
    observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    FOREIGN KEY (market, code) REFERENCES security
);
CREATE INDEX theme_membership_lookup ON theme_membership(market,code,theme_slug);

CREATE FUNCTION prevent_membership_overlap() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE has_overlap boolean;
BEGIN
    -- Serialize changes on the referenced security, including at higher isolation levels.
    UPDATE security SET kind=kind WHERE market=NEW.market AND code=NEW.code AND kind='ordinary';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Membership requires an ordinary share' USING ERRCODE='23503';
    END IF;
    IF TG_TABLE_NAME='official_membership' THEN
        SELECT EXISTS (
            SELECT 1 FROM official_membership WHERE market=NEW.market AND code=NEW.code
                AND id<>NEW.id AND valid_during && NEW.valid_during
        ) INTO has_overlap;
    ELSE
        SELECT EXISTS (
            SELECT 1 FROM theme_membership WHERE market=NEW.market AND code=NEW.code
                AND theme_slug=NEW.theme_slug AND id<>NEW.id AND valid_during && NEW.valid_during
        ) INTO has_overlap;
    END IF;
    IF has_overlap THEN
        RAISE EXCEPTION 'Membership intervals overlap' USING ERRCODE='23P01';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER official_membership_no_overlap BEFORE INSERT OR UPDATE ON official_membership
    FOR EACH ROW EXECUTE FUNCTION prevent_membership_overlap();
CREATE TRIGGER theme_membership_no_overlap BEFORE INSERT OR UPDATE ON theme_membership
    FOR EACH ROW EXECUTE FUNCTION prevent_membership_overlap();

CREATE TABLE quote (
    batch_id bigint NOT NULL REFERENCES import_batch,
    market text NOT NULL,
    code text NOT NULL,
    day date NOT NULL,
    open numeric CHECK (open > 0),
    high numeric CHECK (high > 0),
    low numeric CHECK (low > 0),
    close numeric CHECK (close > 0),
    change numeric,
    volume bigint CHECK (volume >= 0),
    turnover bigint CHECK (turnover >= 0),
    PRIMARY KEY (batch_id, code)
);
CREATE INDEX quote_lookup ON quote (market, day DESC, code);

CREATE TABLE revenue (
    batch_id bigint NOT NULL REFERENCES import_batch,
    market text NOT NULL,
    code text NOT NULL,
    month date NOT NULL CHECK (extract(day from month) = 1),
    export_day date NOT NULL,
    revenue_thousand numeric,
    prior_month_thousand numeric,
    prior_year_thousand numeric,
    PRIMARY KEY (batch_id, code, month)
);
CREATE INDEX revenue_lookup ON revenue (market, code, month DESC);

CREATE TABLE institutional_flow (
    batch_id bigint NOT NULL REFERENCES import_batch,
    market text NOT NULL,
    code text NOT NULL,
    day date NOT NULL,
    foreign_net bigint,
    trust_net bigint,
    dealer_net bigint,
    PRIMARY KEY (batch_id, code)
);

CREATE TABLE market_calendar (
    market text NOT NULL CHECK (market IN ('TWSE', 'TPEX')),
    day date NOT NULL,
    is_open boolean NOT NULL,
    evidence_url text NOT NULL,
    PRIMARY KEY (market, day)
);
