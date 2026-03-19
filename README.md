# VIDEY Clone — Flask Video Sharing Platform

Platform streaming video sederhana mirip Videy, dengan admin upload, Supabase database, dan Cloudinary storage.

---

## 🗂 Struktur File

```
videy-clone/
├── app.py                  # Flask app utama
├── requirements.txt        # Python dependencies
├── vercel.json             # Konfigurasi Vercel
├── supabase_schema.sql     # SQL schema untuk Supabase
├── .env.example            # Contoh environment variables
└── templates/
    ├── base.html           # Template dasar (navbar, footer)
    ├── index.html          # Halaman beranda
    ├── watch.html          # Halaman putar video
    ├── search.html         # Halaman pencarian
    ├── 404.html            # Halaman 404
    └── admin/
        ├── login.html      # Login admin
        ├── dashboard.html  # Dashboard admin
        ├── upload.html     # Upload video
        └── edit.html       # Edit video
```

---

## ⚙️ Setup Supabase

1. Buka [supabase.com](https://supabase.com) → project kamu
2. Pergi ke **SQL Editor** → **New Query**
3. Copy isi `supabase_schema.sql` → paste → **Run**
4. Tabel `videos` akan terbuat otomatis

---

## 🚀 Deploy ke Vercel

### 1. Push ke GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/USERNAME/videy-clone.git
git push -u origin main
```

### 2. Import ke Vercel
- Buka [vercel.com](https://vercel.com) → **Add New Project**
- Import repo GitHub kamu
- Pilih **Python** sebagai framework (otomatis terdeteksi via `vercel.json`)

### 3. Set Environment Variables di Vercel
Masuk ke **Project Settings → Environment Variables**, tambahkan:

| Key | Value |
|-----|-------|
| `SECRET_KEY` | string random panjang |
| `ADMIN_USERNAME` | username admin |
| `ADMIN_PASSWORD` | password admin |
| `CLOUDINARY_CLOUD_NAME` | dzfkklsza |
| `CLOUDINARY_API_KEY` | 588474134734416 |
| `CLOUDINARY_API_SECRET` | 9c12YJe5rZSYSg7zROQuvmVZ7mg |
| `SUPABASE_URL` | https://mafnnqttvkdgqqxczqyt.supabase.co |
| `SUPABASE_ANON_KEY` | (anon key dari Supabase) |

4. Klik **Deploy** → selesai! 🎉

---

## 🔑 Akses Admin

- URL: `https://domain-kamu.vercel.app/admin/login`
- Login dengan username & password yang kamu set di env vars

---

## ✨ Fitur

- 🎬 Streaming video dari Cloudinary
- 🔐 Admin-only upload (login required)
- 📊 View counter per video
- 🔍 Pencarian video
- 🖼 Auto-generate thumbnail dari video
- 📱 Responsive design
- 🗑 Hapus video (otomatis hapus dari Cloudinary & Supabase)
- ✏️ Edit judul & deskripsi
- 🔗 Share URL per video

---

## ⚠️ Catatan Penting

- Vercel punya **batas upload 4.5MB** untuk request body di Serverless Functions.
- Untuk video besar, pertimbangkan **upload langsung ke Cloudinary dari browser** menggunakan Cloudinary Upload Widget (unsigned upload).
- Jangan commit file `.env` ke Git!
