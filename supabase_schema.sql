-- ============================================================
-- VIDEY — Full Schema
-- Jalankan di Supabase SQL Editor
-- ============================================================

-- VIDEOS
CREATE TABLE IF NOT EXISTS videos (
    id                   TEXT PRIMARY KEY,
    title                TEXT NOT NULL,
    description          TEXT,
    uploader_name        TEXT DEFAULT 'Anonymous',
    uploader_ip          TEXT,
    video_url            TEXT NOT NULL,
    thumbnail_url        TEXT,
    cloudinary_public_id TEXT NOT NULL,
    duration             INTEGER DEFAULT 0,
    views                INTEGER DEFAULT 0,
    likes                INTEGER DEFAULT 0,
    dislikes             INTEGER DEFAULT 0,
    status               TEXT DEFAULT 'pending', -- pending | approved | rejected
    is_featured          BOOLEAN DEFAULT false,
    is_trending          BOOLEAN DEFAULT false,
    category             TEXT DEFAULT 'umum',
    tags                 TEXT DEFAULT '',
    created_at           TIMESTAMPTZ DEFAULT now()
);

-- COMMENTS
CREATE TABLE IF NOT EXISTS comments (
    id         SERIAL PRIMARY KEY,
    video_id   TEXT REFERENCES videos(id) ON DELETE CASCADE,
    name       TEXT DEFAULT 'Anonymous',
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- REPORTS
CREATE TABLE IF NOT EXISTS reports (
    id         SERIAL PRIMARY KEY,
    video_id   TEXT REFERENCES videos(id) ON DELETE CASCADE,
    reason     TEXT NOT NULL,
    detail     TEXT,
    reporter_ip TEXT,
    reviewed   BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- REACTIONS (likes/dislikes per IP)
CREATE TABLE IF NOT EXISTS reactions (
    id         SERIAL PRIMARY KEY,
    video_id   TEXT REFERENCES videos(id) ON DELETE CASCADE,
    ip         TEXT NOT NULL,
    type       TEXT NOT NULL, -- 'like' | 'dislike'
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(video_id, ip)
);

-- BLACKLIST KEYWORDS
CREATE TABLE IF NOT EXISTS blacklist (
    id      SERIAL PRIMARY KEY,
    keyword TEXT NOT NULL UNIQUE
);

-- UPLOAD RATE LIMIT (per IP)
CREATE TABLE IF NOT EXISTS upload_log (
    id         SERIAL PRIMARY KEY,
    ip         TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Add missing columns if upgrading existing db
ALTER TABLE videos ADD COLUMN IF NOT EXISTS likes INTEGER DEFAULT 0;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS dislikes INTEGER DEFAULT 0;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';
ALTER TABLE videos ADD COLUMN IF NOT EXISTS is_featured BOOLEAN DEFAULT false;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS is_trending BOOLEAN DEFAULT false;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'umum';
ALTER TABLE videos ADD COLUMN IF NOT EXISTS tags TEXT DEFAULT '';
ALTER TABLE videos ADD COLUMN IF NOT EXISTS uploader_ip TEXT;

-- RLS
ALTER TABLE videos    ENABLE ROW LEVEL SECURITY;
ALTER TABLE comments  ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports   ENABLE ROW LEVEL SECURITY;
ALTER TABLE reactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE blacklist ENABLE ROW LEVEL SECURITY;
ALTER TABLE upload_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public_read_videos"    ON videos    FOR SELECT USING (true);
CREATE POLICY "public_all_videos"     ON videos    FOR ALL    USING (true);
CREATE POLICY "public_all_comments"   ON comments  FOR ALL    USING (true);
CREATE POLICY "public_all_reports"    ON reports   FOR ALL    USING (true);
CREATE POLICY "public_all_reactions"  ON reactions FOR ALL    USING (true);
CREATE POLICY "public_all_blacklist"  ON blacklist FOR ALL    USING (true);
CREATE POLICY "public_all_uploadlog"  ON upload_log FOR ALL   USING (true);
