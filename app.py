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

cloudinary.config(
    cloud_name="dzfkklsza",
    api_key="588474134734416",
    api_secret="9c12YJe5rZSYSg7zROQuvmVZ7mg"
)

_SUPABASE_URL = "https://mafnnqttvkdgqqxczqyt.supabase.co"
_SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1hZm5ucXR0dmtkZ3FxeGN6cXl0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE4NzQyMDEsImV4cCI6MjA4NzQ1MDIwMX0.YRh1oWVKnn4tyQNRbcPhlSyvr7V_1LseWN7VjcImb-Y"

_supabase_client = None
WIB = timezone(timedelta(hours=7))
CATEGORIES = ['umum','hiburan','musik','olahraga','gaming','edukasi','berita','kuliner','travel','lainnya']
UPLOAD_LIMIT_PER_HOUR = 5

def now_wib():
    return datetime.now(WIB).isoformat()

def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
    return _supabase_client

def format_wib(iso_string):
    if not iso_string: return '-'
    try:
        dt = datetime.fromisoformat(str(iso_string).replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(WIB).strftime('%d %b %Y, %H:%M WIB')
    except:
        return str(iso_string)[:10]

def get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()

app.jinja_env.globals['format_wib'] = format_wib
app.jinja_env.globals['categories'] = CATEGORIES

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

# ── HELPERS ──────────────────────────────────────────────────────

def normalize_video(v):
    """Ensure all expected fields exist with defaults — prevents template crashes."""
    if not v:
        return v
    v.setdefault('status', 'approved')
    v.setdefault('is_featured', False)
    v.setdefault('is_trending', False)
    v.setdefault('category', 'umum')
    v.setdefault('tags', '')
    v.setdefault('likes', 0)
    v.setdefault('dislikes', 0)
    v.setdefault('views', 0)
    v.setdefault('uploader_name', 'Anonymous')
    v.setdefault('description', '')
    v.setdefault('uploader_ip', '')
    return v

def normalize_videos(lst):
    return [normalize_video(v) for v in (lst or [])]

def check_blacklist(title):
    """Returns matched keyword or None."""
    try:
        bl = get_supabase().table('blacklist').select('keyword').execute().data
        title_lower = title.lower()
        for row in bl:
            if row['keyword'].lower() in title_lower:
                return row['keyword']
    except:
        pass
    return None

def check_rate_limit(ip):
    """Returns True if allowed, False if rate limited."""
    try:
        one_hour_ago = (datetime.now(WIB) - timedelta(hours=1)).isoformat()
        result = get_supabase().table('upload_log').select('id').eq('ip', ip).gte('created_at', one_hour_ago).execute()
        return len(result.data) < UPLOAD_LIMIT_PER_HOUR
    except:
        return True

def log_upload(ip):
    try:
        get_supabase().table('upload_log').insert({'ip': ip, 'created_at': now_wib()}).execute()
    except:
        pass

# ── PUBLIC ROUTES ────────────────────────────────────────────────

@app.route('/')
def index():
    sort = request.args.get('sort', 'terbaru')
    cat  = request.args.get('cat', '')
    videos = []
    featured = []
    try:
        # Fetch all, normalize, then filter in Python (safe if new columns don't exist yet)
        if sort == 'populer':
            raw = get_supabase().table('videos').select('*').order('views', desc=True).execute().data
        else:
            raw = get_supabase().table('videos').select('*').order('created_at', desc=True).execute().data

        all_videos = normalize_videos(raw)

        # Filter approved (works even if status col missing — normalize defaults to 'approved')
        approved = [v for v in all_videos if v.get('status', 'approved') in ('approved', None, '')]

        if cat:
            approved = [v for v in approved if v.get('category', 'umum') == cat]

        if sort == 'trending':
            videos = [v for v in approved if v.get('is_trending', False)]
        else:
            videos = approved

        featured = [v for v in all_videos if v.get('is_featured', False) and v.get('status', 'approved') in ('approved', None, '')]
    except Exception as e:
        videos = []
        featured = []
    return render_template('index.html', videos=videos, featured=featured, sort=sort, cat=cat)

@app.route('/v/<video_id>')
def watch(video_id):
    try:
        raw = get_supabase().table('videos').select('*').eq('id', video_id).execute().data
        if not raw:
            return render_template('404.html'), 404
        video = normalize_video(raw[0])
        status = video.get('status', 'approved')
        if status not in ('approved', None, ''):
            return render_template('404.html'), 404

        # Related videos
        try:
            cat = video.get('category', 'umum')
            rel_raw = get_supabase().table('videos').select('*').neq('id', video_id).order('views', desc=True).limit(12).execute().data
            all_rel = normalize_videos(rel_raw)
            approved_rel = [v for v in all_rel if v.get('status','approved') in ('approved', None, '')]
            # Prefer same category first
            same_cat = [v for v in approved_rel if v.get('category','umum') == cat]
            other = [v for v in approved_rel if v.get('category','umum') != cat]
            related = (same_cat + other)[:8]
        except:
            related = []

        # Comments
        comments = []
        try:
            comments = get_supabase().table('comments').select('*').eq('video_id', video_id).order('created_at', desc=True).execute().data
        except:
            pass

        # User reaction
        ip = get_client_ip()
        user_reaction = None
        try:
            rx = get_supabase().table('reactions').select('type').eq('video_id', video_id).eq('ip', ip).execute().data
            if rx: user_reaction = rx[0]['type']
        except:
            pass

        return render_template('watch.html', video=video, related=related, comments=comments, user_reaction=user_reaction)
    except Exception as e:
        return render_template('404.html'), 404

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    cat   = request.args.get('cat', '')
    videos = []
    if query:
        try:
            raw = get_supabase().table('videos').select('*').ilike('title', f'%{query}%').execute().data
            videos = normalize_videos(raw)
            videos = [v for v in videos if v.get('status','approved') in ('approved',None,'')]
            if cat:
                videos = [v for v in videos if v.get('category','umum') == cat]
        except:
            pass
    return render_template('search.html', videos=videos, query=query, cat=cat)

@app.route('/category/<cat>')
def category(cat):
    try:
        raw = get_supabase().table('videos').select('*').order('created_at', desc=True).execute().data
        all_v = normalize_videos(raw)
        videos = [v for v in all_v if v.get('status','approved') in ('approved',None,'') and v.get('category','umum') == cat]
    except:
        videos = []
    return render_template('category.html', videos=videos, cat=cat)

@app.route('/uploader/<n>')
def uploader_profile(n):
    try:
        raw = get_supabase().table('videos').select('*').eq('uploader_name', n).order('created_at', desc=True).execute().data
        videos = normalize_videos(raw)
        videos = [v for v in videos if v.get('status','approved') in ('approved',None,'')]
        total_views = sum(v.get('views', 0) for v in videos)
    except:
        videos = []
        total_views = 0
    return render_template('uploader.html', videos=videos, name=n, total_views=total_views)

@app.route('/upload')
def public_upload():
    return render_template('upload.html')

# ── PUBLIC APIs ──────────────────────────────────────────────────

@app.route('/api/save-video', methods=['POST'])
def save_video():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data'}), 400

        title = data.get('title', '').strip()
        if not title:
            return jsonify({'success': False, 'error': 'Judul wajib diisi'}), 400

        ip = get_client_ip()

        # Rate limit check
        if not check_rate_limit(ip):
            return jsonify({'success': False, 'error': f'Terlalu banyak upload. Maksimal {UPLOAD_LIMIT_PER_HOUR}x per jam.'}), 429

        # Blacklist check
        matched = check_blacklist(title)
        if matched:
            return jsonify({'success': False, 'error': f'Judul mengandung kata terlarang: "{matched}"'}), 400

        video_id = str(uuid.uuid4())[:8]
        is_admin = data.get('is_admin', False)

        get_supabase().table('videos').insert({
            'id': video_id,
            'title': title,
            'description': data.get('description', ''),
            'uploader_name': data.get('uploader_name', 'Anonymous'),
            'uploader_ip': ip,
            'video_url': data.get('video_url', ''),
            'thumbnail_url': data.get('thumbnail_url', ''),
            'cloudinary_public_id': data.get('cloudinary_public_id', ''),
            'duration': int(data.get('duration', 0)),
            'category': data.get('category', 'umum'),
            'tags': data.get('tags', ''),
            'views': 0, 'likes': 0, 'dislikes': 0,
            'status': 'approved' if is_admin else 'pending',
            'is_featured': False, 'is_trending': False,
            'created_at': now_wib()
        }).execute()

        log_upload(ip)
        return jsonify({'success': True, 'video_id': video_id, 'status': 'approved' if is_admin else 'pending'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/view/<video_id>', methods=['POST'])
def increment_view(video_id):
    try:
        r = get_supabase().table('videos').select('views').eq('id', video_id).single().execute()
        get_supabase().table('videos').update({'views': (r.data['views'] or 0) + 1}).eq('id', video_id).execute()
        return jsonify({'success': True})
    except:
        return jsonify({'success': False}), 400

@app.route('/api/react/<video_id>', methods=['POST'])
def react(video_id):
    try:
        data = request.get_json()
        rtype = data.get('type')  # 'like' or 'dislike'
        ip = get_client_ip()
        if rtype not in ('like', 'dislike'):
            return jsonify({'success': False}), 400

        existing = get_supabase().table('reactions').select('*').eq('video_id', video_id).eq('ip', ip).execute().data
        video = get_supabase().table('videos').select('likes,dislikes').eq('id', video_id).single().execute().data
        likes = video['likes'] or 0
        dislikes = video['dislikes'] or 0

        if existing:
            old_type = existing[0]['type']
            if old_type == rtype:
                # Toggle off
                get_supabase().table('reactions').delete().eq('video_id', video_id).eq('ip', ip).execute()
                if rtype == 'like': likes = max(0, likes - 1)
                else: dislikes = max(0, dislikes - 1)
                user_reaction = None
            else:
                # Switch
                get_supabase().table('reactions').update({'type': rtype}).eq('video_id', video_id).eq('ip', ip).execute()
                if rtype == 'like': likes += 1; dislikes = max(0, dislikes - 1)
                else: dislikes += 1; likes = max(0, likes - 1)
                user_reaction = rtype
        else:
            get_supabase().table('reactions').insert({'video_id': video_id, 'ip': ip, 'type': rtype, 'created_at': now_wib()}).execute()
            if rtype == 'like': likes += 1
            else: dislikes += 1
            user_reaction = rtype

        get_supabase().table('videos').update({'likes': likes, 'dislikes': dislikes}).eq('id', video_id).execute()
        return jsonify({'success': True, 'likes': likes, 'dislikes': dislikes, 'user_reaction': user_reaction})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/comment/<video_id>', methods=['POST'])
def add_comment(video_id):
    try:
        data = request.get_json()
        name    = (data.get('name') or 'Anonymous').strip()[:50]
        content = (data.get('content') or '').strip()[:500]
        if not content:
            return jsonify({'success': False, 'error': 'Komentar kosong'}), 400

        matched = check_blacklist(content)
        if matched:
            return jsonify({'success': False, 'error': f'Komentar mengandung kata terlarang'}), 400

        get_supabase().table('comments').insert({
            'video_id': video_id, 'name': name,
            'content': content, 'created_at': now_wib()
        }).execute()
        return jsonify({'success': True, 'name': name, 'content': content, 'created_at': now_wib()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/report/<video_id>', methods=['POST'])
def report_video(video_id):
    try:
        data = request.get_json()
        reason = data.get('reason', '').strip()
        detail = data.get('detail', '').strip()[:300]
        if not reason:
            return jsonify({'success': False, 'error': 'Alasan wajib diisi'}), 400
        get_supabase().table('reports').insert({
            'video_id': video_id, 'reason': reason, 'detail': detail,
            'reporter_ip': get_client_ip(), 'reviewed': False, 'created_at': now_wib()
        }).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ── ADMIN ROUTES ─────────────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('logged_in'):
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USERNAME and request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin_dashboard'))
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
        raw = get_supabase().table('videos').select('*').order('created_at', desc=True).execute().data
        all_videos = normalize_videos(raw)
        pending    = [v for v in all_videos if v.get('status','approved') == 'pending']
        approved   = [v for v in all_videos if v.get('status','approved') in ('approved', None, '')]
        total_views = sum(v.get('views', 0) for v in approved)
        reports = []
        try:
            reports = get_supabase().table('reports').select('*').eq('reviewed', False).order('created_at', desc=True).execute().data
        except:
            pass
        comments_count = []
        try:
            comments_count = get_supabase().table('comments').select('id').execute().data
        except:
            pass
        stats = {
            'total': len(all_videos),
            'approved': len(approved),
            'pending': len(pending),
            'reports': len(reports),
            'views': total_views,
            'comments': len(comments_count)
        }
        top_videos = sorted(approved, key=lambda v: v.get('views', 0), reverse=True)[:5]
    except Exception as e:
        all_videos = pending = approved = reports = top_videos = []
        stats = {'total':0,'approved':0,'pending':0,'reports':0,'views':0,'comments':0}
    return render_template('admin/dashboard.html', all_videos=all_videos, pending=pending,
                           reports=reports, stats=stats, top_videos=top_videos)

@app.route('/admin/videos')
@login_required
def admin_videos():
    status_filter = request.args.get('status', 'all')
    try:
        raw = get_supabase().table('videos').select('*').order('created_at', desc=True).execute().data
        videos = normalize_videos(raw)
        if status_filter != 'all':
            if status_filter == 'approved':
                videos = [v for v in videos if v.get('status','approved') in ('approved', None, '')]
            else:
                videos = [v for v in videos if v.get('status','approved') == status_filter]
    except:
        videos = []
    return render_template('admin/videos.html', videos=videos, status_filter=status_filter)

@app.route('/admin/upload')
@login_required
def admin_upload():
    return render_template('admin/upload.html')

@app.route('/admin/moderate/<video_id>/<action>', methods=['POST'])
@login_required
def moderate(video_id, action):
    if action in ('approve', 'reject'):
        status = 'approved' if action == 'approve' else 'rejected'
        get_supabase().table('videos').update({'status': status}).eq('id', video_id).execute()
        flash(f'Video {"disetujui" if action == "approve" else "ditolak"}.', 'success')
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/admin/feature/<video_id>/<action>', methods=['POST'])
@login_required
def feature_video(video_id, action):
    field = 'is_featured' if 'featured' in action else 'is_trending'
    val   = action in ('set_featured', 'set_trending')
    get_supabase().table('videos').update({field: val}).eq('id', video_id).execute()
    return redirect(request.referrer or url_for('admin_videos'))

@app.route('/admin/delete/<video_id>', methods=['POST'])
@login_required
def admin_delete(video_id):
    try:
        video = get_supabase().table('videos').select('*').eq('id', video_id).single().execute().data
        if video:
            try: cloudinary.uploader.destroy(video['cloudinary_public_id'], resource_type='video')
            except: pass
            get_supabase().table('videos').delete().eq('id', video_id).execute()
            flash('Video berhasil dihapus.', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    return redirect(request.referrer or url_for('admin_videos'))

@app.route('/admin/bulk-delete', methods=['POST'])
@login_required
def bulk_delete():
    ids = request.form.getlist('video_ids')
    deleted = 0
    for vid in ids:
        try:
            video = get_supabase().table('videos').select('cloudinary_public_id').eq('id', vid).single().execute().data
            if video:
                try: cloudinary.uploader.destroy(video['cloudinary_public_id'], resource_type='video')
                except: pass
                get_supabase().table('videos').delete().eq('id', vid).execute()
                deleted += 1
        except: pass
    flash(f'{deleted} video berhasil dihapus.', 'success')
    return redirect(url_for('admin_videos'))

@app.route('/admin/edit/<video_id>', methods=['GET', 'POST'])
@login_required
def admin_edit(video_id):
    try:
        video = get_supabase().table('videos').select('*').eq('id', video_id).single().execute().data
    except:
        flash('Video tidak ditemukan.', 'error')
        return redirect(url_for('admin_videos'))
    if request.method == 'POST':
        try:
            get_supabase().table('videos').update({
                'title': request.form.get('title','').strip(),
                'description': request.form.get('description','').strip(),
                'category': request.form.get('category','umum'),
                'tags': request.form.get('tags','').strip(),
                'status': request.form.get('status','pending'),
                'is_featured': 'is_featured' in request.form,
                'is_trending': 'is_trending' in request.form,
            }).eq('id', video_id).execute()
            flash('Video diperbarui.', 'success')
            return redirect(url_for('admin_videos'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
    return render_template('admin/edit.html', video=video)

@app.route('/admin/reports')
@login_required
def admin_reports():
    try:
        reports = get_supabase().table('reports').select('*').order('created_at', desc=True).execute().data
        # Attach video titles
        for r in reports:
            try:
                v = get_supabase().table('videos').select('title').eq('id', r['video_id']).single().execute().data
                r['video_title'] = v['title'] if v else '(dihapus)'
            except:
                r['video_title'] = '(tidak ditemukan)'
    except:
        reports = []
    return render_template('admin/reports.html', reports=reports)

@app.route('/admin/reports/resolve/<int:report_id>', methods=['POST'])
@login_required
def resolve_report(report_id):
    get_supabase().table('reports').update({'reviewed': True}).eq('id', report_id).execute()
    return redirect(url_for('admin_reports'))

@app.route('/admin/blacklist', methods=['GET', 'POST'])
@login_required
def admin_blacklist():
    if request.method == 'POST':
        keyword = request.form.get('keyword', '').strip().lower()
        if keyword:
            try:
                get_supabase().table('blacklist').insert({'keyword': keyword}).execute()
                flash(f'Kata "{keyword}" ditambahkan ke blacklist.', 'success')
            except:
                flash('Kata sudah ada di blacklist.', 'error')
    try:
        keywords = get_supabase().table('blacklist').select('*').order('id', desc=True).execute().data
    except:
        keywords = []
    return render_template('admin/blacklist.html', keywords=keywords)

@app.route('/admin/blacklist/delete/<int:kw_id>', methods=['POST'])
@login_required
def delete_blacklist(kw_id):
    get_supabase().table('blacklist').delete().eq('id', kw_id).execute()
    flash('Kata dihapus dari blacklist.', 'success')
    return redirect(url_for('admin_blacklist'))

@app.route('/admin/comments')
@login_required
def admin_comments():
    try:
        comments = get_supabase().table('comments').select('*').order('created_at', desc=True).limit(200).execute().data
        for c in comments:
            try:
                v = get_supabase().table('videos').select('title').eq('id', c['video_id']).single().execute().data
                c['video_title'] = v['title'] if v else '(dihapus)'
            except:
                c['video_title'] = '-'
    except:
        comments = []
    return render_template('admin/comments.html', comments=comments)

@app.route('/admin/comments/delete/<int:comment_id>', methods=['POST'])
@login_required
def delete_comment(comment_id):
    get_supabase().table('comments').delete().eq('id', comment_id).execute()
    return redirect(url_for('admin_comments'))

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(debug=True)

@app.route('/embed/<video_id>')
def embed(video_id):
    try:
        video = get_supabase().table('videos').select('*').eq('id', video_id).eq('status','approved').single().execute().data
        if not video: return "Video not found", 404
        return render_template('embed.html', video=video)
    except:
        return "Video not found", 404
