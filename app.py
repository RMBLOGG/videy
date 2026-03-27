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
app.jinja_env.globals['_is_noads_user'] = lambda: _is_noads(session.get('user_id')) if session.get('user_id') else False

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
    folders_data = []
    try:
        if sort == 'populer':
            raw = get_supabase().table('videos').select('*').order('views', desc=True).execute().data
        else:
            raw = get_supabase().table('videos').select('*').order('created_at', desc=True).execute().data

        all_videos = normalize_videos(raw)
        approved = [v for v in all_videos if v.get('status', 'approved') in ('approved', None, '')]

        if cat:
            approved = [v for v in approved if v.get('category', 'umum') == cat]

        if sort == 'trending':
            videos = [v for v in approved if v.get('is_trending', False)]
        else:
            videos = approved

        featured = [v for v in all_videos if v.get('is_featured', False) and v.get('status', 'approved') in ('approved', None, '')]

        # Load folders (hanya info, tanpa video — detail ada di halaman masing-masing)
        if not cat:
            folders_raw = get_supabase().table('folders').select('*').order('created_at', desc=True).execute().data or []
            for f in folders_raw:
                count = get_supabase().table('folder_videos').select('id', count='exact').eq('folder_id', f['id']).execute()
                f['video_count'] = count.count or 0
            folders_data = [f for f in folders_raw if f['video_count'] > 0]
    except Exception as e:
        videos = []
        featured = []
        folders_data = []
    return render_template('index.html', videos=videos, featured=featured, sort=sort, cat=cat, folders=folders_data)

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

        return render_template('watch.html', video=video, related=related, comments=comments, user_reaction=user_reaction,
                               is_premium=_is_premium(session.get('user_id')),
                               perks=_get_user_perks(session.get('user_id')))
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
        is_admin = session.get('logged_in', False)

        # Rate limit check — skip untuk admin
        if not is_admin and not check_rate_limit(ip):
            return jsonify({'success': False, 'error': f'Terlalu banyak upload. Maksimal {UPLOAD_LIMIT_PER_HOUR}x per jam.'}), 429

        # Blacklist check
        matched = check_blacklist(title)
        if matched:
            return jsonify({'success': False, 'error': f'Judul mengandung kata terlarang: "{matched}"'}), 400

        video_id = str(uuid.uuid4())[:8]

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

@app.route('/embed/<video_id>')
def embed(video_id):
    try:
        video = get_supabase().table('videos').select('*').eq('id', video_id).eq('status','approved').single().execute().data
        if not video: return "Video not found", 404
        return render_template('embed.html', video=video)
    except:
        return "Video not found", 404

# ── FOLDER ROUTES ──────────────────────────────────────────────

@app.route('/folder/<int:folder_id>')
def folder_detail(folder_id):
    try:
        folder = get_supabase().table('folders').select('*').eq('id', folder_id).single().execute().data
        if not folder:
            return render_template('404.html'), 404
        fv = get_supabase().table('folder_videos').select('video_id').eq('folder_id', folder_id).execute().data or []
        video_ids = [r['video_id'] for r in fv]
        videos = []
        if video_ids:
            raw = get_supabase().table('videos').select('*').in_('id', video_ids).execute().data or []
            videos = normalize_videos(raw)
            videos = [v for v in videos if v.get('status','approved') in ('approved', None, '')]
        return render_template('folder.html', folder=folder, videos=videos)
    except Exception as e:
        return render_template('404.html'), 404

@app.route('/admin/folders')
@login_required
def admin_folders():
    try:
        folders = get_supabase().table('folders').select('*').order('created_at', desc=True).execute().data or []
        # Hitung jumlah video per folder
        for f in folders:
            count = get_supabase().table('folder_videos').select('id', count='exact').eq('folder_id', f['id']).execute()
            f['video_count'] = count.count or 0
        all_videos = get_supabase().table('videos').select('id,title,thumbnail_url').eq('status','approved').order('created_at', desc=True).execute().data or []
        return render_template('admin/folders.html', folders=folders, all_videos=all_videos)
    except Exception as e:
        flash(f'Error: {e}', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/folders/create', methods=['POST'])
@login_required
def admin_folder_create():
    try:
        name = request.form.get('name', '').strip()
        desc = request.form.get('description', '').strip()
        if not name:
            flash('Nama folder wajib diisi', 'error')
            return redirect(url_for('admin_folders'))
        result = get_supabase().table('folders').insert({'name': name, 'description': desc}).execute()
        flash(f'Folder "{name}" berhasil dibuat', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('admin_folders'))

@app.route('/admin/folders/delete/<int:folder_id>', methods=['POST'])
@login_required
def admin_folder_delete(folder_id):
    try:
        get_supabase().table('folders').delete().eq('id', folder_id).execute()
        flash('Folder dihapus', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('admin_folders'))

@app.route('/admin/folders/<int:folder_id>/videos', methods=['POST'])
@login_required
def admin_folder_set_videos(folder_id):
    try:
        # Hapus semua video lama di folder ini
        get_supabase().table('folder_videos').delete().eq('folder_id', folder_id).execute()
        # Tambah video yang dipilih
        video_ids = request.form.getlist('video_ids')
        if video_ids:
            rows = [{'folder_id': folder_id, 'video_id': vid} for vid in video_ids]
            get_supabase().table('folder_videos').insert(rows).execute()
        flash('Isi folder berhasil diperbarui', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('admin_folders'))

@app.route('/admin/folders/<int:folder_id>/rename', methods=['POST'])
@login_required
def admin_folder_rename(folder_id):
    try:
        name = request.form.get('name', '').strip()
        desc = request.form.get('description', '').strip()
        if name:
            get_supabase().table('folders').update({'name': name, 'description': desc}).eq('id', folder_id).execute()
            flash('Folder diperbarui', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('admin_folders'))

# ── User Auth (Register / Login / Logout) — Manual Table ──────────────────────
import hashlib, re as _re

def _hash_password(pw):
    """SHA-256 hash password."""
    return hashlib.sha256(pw.encode()).hexdigest()

def _valid_email(email):
    return bool(_re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email))

def _valid_username(u):
    """Hanya huruf, angka, underscore, 3-20 karakter."""
    return bool(_re.match(r'^[a-zA-Z0-9_]{3,20}$', u))

@app.route('/daftar', methods=['GET', 'POST'])
def user_register():
    if session.get('user_id'):
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()

        # Validasi
        if not username or not email or not password:
            error = 'Semua field wajib diisi.'
        elif not _valid_username(username):
            error = 'Username hanya boleh huruf, angka, underscore (3–20 karakter).'
        elif not _valid_email(email):
            error = 'Format email tidak valid.'
        elif len(password) < 6:
            error = 'Password minimal 6 karakter.'
        else:
            sb = get_supabase()
            # Cek duplikat username
            cek_u = sb.table('users').select('id').eq('username', username).execute()
            if cek_u.data:
                error = 'Username sudah dipakai, coba yang lain.'
            else:
                # Cek duplikat email
                cek_e = sb.table('users').select('id').eq('email', email).execute()
                if cek_e.data:
                    error = 'Email sudah terdaftar, silakan login.'
                else:
                    # Simpan ke tabel users
                    try:
                        new_user = sb.table('users').insert({
                            'username': username,
                            'email':    email,
                            'password': _hash_password(password),
                        }).execute()
                        if new_user.data:
                            user = new_user.data[0]
                            session['user_id']       = user['id']
                            session['user_username'] = user['username']
                            session['user_email']    = user['email']
                            return redirect(url_for('index'))
                        else:
                            error = 'Gagal menyimpan akun, coba lagi.'
                    except Exception as e:
                        error = f'Error: {str(e)}'
    return render_template('auth/register.html', error=error)

@app.route('/masuk', methods=['GET', 'POST'])
def user_login():
    if session.get('user_id'):
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        login_field = request.form.get('login', '').strip().lower()
        password    = request.form.get('password', '').strip()

        if not login_field or not password:
            error = 'Semua field wajib diisi.'
        else:
            sb = get_supabase()
            # Cari berdasarkan email atau username
            if '@' in login_field:
                res = sb.table('users').select('*').eq('email', login_field).execute()
            else:
                res = sb.table('users').select('*').eq('username', login_field).execute()

            if not res.data:
                error = 'Akun tidak ditemukan.'
            else:
                user = res.data[0]
                if user['password'] != _hash_password(password):
                    error = 'Password salah.'
                else:
                    session['user_id']       = user['id']
                    session['user_username'] = user['username']
                    session['user_email']    = user['email']
                    return redirect(url_for('index'))
    return render_template('auth/login.html', error=error)

@app.route('/keluar')
def user_logout():
    session.pop('user_id', None)
    session.pop('user_username', None)
    session.pop('user_email', None)
    return redirect(url_for('index'))

# ── Voucher & Premium System (2 Paket) ────────────────────────────────────────
# Paket: "noads"    → no-ads selamanya (kolom noads_active = true)
#        "download" → download 30 hari (kolom download_expires_at)

def _get_user_perks(user_id):
    if not user_id:
        return {'noads': False, 'download': False, 'download_expires': None}
    try:
        res = get_supabase().table('user_premium') \
            .select('noads_active, download_expires_at') \
            .eq('user_id', user_id).execute()
        if not res.data:
            return {'noads': False, 'download': False, 'download_expires': None}
        d     = res.data[0]
        noads = bool(d.get('noads_active', False))
        exp   = d.get('download_expires_at')
        dl    = False
        if exp:
            exp_dt = datetime.fromisoformat(exp.replace('Z', '+00:00'))
            dl = exp_dt > datetime.now(timezone.utc)
        return {'noads': noads, 'download': dl, 'download_expires': exp[:10] if exp else None}
    except Exception:
        return {'noads': False, 'download': False, 'download_expires': None}

def _is_noads(user_id):
    return _get_user_perks(user_id)['noads']

def _is_premium(user_id):
    return _get_user_perks(user_id)['download']

# ── User: halaman premium ──────────────────────────────────────────────────────
@app.route('/premium')
def premium_page():
    user_id = session.get('user_id')
    perks   = _get_user_perks(user_id)
    return render_template('premium.html', perks=perks)

# ── User: redeem voucher ───────────────────────────────────────────────────────
@app.route('/premium/redeem', methods=['POST'])
def premium_redeem():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Login dulu untuk redeem voucher.'}), 401

    kode = request.form.get('kode', '').strip().upper()
    if not kode:
        return jsonify({'error': 'Kode voucher tidak boleh kosong.'}), 400

    try:
        sb  = get_supabase()
        now = datetime.now(timezone.utc)

        res = sb.table('vouchers').select('*').eq('kode', kode).execute()
        if not res.data:
            return jsonify({'error': 'Kode voucher tidak ditemukan.'}), 404
        v = res.data[0]
        if v.get('used'):
            return jsonify({'error': 'Kode voucher sudah pernah dipakai.'}), 400

        tipe   = v.get('tipe', 'download')
        durasi = v.get('durasi_hari', 30)

        cek = sb.table('user_premium').select('*').eq('user_id', user_id).execute()

        if tipe == 'noads':
            upsert_data  = {'noads_active': True}
            msg          = 'Berhasil! Iklan dimatikan selamanya.'
            result_extra = {}
        else:
            if cek.data:
                old_exp = cek.data[0].get('download_expires_at', '')
                try:
                    old_dt = datetime.fromisoformat(old_exp.replace('Z', '+00:00'))
                    base = old_dt if old_dt > now else now
                except Exception:
                    base = now
            else:
                base = now
            new_exp      = (base + timedelta(days=durasi)).isoformat()
            upsert_data  = {'download_expires_at': new_exp}
            msg          = f'Berhasil! Download aktif {durasi} hari.'
            result_extra = {'expires': new_exp[:10]}

        if cek.data:
            sb.table('user_premium').update(upsert_data).eq('user_id', user_id).execute()
        else:
            upsert_data['user_id'] = user_id
            sb.table('user_premium').insert(upsert_data).execute()

        sb.table('vouchers').update({
            'used': True, 'used_by': user_id, 'used_at': now.isoformat()
        }).eq('kode', kode).execute()

        return jsonify({'ok': True, 'message': msg, 'tipe': tipe, **result_extra})
    except Exception as e:
        return jsonify({'error': f'Debug: {str(e)}'}), 500

# ── Download terlindungi premium download ─────────────────────────────────────
@app.route('/download/<video_id>')
def download_video(video_id):
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('user_login') + '?next=' + request.path)
    if not _is_premium(user_id):
        return redirect(url_for('premium_page'))
    try:
        res = get_supabase().table('videos').select('video_url,title') \
            .eq('id', video_id).single().execute()
        if not res.data:
            return 'Video tidak ditemukan.', 404
        return redirect(res.data['video_url'])
    except Exception:
        return 'Terjadi kesalahan.', 500

# ── Admin: kelola voucher ──────────────────────────────────────────────────────
@app.route('/admin/voucher')
@login_required
def admin_voucher():
    vouchers = get_supabase().table('vouchers').select('*') \
        .order('created_at', desc=True).execute().data or []
    return render_template('admin/voucher.html', vouchers=vouchers)

@app.route('/admin/voucher/generate', methods=['POST'])
@login_required
def admin_voucher_generate():
    import secrets, string
    tipe   = request.form.get('tipe', 'download')
    jumlah = min(int(request.form.get('jumlah', 1)), 50)
    durasi = int(request.form.get('durasi_hari', 30))
    prefix = 'NOADS' if tipe == 'noads' else 'DL'
    alpha  = string.ascii_uppercase + string.digits
    sb     = get_supabase()
    for _ in range(jumlah):
        kode = prefix + '-' + ''.join(secrets.choice(alpha) for _ in range(8))
        sb.table('vouchers').insert({
            'kode':        kode,
            'tipe':        tipe,
            'durasi_hari': durasi if tipe == 'download' else None,
            'used':        False,
        }).execute()
    flash(f'{jumlah} voucher {tipe} berhasil dibuat.', 'success')
    return redirect(url_for('admin_voucher'))

@app.route('/admin/voucher/delete/<int:vid>', methods=['POST'])
@login_required
def admin_voucher_delete(vid):
    get_supabase().table('vouchers').delete().eq('id', vid).execute()
    flash('Voucher dihapus.', 'success')
    return redirect(url_for('admin_voucher'))

# ── Notifikasi Sitewide ────────────────────────────────────────────────────────
def _get_all_notifs():
    try:
        res = get_supabase().table('site_notifications').select('*').order('id').execute()
        return res.data or []
    except Exception:
        return []

@app.context_processor
def inject_notifications():
    try:
        notifs = _get_all_notifs()
        banner  = next((n for n in notifs if n['type'] == 'banner'  and n['aktif']), None)
        marquee = next((n for n in notifs if n['type'] == 'marquee' and n['aktif']), None)
        marquee_items = []
        if marquee and marquee.get('items'):
            items = marquee['items']
            if isinstance(items, str):
                import json
                items = json.loads(items)
            marquee_items = items
        return dict(site_banner=banner, site_marquee=marquee, site_marquee_items=marquee_items)
    except Exception:
        return dict(site_banner=None, site_marquee=None, site_marquee_items=[])

@app.route('/admin/notifikasi', methods=['GET'])
@login_required
def admin_notifikasi():
    notifs = _get_all_notifs()
    banner  = next((n for n in notifs if n['type'] == 'banner'),  None)
    marquee = next((n for n in notifs if n['type'] == 'marquee'), None)
    marquee_items = []
    if marquee and marquee.get('items'):
        items = marquee['items']
        if isinstance(items, str):
            import json
            items = json.loads(items)
        marquee_items = items
    return render_template('admin/notifikasi.html', banner=banner, marquee=marquee, marquee_items=marquee_items)

@app.route('/admin/notifikasi/banner/save', methods=['POST'])
@login_required
def admin_banner_save():
    sb = get_supabase()
    notifs = _get_all_notifs()
    banner = next((n for n in notifs if n['type'] == 'banner'), None)
    data = {
        'konten': request.form.get('konten', '').strip(),
        'warna':  request.form.get('warna', 'info'),
        'aktif':  request.form.get('aktif') == '1',
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }
    if banner:
        sb.table('site_notifications').update(data).eq('id', banner['id']).execute()
    else:
        data['type'] = 'banner'
        data['items'] = []
        sb.table('site_notifications').insert(data).execute()
    flash('Banner disimpan.', 'success')
    return redirect(url_for('admin_notifikasi'))

@app.route('/admin/notifikasi/marquee/save', methods=['POST'])
@login_required
def admin_marquee_save():
    import json
    sb = get_supabase()
    notifs = _get_all_notifs()
    marquee = next((n for n in notifs if n['type'] == 'marquee'), None)
    # Ambil semua judul[] dan link[]
    juduls = request.form.getlist('judul[]')
    links  = request.form.getlist('link[]')
    items  = [{'judul': j.strip(), 'link': l.strip()} for j, l in zip(juduls, links) if j.strip()]
    data = {
        'aktif':  request.form.get('aktif') == '1',
        'items':  json.dumps(items, ensure_ascii=False),
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }
    if marquee:
        sb.table('site_notifications').update(data).eq('id', marquee['id']).execute()
    else:
        data['type'] = 'marquee'
        data['konten'] = ''
        data['warna'] = 'info'
        sb.table('site_notifications').insert(data).execute()
    flash('Marquee disimpan.', 'success')
    return redirect(url_for('admin_notifikasi'))

# ── Inbox / User Messages ──────────────────────────────────────────────────────

def _get_inbox_messages(user_id):
    """Ambil semua pesan untuk user: broadcast + personal."""
    try:
        sb = get_supabase()
        # Pesan broadcast
        broadcast = sb.table('user_messages') \
            .select('*') \
            .eq('target', 'all') \
            .order('created_at', desc=True).execute().data or []

        # Pesan personal ke user ini
        personal = sb.table('user_messages') \
            .select('*') \
            .eq('target', 'user') \
            .eq('to_user_id', str(user_id)) \
            .order('created_at', desc=True).execute().data or []

        # Gabungkan & sort by created_at desc
        all_msgs = broadcast + personal
        all_msgs.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        # Cek status baca per pesan (tabel user_message_reads)
        try:
            reads = sb.table('user_message_reads') \
                .select('message_id') \
                .eq('user_id', str(user_id)).execute().data or []
            read_ids = {r['message_id'] for r in reads}
        except Exception:
            read_ids = set()

        for m in all_msgs:
            m['is_read'] = m['id'] in read_ids

        return all_msgs
    except Exception:
        return []


def _get_unread_count(user_id):
    if not user_id:
        return 0
    try:
        msgs = _get_inbox_messages(user_id)
        return sum(1 for m in msgs if not m.get('is_read'))
    except Exception:
        return 0


@app.context_processor
def inject_inbox_unread():
    user_id = session.get('user_id')
    count = _get_unread_count(user_id) if user_id else 0
    return dict(inbox_unread_count=count)


@app.route('/inbox')
def user_inbox():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('user_login') + '?next=/inbox')
    messages = _get_inbox_messages(user_id)
    unread_count = sum(1 for m in messages if not m.get('is_read'))
    return render_template('inbox.html', messages=messages, unread_count=unread_count)


@app.route('/inbox/read/<int:msg_id>', methods=['POST'])
def inbox_mark_read(msg_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'ok': False}), 401
    try:
        sb = get_supabase()
        # Cek sudah ada atau belum
        existing = sb.table('user_message_reads') \
            .select('id').eq('user_id', str(user_id)).eq('message_id', msg_id).execute().data
        if not existing:
            sb.table('user_message_reads').insert({
                'user_id': str(user_id),
                'message_id': msg_id,
                'read_at': datetime.now(timezone.utc).isoformat()
            }).execute()
    except Exception:
        pass
    return jsonify({'ok': True})


@app.route('/inbox/read-all', methods=['POST'])
def inbox_mark_all_read():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('user_login'))
    try:
        msgs = _get_inbox_messages(user_id)
        sb = get_supabase()
        for m in msgs:
            if not m.get('is_read'):
                try:
                    sb.table('user_message_reads').insert({
                        'user_id': str(user_id),
                        'message_id': m['id'],
                        'read_at': datetime.now(timezone.utc).isoformat()
                    }).execute()
                except Exception:
                    pass
    except Exception:
        pass
    flash('Semua pesan ditandai sudah dibaca.', 'success')
    return redirect(url_for('user_inbox'))


# ── Admin: Kelola Pesan User ───────────────────────────────────────────────────

@app.route('/admin/messages')
@login_required
def admin_messages():
    try:
        msgs = get_supabase().table('user_messages') \
            .select('*').order('created_at', desc=True).execute().data or []

        # Untuk pesan personal, ambil username dari tabel users
        for m in msgs:
            if m.get('target') == 'user' and m.get('to_user_id'):
                try:
                    u = get_supabase().table('users').select('username') \
                        .eq('id', m['to_user_id']).single().execute().data
                    m['to_username'] = u['username'] if u else m['to_user_id']
                except Exception:
                    m['to_username'] = m['to_user_id']
            # Hitung berapa yang sudah baca (untuk broadcast)
            if m.get('target') == 'all':
                try:
                    r = get_supabase().table('user_message_reads') \
                        .select('id', count='exact').eq('message_id', m['id']).execute()
                    m['read_count'] = r.count or 0
                except Exception:
                    m['read_count'] = 0
    except Exception:
        msgs = []
    # Load semua user untuk dropdown
    users = []
    try:
        users = get_supabase().table('users').select('id,username,email') \
            .order('username').execute().data or []
    except Exception:
        pass
    return render_template('admin/messages.html', messages=msgs, users=users)


@app.route('/admin/messages/send', methods=['POST'])
@login_required
def admin_message_send():
    target   = request.form.get('target', 'all')
    to_user  = request.form.get('to_user', '').strip()
    tipe     = request.form.get('tipe', 'info')
    judul    = request.form.get('judul', '').strip()
    isi      = request.form.get('isi', '').strip()
    link     = request.form.get('link', '').strip()

    if not judul or not isi:
        flash('Judul dan isi pesan wajib diisi.', 'error')
        return redirect(url_for('admin_messages'))

    to_user_id = None
    if target == 'user':
        if not to_user:
            flash('Username tujuan wajib diisi untuk pesan personal.', 'error')
            return redirect(url_for('admin_messages'))
        # Resolve username → id
        try:
            res = get_supabase().table('users').select('id').eq('username', to_user).execute()
            if not res.data:
                # Coba cari by id langsung
                res2 = get_supabase().table('users').select('id').eq('id', to_user).execute()
                if not res2.data:
                    flash(f'User "{to_user}" tidak ditemukan.', 'error')
                    return redirect(url_for('admin_messages'))
                to_user_id = res2.data[0]['id']
            else:
                to_user_id = res.data[0]['id']
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            return redirect(url_for('admin_messages'))

    try:
        get_supabase().table('user_messages').insert({
            'target':     target,
            'to_user_id': str(to_user_id) if to_user_id else None,
            'tipe':       tipe,
            'judul':      judul,
            'isi':        isi,
            'link':       link or None,
            'created_at': datetime.now(timezone.utc).isoformat()
        }).execute()
        flash(f'Pesan berhasil dikirim{"ke semua user" if target == "all" else f" ke {to_user}"}.', 'success')
    except Exception as e:
        flash(f'Gagal kirim: {str(e)}', 'error')

    return redirect(url_for('admin_messages'))


@app.route('/admin/messages/delete/<int:msg_id>', methods=['POST'])
@login_required
def admin_message_delete(msg_id):
    try:
        # Hapus data reads dulu biar tidak orphan
        get_supabase().table('user_message_reads').delete().eq('message_id', msg_id).execute()
        get_supabase().table('user_messages').delete().eq('id', msg_id).execute()
        flash('Pesan dihapus.', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('admin_messages'))


if __name__ == '__main__':
    app.run(debug=True)
