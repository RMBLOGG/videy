from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import cloudinary
import cloudinary.uploader
import cloudinary.api
from supabase import create_client, Client
import os
from functools import wraps
from datetime import datetime, timezone, timedelta
import uuid

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "default-secret-key")

# Cloudinary config — hardcoded
cloudinary.config(
    cloud_name="dzfkklsza",
    api_key="588474134734416",
    api_secret="9c12YJe5rZSYSg7zROQuvmVZ7mg"
)

# Supabase config — hardcoded, lazy init
_SUPABASE_URL = "https://mafnnqttvkdgqqxczqyt.supabase.co"
_SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1hZm5ucXR0dmtkZ3FxeGN6cXl0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE4NzQyMDEsImV4cCI6MjA4NzQ1MDIwMX0.YRh1oWVKnn4tyQNRbcPhlSyvr7V_1LseWN7VjcImb-Y"

_supabase_client = None

WIB = timezone(timedelta(hours=7))

def now_wib():
    """Return current datetime in WIB (UTC+7) as ISO string."""
    return datetime.now(WIB).isoformat()

def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
    return _supabase_client

# Admin credentials — set via Vercel env vars
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def format_wib(iso_string):
    """Format ISO datetime string to WIB display string."""
    if not iso_string:
        return '-'
    try:
        # Parse ISO string, handle both with/without timezone
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            # Assume UTC if no timezone
            dt = dt.replace(tzinfo=timezone.utc)
        dt_wib = dt.astimezone(WIB)
        return dt_wib.strftime('%d %b %Y, %H:%M WIB')
    except Exception:
        return iso_string[:10] if iso_string else '-'

# Make format_wib available in all templates
app.jinja_env.globals['format_wib'] = format_wib

# ─── PUBLIC ROUTES ───────────────────────────────────────────────

@app.route('/')
def index():
    try:
        response = get_supabase().table('videos').select('*').order('created_at', desc=True).execute()
        videos = response.data
    except Exception:
        videos = []
    return render_template('index.html', videos=videos)

@app.route('/v/<video_id>')
def watch(video_id):
    try:
        response = get_supabase().table('videos').select('*').eq('id', video_id).single().execute()
        video = response.data
        if not video:
            return render_template('404.html'), 404
        related = get_supabase().table('videos').select('*').neq('id', video_id).limit(6).execute()
        return render_template('watch.html', video=video, related=related.data)
    except Exception:
        return render_template('404.html'), 404

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    videos = []
    if query:
        try:
            response = get_supabase().table('videos').select('*').ilike('title', f'%{query}%').execute()
            videos = response.data
        except Exception:
            videos = []
    return render_template('search.html', videos=videos, query=query)

# ─── PUBLIC UPLOAD (tanpa login) ─────────────────────────────────

@app.route('/upload')
def public_upload():
    return render_template('upload.html')

# API endpoint — menerima data video setelah upload langsung ke Cloudinary dari browser
@app.route('/api/save-video', methods=['POST'])
def save_video():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data received'}), 400

        title = data.get('title', '').strip()
        if not title:
            return jsonify({'success': False, 'error': 'Judul wajib diisi'}), 400

        video_id = str(uuid.uuid4())[:8]
        get_supabase().table('videos').insert({
            'id': video_id,
            'title': title,
            'description': data.get('description', ''),
            'uploader_name': data.get('uploader_name', 'Anonymous'),
            'video_url': data.get('video_url', ''),
            'thumbnail_url': data.get('thumbnail_url', ''),
            'cloudinary_public_id': data.get('cloudinary_public_id', ''),
            'duration': int(data.get('duration', 0)),
            'views': 0,
            'created_at': now_wib()
        }).execute()

        return jsonify({'success': True, 'video_id': video_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ─── ADMIN ROUTES ─────────────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('logged_in'):
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['admin'] = username
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Username atau password salah.', 'error')
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin_dashboard():
    try:
        response = get_supabase().table('videos').select('*').order('created_at', desc=True).execute()
        videos = response.data
        total = len(videos)
    except Exception:
        videos = []
        total = 0
    return render_template('admin/dashboard.html', videos=videos, total=total)

@app.route('/admin/upload')
@login_required
def admin_upload():
    return render_template('admin/upload.html')

@app.route('/admin/delete/<video_id>', methods=['POST'])
@login_required
def admin_delete(video_id):
    try:
        response = get_supabase().table('videos').select('*').eq('id', video_id).single().execute()
        video = response.data
        if video:
            cloudinary.uploader.destroy(video['cloudinary_public_id'], resource_type='video')
            get_supabase().table('videos').delete().eq('id', video_id).execute()
            flash('Video berhasil dihapus.', 'success')
        else:
            flash('Video tidak ditemukan.', 'error')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit/<video_id>', methods=['GET', 'POST'])
@login_required
def admin_edit(video_id):
    try:
        response = get_supabase().table('videos').select('*').eq('id', video_id).single().execute()
        video = response.data
    except Exception:
        flash('Video tidak ditemukan.', 'error')
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        try:
            get_supabase().table('videos').update({
                'title': title,
                'description': description
            }).eq('id', video_id).execute()
            flash('Video berhasil diperbarui.', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')

    return render_template('admin/edit.html', video=video)

@app.route('/api/view/<video_id>', methods=['POST'])
def increment_view(video_id):
    try:
        response = get_supabase().table('videos').select('views').eq('id', video_id).single().execute()
        current_views = response.data['views'] or 0
        get_supabase().table('videos').update({'views': current_views + 1}).eq('id', video_id).execute()
        return jsonify({'success': True})
    except Exception:
        return jsonify({'success': False}), 400

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(debug=True)
