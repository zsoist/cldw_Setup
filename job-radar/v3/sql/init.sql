-- Job Radar V3 Schema
BEGIN;

CREATE TABLE IF NOT EXISTS companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    name_normalized TEXT NOT NULL,
    careers_url TEXT,
    ats_platform TEXT,
    watchlist BOOLEAN DEFAULT false,
    auto_suppress BOOLEAN DEFAULT false,
    suppress_reason TEXT,
    first_seen_at TIMESTAMPTZ DEFAULT now(),
    last_seen_at TIMESTAMPTZ DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb,
    CONSTRAINT uq_company_normalized UNIQUE (name_normalized)
);

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id),
    title TEXT NOT NULL,
    title_normalized TEXT NOT NULL,
    url TEXT NOT NULL,
    url_canonical TEXT NOT NULL,
    source TEXT NOT NULL,
    description_snippet TEXT,
    requirements TEXT[],
    tech_stack TEXT[],
    seniority_signal TEXT,
    yoe_min INT,
    yoe_max INT,
    salary_min INT,
    salary_max INT,
    salary_currency TEXT,
    remote_policy TEXT,
    timezone_signal TEXT,
    contractor_ok BOOLEAN DEFAULT false,
    location_raw TEXT,
    score_opportunity SMALLINT NOT NULL DEFAULT 0,
    score_junior SMALLINT NOT NULL DEFAULT 0,
    score_colombia SMALLINT NOT NULL DEFAULT 0,
    score_composite SMALLINT NOT NULL DEFAULT 0,
    score_method TEXT DEFAULT 'rules',
    confidence TEXT DEFAULT 'medium',
    hidden_junior BOOLEAN DEFAULT false,
    apply_url TEXT,
    apply_method TEXT,
    apply_notes TEXT,
    content_hash TEXT NOT NULL,
    dedup_cluster_id UUID,
    status TEXT DEFAULT 'new',
    posted_at TIMESTAMPTZ,
    discovered_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ,
    CONSTRAINT uq_job_url_canonical UNIQUE (url_canonical),
    CONSTRAINT uq_job_content_hash UNIQUE (content_hash)
);

CREATE INDEX IF NOT EXISTS idx_jobs_composite ON jobs (score_composite DESC) WHERE status NOT IN ('dismissed', 'expired', 'closed');
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs (source);
CREATE INDEX IF NOT EXISTS idx_jobs_discovered ON jobs (discovered_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs (company_id);
CREATE INDEX IF NOT EXISTS idx_jobs_hidden_junior ON jobs (hidden_junior) WHERE hidden_junior = true;

CREATE TABLE IF NOT EXISTS job_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    reason TEXT,
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedback_job ON job_feedback (job_id);
CREATE INDEX IF NOT EXISTS idx_feedback_action ON job_feedback (action);

CREATE TABLE IF NOT EXISTS dedup_index (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url_canonical TEXT,
    content_hash TEXT,
    title_normalized TEXT,
    company_normalized TEXT,
    cluster_id UUID,
    created_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_dedup_url ON dedup_index (url_canonical);
CREATE INDEX IF NOT EXISTS idx_dedup_hash ON dedup_index (content_hash);
CREATE INDEX IF NOT EXISTS idx_dedup_expires ON dedup_index (expires_at);

CREATE TABLE IF NOT EXISTS digest_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    digest_type TEXT NOT NULL,
    jobs_shown INT DEFAULT 0,
    jobs_saved_24h INT DEFAULT 0,
    jobs_dismissed_24h INT DEFAULT 0,
    content_hash TEXT,
    sent_at TIMESTAMPTZ DEFAULT now()
);

-- Views
CREATE OR REPLACE VIEW active_jobs AS
SELECT j.*, c.name as company_name, c.careers_url as company_careers_url, c.ats_platform
FROM jobs j
JOIN companies c ON j.company_id = c.id
WHERE j.status NOT IN ('dismissed', 'expired', 'closed')
  AND j.discovered_at > now() - INTERVAL '21 days'
  AND c.auto_suppress = false
ORDER BY j.score_composite DESC;

CREATE OR REPLACE VIEW hot_leads AS
SELECT * FROM active_jobs
WHERE score_composite >= 70 AND status = 'new';

CREATE OR REPLACE VIEW hidden_junior_jobs AS
SELECT * FROM active_jobs
WHERE hidden_junior = true AND status = 'new';

CREATE OR REPLACE VIEW pipeline_view AS
SELECT status, COUNT(*) as count, ROUND(AVG(score_composite)) as avg_composite
FROM jobs
WHERE discovered_at > now() - INTERVAL '30 days'
GROUP BY status
ORDER BY count DESC;

COMMIT;
