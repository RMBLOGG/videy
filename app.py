from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import cloudinary
import cloudinary.uploader
import cloudinary.api
from supabase import create_client, Client
import os
from functools import wraps
from datetime import datetime
import uuid

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "your-secret-key-change-in-production")

# Cloudinary config
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET")
)

# Supabase config
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# Admin credentials (store securely in env vars)
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# ─── PUBLIC ROUTES ───────────────────────────────────────────────

@app.route('/')
def index():
    try:
        response = supabase.table('videos').select('*').order('created_at', desc=True).execute()
        videos = response.data
    except Exception as e:
        videos = []
    return render_template('index.html', videos=videos)

@app.route('/v/<video_id>')
def watch(video_id):
    try:
        response = supabase.table('videos').select('*').eq('id', video_id).single().execute()
        video = response.data
        if not video:
            return render_template('404.html'), 404
        # Get related videos
        related = supabase.table('videos').select('*').neq('id', video_id).limit(6).execute()
        return render_template('watch.html', video=video, related=related.data)
    except Exception as e:
        return render_template('404.html'), 404

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    videos = []
    if query:
        try:
            response = supabase.table('videos').select('*').ilike('title', f'%{query}%').execute()
            videos = response.data
        except Exception as e:
            videos = []
    return render_template('search.html', videos=videos, query=query)

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
        response = supabase.table('videos').select('*').order('created_at', desc=True).execute()
        videos = response.data
        total = len(videos)
    except:
        videos = []
        total = 0
    return render_template('admin/dashboard.html', videos=videos, total=total)

@app.route('/admin/upload', methods=['GET', 'POST'])
@login_required
def admin_upload():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        video_file = request.files.get('video')
        thumbnail_file = request.files.get('thumbnail')

        if not title or not video_file:
            flash('Judul dan file video wajib diisi.', 'error')
            return redirect(url_for('admin_upload'))

        try:
            # Upload video ke Cloudinary
            video_upload = cloudinary.uploader.upload(
                video_file,
                resource_type='video',
                folder='videy/videos',
                chunk_size=6000000
            )
            video_url = video_upload['secure_url']
            video_public_id = video_upload['public_id']
            duration = video_upload.get('duration', 0)

            # Upload thumbnail (opsional)
            thumbnail_url = None
            if thumbnail_file and thumbnail_file.filename:
                thumb_upload = cloudinary.uploader.upload(
                    thumbnail_file,
                    folder='videy/thumbnails'
                )
                thumbnail_url = thumb_upload['secure_url']
            else:
                # Auto-generate thumbnail dari video
                thumbnail_url = cloudinary.CloudinaryVideo(video_public_id).build_url(
                    resource_type='video',
                    format='jpg',
                    transformation=[{'start_offset': '0'}]
                )

            # Simpan ke Supabase
            video_id = str(uuid.uuid4())[:8]
            supabase.table('videos').insert({
                'id': video_id,
                'title': title,
                'description': description,
                'video_url': video_url,
                'thumbnail_url': thumbnail_url,
                'cloudinary_public_id': video_public_id,
                'duration': int(duration),
                'views': 0,
                'created_at': datetime.utcnow().isoformat()
            }).execute()

            flash(f'Video "{title}" berhasil diupload!', 'success')
            return redirect(url_for('admin_dashboard'))

        except Exception as e:
            flash(f'Error upload: {str(e)}', 'error')
            return redirect(url_for('admin_upload'))

    return render_template('admin/upload.html')

@app.route('/admin/delete/<video_id>', methods=['POST'])
@login_required
def admin_delete(video_id):
    try:
        # Ambil data video
        response = supabase.table('videos').select('*').eq('id', video_id).single().execute()
        video = response.data

        if video:
            # Hapus dari Cloudinary
            cloudinary.uploader.destroy(video['cloudinary_public_id'], resource_type='video')
            # Hapus dari Supabase
            supabase.table('videos').delete().eq('id', video_id).execute()
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
        response = supabase.table('videos').select('*').eq('id', video_id).single().execute()
        video = response.data
    except:
        flash('Video tidak ditemukan.', 'error')
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        try:
            supabase.table('videos').update({
                'title': title,
                'description': description
            }).eq('id', video_id).execute()
            flash('Video berhasil diperbarui.', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')

    return render_template('admin/edit.html', video=video)

# Increment views
@app.route('/api/view/<video_id>', methods=['POST'])
def increment_view(video_id):
    try:
        response = supabase.table('videos').select('views').eq('id', video_id).single().execute()
        current_views = response.data['views'] or 0
        supabase.table('videos').update({'views': current_views + 1}).eq('id', video_id).execute()
        return jsonify({'success': True})
    except:
        return jsonify({'success': False}), 400

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(debug=True)
