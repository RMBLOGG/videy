-- Jalankan SQL ini di Supabase SQL Editor
-- Dashboard Supabase → SQL Editor → New Query → Paste & Run

CREATE TABLE IF NOT EXISTS videos (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT,
    video_url   TEXT NOT NULL,
    thumbnail_url TEXT,
    cloudinary_public_id TEXT NOT NULL,
    duration    INTEGER DEFAULT 0,
    views       INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Enable Row Level Security (opsional tapi disarankan)
ALTER TABLE videos ENABLE ROW LEVEL SECURITY;

-- Policy: semua orang bisa baca (public read)
CREATE POLICY "Public read" ON videos
    FOR SELECT USING (true);

-- Policy: hanya service_role yang bisa insert/update/delete
-- (karena kita pakai anon key di server, nonaktifkan ini jika ingin fleksibel)
CREATE POLICY "Allow all for anon" ON videos
    FOR ALL USING (true);
