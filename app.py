import os
import signal
import subprocess
import threading
import time
import shutil
import zipfile
import psutil
import json
import hashlib
import secrets
import io
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, session, flash
from functools import wraps

def extract_7z_archive(archive_path, output_dir):
    seven_zip = shutil.which("7z") or shutil.which("7zz")
    if not seven_zip:
        raise RuntimeError("7z command not found. Install it in Termux with: pkg install p7zip")
    result = subprocess.run(
        [seven_zip, "x", "-y", archive_path, f"-o{output_dir}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout.strip() or "7z extraction failed")

app = Flask(__name__)
SECRET_KEY_FILE = os.path.join(os.getcwd(), '.secret_key')
try:
    if os.path.exists(SECRET_KEY_FILE):
        with open(SECRET_KEY_FILE, 'r', encoding='utf-8') as _f:
            _persistent_secret = _f.read().strip()
    else:
        _persistent_secret = secrets.token_hex(48)
        with open(SECRET_KEY_FILE, 'w', encoding='utf-8') as _f:
            _f.write(_persistent_secret)
except Exception:
    _persistent_secret = secrets.token_hex(48)
app.secret_key = _persistent_secret

# --- CONFIGURATION ---
BASE_DIR = os.getcwd()
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'user_files')
STATIC_FOLDER = os.path.join(BASE_DIR, 'static')
DB_FILE = 'servers_db.json'
CONFIG_FILE = 'config.json'

if not os.path.exists(STATIC_FOLDER):
    os.makedirs(STATIC_FOLDER)
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

DEFAULT_ICON = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='%2300ff00'%3E%3Cpath d='M20 9V7c0-1.1-.9-2-2-2h-4c0-1.1-.9-2-2-2H6c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-2h-2v2H6V5h4v2h8v2h2z'/%3E%3C/svg%3E"

DEFAULT_CONFIG = {
    "site_title": "SHIHAB X HOSTING",
    "site_header": "SHIHAB X HOSTING",
    "icon_url": DEFAULT_ICON,
    "theme": "matrix",
    "font_family": "default",
    "colors": {
        "matrix": {
            "name": "Matrix Green",
            "primary": "#00ff00",
            "secondary": "#00cc00",
            "accent": "#00ff80",
            "background": "#000000",
            "card_bg": "#0a0a0a",
            "text": "#00ff00",
            "danger": "#ff0000",
            "header_text": "#00ff00",
            "stats_text": "#00ff00"
        }
    },
    "fonts": {
        "default": "'Segoe UI', sans-serif",
        "hacker": "'Courier New', monospace",
        "terminal": "'Consolas', monospace",
        "code": "'Fira Code', monospace",
        "retro": "'VT323', monospace"
    },
    "background": {
        "type": "blackhole",
        "url": "",
        "opacity": 0.82,
        "speed": 1.0,
        "emoji": "❤️✨💎🔥⭐",
        "rain_count": 28
    },
    "branding": {
        "credit": "T10 SHIHAB",
        "version": "3.0.0"
    },
    "passwords": {
        "secret": hashlib.sha256("SHIHAB567".encode()).hexdigest(),
        "user": hashlib.sha256("admin".encode()).hexdigest()
    },
    "users": {
        "admin": {
            "password": hashlib.sha256("misty07".encode()).hexdigest(),
            "role": "admin"
        }
    },
    "default_max_servers": 5,
    "user_limits": {},
    "support": {
        "name": "Support",
        "link": "https://t.me/ShihabXOFC"
    },
    "login_access": {
        "name": "GET ACCESS",
        "link": "https://t.me/Shihab_71S"
    }
}

def load_config():
    """Load config from file, merging with defaults and preserving all keys."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # Ensure all top-level keys exist
            for key, default_val in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = default_val.copy() if isinstance(default_val, dict) else default_val
                elif isinstance(default_val, dict) and isinstance(config.get(key), dict):
                    # Deep merge for dicts (background, colors, fonts, etc.)
                    for sub_key, sub_val in default_val.items():
                        if sub_key not in config[key]:
                            config[key][sub_key] = sub_val
            # Critical: never lose users or passwords
            if 'users' not in config or not config['users']:
                config['users'] = DEFAULT_CONFIG['users'].copy()
            if 'passwords' not in config or not config['passwords']:
                config['passwords'] = DEFAULT_CONFIG['passwords'].copy()
            return config
        except Exception as e:
            print(f"Error loading config: {e}")
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()

def save_config(config):
    """Save config to disk with integrity check and automatic backup."""
    # Ensure critical keys are never lost
    if 'users' not in config or not config['users']:
        config['users'] = DEFAULT_CONFIG['users'].copy()
    if 'passwords' not in config or not config['passwords']:
        config['passwords'] = DEFAULT_CONFIG['passwords'].copy()
    # Ensure all top-level keys exist
    for key, default_val in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = default_val.copy() if isinstance(default_val, dict) else default_val
        elif isinstance(default_val, dict) and isinstance(config.get(key), dict):
            for sub_key, sub_val in default_val.items():
                if sub_key not in config[key]:
                    config[key][sub_key] = sub_val
    # Backup existing config
    if os.path.exists(CONFIG_FILE):
        backup_dir = os.path.join(BASE_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        stamp = time.strftime('%Y%m%d_%H%M%S')
        shutil.copy2(CONFIG_FILE, os.path.join(backup_dir, f'config_{stamp}.json'))
        backups = sorted(
            [os.path.join(backup_dir, x) for x in os.listdir(backup_dir) if x.startswith('config_') and x.endswith('.json')],
            key=os.path.getmtime,
            reverse=True
        )
        for old_backup in backups[10:]:
            try: os.remove(old_backup)
            except OSError: pass
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def reload_config():
    """Force a full reload of the config from disk into the global CONFIG."""
    global CONFIG
    CONFIG = load_config()

CONFIG = load_config()
SERVERS = {}

def save_servers():
    try:
        data = {}
        for sid, s in SERVERS.items():
            data[sid] = {
                'cmd': s.get('cmd', ''),
                'cwd': s.get('cwd', ''),
                'path': s.get('path', ''),
                'auto_restart': s.get('auto_restart', False),
                'restart_interval': s.get('restart_interval', '1h'),
                'status': s.get('status', 'stopped'),
                'last_start_time': s.get('last_start_time', 0),
                'owner': s.get('owner', '')
            }
        with open(DB_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving servers: {e}")

def load_servers():
    global SERVERS
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                saved = json.load(f)
                for sid, s in saved.items():
                    SERVERS[sid] = {
                        'process': None,
                        'cmd': s.get('cmd', ''),
                        'cwd': s.get('cwd', ''),
                        'auto_restart': s.get('auto_restart', False),
                        'restart_interval': s.get('restart_interval', '1h'),
                        'logs': ["Restored from previous session..."],
                        'status': s.get('status', 'stopped'),
                        'path': s.get('path', ''),
                        'last_start_time': s.get('last_start_time', 0),
                        'owner': s.get('owner', '')
                    }
        except Exception as e:
            print(f"Error loading servers: {e}")

load_servers()

@app.route('/static/<path:filename>')
def serve_static(filename):
    try:
        return send_file(os.path.join(STATIC_FOLDER, filename))
    except:
        return "File not found", 404

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_system_stats():
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
    except:
        cpu, ram, disk = 0, 0, 0
    return cpu, ram, disk

def log_monitor(server_id, proc_obj):
    server = SERVERS.get(server_id)
    if not server:
        return
    try:
        for line in iter(proc_obj.stdout.readline, ''):
            if server_id not in SERVERS or SERVERS[server_id].get('process') != proc_obj:
                break
            if line:
                cleaned_line = line.strip()
                if cleaned_line:
                    if len(SERVERS[server_id]['logs']) > 1000:
                        SERVERS[server_id]['logs'] = SERVERS[server_id]['logs'][-900:]
                    SERVERS[server_id]['logs'].append(cleaned_line)
    except Exception as e:
        print(f"Log monitor error: {e}")
    finally:
        try:
            proc_obj.stdout.close()
        except:
            pass
    if server_id in SERVERS and SERVERS[server_id].get('process') == proc_obj:
        SERVERS[server_id]['status'] = 'stopped'
        SERVERS[server_id]['process'] = None
        SERVERS[server_id]['logs'].append(">>> Process terminated.")
        save_servers()

def kill_process_completely(proc):
    try:
        if proc is None: return
        parent = psutil.Process(proc.pid)
        children = parent.children(recursive=True)
        for child in children:
            try: child.terminate()
            except: pass
        gone, alive = psutil.wait_procs(children, timeout=3)
        for child in alive:
            try: child.kill()
            except: pass
        try:
            parent.terminate()
            parent.wait(timeout=3)
        except:
            try: parent.kill()
            except: pass
    except Exception as e:
        print(f"Error killing process: {e}")

def run_install_command(server_id, command):
    if server_id in SERVERS:
        SERVERS[server_id]['logs'].append(f">>> {command}")
        try:
            process = subprocess.Popen(
                command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
            )
            for line in iter(process.stdout.readline, ''):
                if line:
                    SERVERS[server_id]['logs'].append(line.strip())
                    if len(SERVERS[server_id]['logs']) > 1000:
                        SERVERS[server_id]['logs'] = SERVERS[server_id]['logs'][-900:]
            SERVERS[server_id]['logs'].append(">>> Installation finished.")
        except Exception as e:
            SERVERS[server_id]['logs'].append(f"Error: {str(e)}")

def start_server_internal(server_id, server):
    if server['status'] == 'running':
        return True
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    work_dir = os.path.join(server['path'], server.get('cwd', ''))
    if not os.path.exists(work_dir):
        work_dir = server['path']
    try:
        if not server['cmd'] or server['cmd'].strip() == '':
            server['logs'].append(">>> Error: No start command specified")
            return False
        if not os.path.exists(work_dir):
            server['logs'].append(f">>> Error: Working directory does not exist: {work_dir}")
            return False
        proc = subprocess.Popen(
            server['cmd'],
            shell=True,
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env,
            preexec_fn=os.setsid if os.name != 'nt' else None
        )
        server['process'] = proc
        server['status'] = 'running'
        server['last_start_time'] = time.time()
        server['logs'].append(f">>> Server started at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        threading.Thread(target=log_monitor, args=(server_id, proc), daemon=True).start()
        save_servers()
        return True
    except Exception as e:
        server['logs'].append(f">>> Failed to start: {str(e)}")
        return False

def auto_restarter():
    while True:
        time.sleep(5)
        current_time = time.time()
        for server_id, server in list(SERVERS.items()):
            try:
                if server.get('status') == 'running' and server.get('auto_restart'):
                    interval_str = server.get('restart_interval', '1h')
                    interval_map = {
                        '30s': 30, '1m': 60, '5m': 300, '10m': 600, '30m': 1800,
                        '1h': 3600, '2h': 7200, '3h': 10800, '6h': 21600,
                        '12h': 43200, '24h': 86400
                    }
                    interval_sec = interval_map.get(interval_str, 3600)
                    last_start = server.get('last_start_time', current_time)
                    if current_time - last_start >= interval_sec:
                        server['logs'].append(f">>> Auto-restarting server (Interval: {interval_str})...")
                        if server.get('process'):
                            kill_process_completely(server['process'])
                            server['process'] = None
                        server['status'] = 'stopped'
                        start_server_internal(server_id, server)
            except Exception as e:
                print(f"Error in auto_restarter for {server_id}: {e}")

restarter_thread = threading.Thread(target=auto_restarter, daemon=True)
restarter_thread.start()

# ==================== AUTH ====================

# ---- User Login (only user accounts) ----
@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            hashed_input = hashlib.sha256(password.encode()).hexdigest()

            # Check if user exists and is NOT an admin (only operator)
            if username in CONFIG.get('users', {}):
                user_data = CONFIG['users'][username]
                if user_data['role'] == 'admin':
                    return render_template('login.html', config=CONFIG, error="Admin login is not allowed here. Please use the admin login page.")
                if user_data['password'] == hashed_input:
                    session['logged_in'] = True
                    session['username'] = username
                    session['role'] = user_data['role']
                    return redirect(url_for('user_dashboard'))
                else:
                    # Reload config in case it got out of sync
                    reload_config()
                    if username in CONFIG.get('users', {}):
                        user_data = CONFIG['users'][username]
                        if user_data['role'] != 'admin' and user_data['password'] == hashed_input:
                            session['logged_in'] = True
                            session['username'] = username
                            session['role'] = user_data['role']
                            return redirect(url_for('user_dashboard'))
                    return render_template('login.html', config=CONFIG, error="Invalid username or password")

            # Check legacy user password (operator)
            if hashed_input == CONFIG.get('passwords', {}).get('user', ''):
                session['logged_in'] = True
                session['username'] = 'user'
                session['role'] = 'operator'
                return redirect(url_for('user_dashboard'))
            # Reject legacy admin password
            elif hashed_input == CONFIG.get('passwords', {}).get('secret', ''):
                return render_template('login.html', config=CONFIG, error="Admin login is not allowed here. Please use the admin login page.")
            else:
                # Last resort: reload config and try again
                reload_config()
                if username in CONFIG.get('users', {}):
                    user_data = CONFIG['users'][username]
                    if user_data['role'] != 'admin' and user_data['password'] == hashed_input:
                        session['logged_in'] = True
                        session['username'] = username
                        session['role'] = user_data['role']
                        return redirect(url_for('user_dashboard'))
                return render_template('login.html', config=CONFIG, error="Invalid username or password")
        return render_template('login.html', config=CONFIG)
    except Exception as e:
        print(f"Login error: {e}")
        return "Login error", 500

# ---- Admin Login (only admin accounts) ----
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    try:
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            hashed_input = hashlib.sha256(password.encode()).hexdigest()

            # Check if user exists and is admin
            if username in CONFIG.get('users', {}):
                user_data = CONFIG['users'][username]
                if user_data['role'] != 'admin':
                    return render_template('admin_login.html', config=CONFIG, error="Only admin accounts can login here.")
                if user_data['password'] == hashed_input:
                    session['logged_in'] = True
                    session['username'] = username
                    session['role'] = 'admin'
                    return redirect(url_for('admin_dashboard'))
                else:
                    # Reload config and retry
                    reload_config()
                    if username in CONFIG.get('users', {}):
                        user_data = CONFIG['users'][username]
                        if user_data['role'] == 'admin' and user_data['password'] == hashed_input:
                            session['logged_in'] = True
                            session['username'] = username
                            session['role'] = 'admin'
                            return redirect(url_for('admin_dashboard'))
                    return render_template('admin_login.html', config=CONFIG, error="Invalid admin credentials")

            # Check legacy admin password
            if hashed_input == CONFIG.get('passwords', {}).get('secret', ''):
                session['logged_in'] = True
                session['username'] = 'secret_admin'
                session['role'] = 'admin'
                return redirect(url_for('admin_dashboard'))
            # Reject legacy user password
            elif hashed_input == CONFIG.get('passwords', {}).get('user', ''):
                return render_template('admin_login.html', config=CONFIG, error="User login is not allowed here. Please use the user login page.")
            else:
                # Last resort: reload and retry
                reload_config()
                if username in CONFIG.get('users', {}):
                    user_data = CONFIG['users'][username]
                    if user_data['role'] == 'admin' and user_data['password'] == hashed_input:
                        session['logged_in'] = True
                        session['username'] = username
                        session['role'] = 'admin'
                        return redirect(url_for('admin_dashboard'))
                return render_template('admin_login.html', config=CONFIG, error="Invalid admin credentials")
        return render_template('admin_login.html', config=CONFIG)
    except Exception as e:
        print(f"Admin login error: {e}")
        return "Admin login error", 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==================== DASHBOARD ROUTES (Separated) ====================
@app.route('/')
@login_required
def index():
    # Redirect based on role
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('user_dashboard'))

@app.route('/admin')
@login_required
def admin_dashboard():
    if session.get('role') != 'admin':
        flash('Access denied. Admin only.', 'error')
        return redirect(url_for('user_dashboard'))
    return render_dashboard('admin.html')

@app.route('/user')
@login_required
def user_dashboard():
    # Both admin and user can access this, but admin will see all servers; users see only their own.
    return render_dashboard('user.html')

def render_dashboard(template):
    cpu, ram, disk = get_system_stats()
    current_colors = CONFIG['colors'].get(CONFIG['theme'], CONFIG['colors']['matrix'])
    username = session['username']
    role = session['role']
    
    if role == 'admin':
        filtered_servers = {k: v for k, v in SERVERS.items()}
    else:
        filtered_servers = {k: v for k, v in SERVERS.items() if v.get('owner') == username}
        
    serializable_servers = {}
    for sid, s in filtered_servers.items():
        serializable_servers[sid] = {
            'cmd': s.get('cmd', ''),
            'cwd': s.get('cwd', ''),
            'auto_restart': s.get('auto_restart', False),
            'restart_interval': s.get('restart_interval', '1h'),
            'status': s.get('status', 'stopped'),
            'path': s.get('path', ''),
            'last_start_time': s.get('last_start_time', 0),
            'owner': s.get('owner', '')
        }
    
    return render_template(template,
                         servers=serializable_servers,
                         cpu=cpu, ram=ram, disk=disk,
                         total_count=len(SERVERS),
                         running_count=sum(1 for s in SERVERS.values() if s['status'] == 'running'),
                         config=CONFIG,
                         colors=current_colors,
                         role=role,
                         username=username)

# ==================== SERVER MANAGEMENT (shared) ====================
@app.route('/create_server', methods=['POST'])
@login_required
def create_server():
    try:
        username = session['username']
        role = session['role']
        
        server_name = request.form.get('server_name').strip().replace(" ", "_")
        start_command = request.form.get('start_command').strip()
        
        if not server_name:
            flash('Server name is required!', 'error')
            return redirect(url_for('user_dashboard') if role != 'admin' else url_for('admin_dashboard'))
        
        if role != 'admin':
            max_servers = CONFIG['user_limits'].get(username, CONFIG.get('default_max_servers', 5))
            user_servers_count = len([s for s in SERVERS.values() if s.get('owner') == username])
            if user_servers_count >= max_servers:
                flash(f'You have reached your server limit of {max_servers}. Please contact Admin.', 'error')
                return redirect(url_for('user_dashboard'))
        
        if any(s.get('owner') == username and server_name in s.get('path', '') for s in SERVERS.values()):
            flash('Server name already exists for your account!', 'error')
            return redirect(url_for('user_dashboard') if role != 'admin' else url_for('admin_dashboard'))
        
        server_path = os.path.join(UPLOAD_FOLDER, username, server_name)
        os.makedirs(server_path, exist_ok=True)
        
        file = request.files.get('file')
        if file and file.filename:
            file_path = os.path.join(server_path, file.filename)
            file.save(file_path)
            
            if file.filename.lower().endswith('.zip'):
                try:
                    with zipfile.ZipFile(file_path, 'r') as zip_ref:
                        zip_ref.extractall(server_path)
                except Exception as e:
                    print(f"Zip extraction error: {e}")
            elif file.filename.lower().endswith('.7z'):
                try:
                    extract_7z_archive(file_path, server_path)
                except Exception as e:
                    print(f"7z extraction error: {e}")

        SERVERS[server_name] = {
            'process': None,
            'cmd': start_command,
            'cwd': '',
            'logs': [f">>> Server '{server_name}' created by {username} at {time.strftime('%Y-%m-%d %H:%M:%S')}"],
            'auto_restart': False,
            'restart_interval': '1h',
            'last_start_time': 0,
            'status': 'stopped',
            'path': server_path,
            'owner': username
        }
        save_servers()
        
        flash(f'User "{username}" created server "{server_name}" successfully!', 'success')
        return redirect(url_for('user_dashboard') if role != 'admin' else url_for('admin_dashboard'))
    except Exception as e:
        print(f"Create server error: {e}")
        flash(f'Error creating server: {str(e)}', 'error')
        return redirect(url_for('user_dashboard') if session.get('role') != 'admin' else url_for('admin_dashboard'))

@app.route('/action/<server_id>/<action>')
@login_required
def server_action(server_id, action):
    try:
        if server_id not in SERVERS:
            return jsonify({'error': 'Server not found'}), 404
        
        server = SERVERS[server_id]
        current_user = session['username']
        is_admin = session['role'] == 'admin'

        if server.get('owner') != current_user and not is_admin:
            flash('You are not the owner of this server!', 'error')
            return redirect(url_for('user_dashboard') if not is_admin else url_for('admin_dashboard'))

        if action == 'start':
            start_server_internal(server_id, server)
            flash(f'User "{current_user}" started server "{server_id}".', 'success')
            return redirect(url_for('user_dashboard') if not is_admin else url_for('admin_dashboard'))
        elif action == 'stop':
            if server['process']:
                kill_process_completely(server['process'])
                server['process'] = None
            server['status'] = 'stopped'
            server['logs'].append(f">>> Stopped by {current_user} at {time.strftime('%Y-%m-%d %H:%M:%S')}")
            save_servers()
            flash(f'User "{current_user}" stopped server "{server_id}".', 'success')
            return redirect(url_for('user_dashboard') if not is_admin else url_for('admin_dashboard'))
        elif action == 'restart':
            if server['process']:
                kill_process_completely(server['process'])
                server['process'] = None
            server['status'] = 'stopped'
            server['logs'].append(">>> Manual restart triggered...")
            time.sleep(1)
            start_server_internal(server_id, server)
            flash(f'User "{current_user}" restarted server "{server_id}".', 'success')
            return redirect(url_for('user_dashboard') if not is_admin else url_for('admin_dashboard'))
        elif action == 'delete':
            if not is_admin and server.get('owner') != current_user:
                flash('Only admin or owner can delete this server!', 'error')
                return redirect(url_for('user_dashboard') if not is_admin else url_for('admin_dashboard'))
            if server['process']:
                kill_process_completely(server['process'])
                server['process'] = None
            if os.path.exists(server['path']):
                shutil.rmtree(server['path'], ignore_errors=True)
            del SERVERS[server_id]
            save_servers()
            flash(f'User "{current_user}" deleted server "{server_id}".', 'success')
            return redirect(url_for('user_dashboard') if not is_admin else url_for('admin_dashboard'))
        else:
            return jsonify({'error': 'Invalid action'}), 400
    except Exception as e:
        print(f"Server action error: {e}")
        flash(f'Error: {str(e)}', 'error')
        if server_id in SERVERS:
            SERVERS[server_id]['logs'].append(f"Error during {action}: {str(e)}")
        return redirect(url_for('user_dashboard') if session.get('role') != 'admin' else url_for('admin_dashboard'))

# ==================== ADMIN USER MANAGEMENT (only admin) ====================
@app.route('/admin/users', methods=['GET'])
@login_required
def admin_get_users():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    
    users_list = []
    for u, d in CONFIG['users'].items():
        max_limit = CONFIG['user_limits'].get(u, CONFIG.get('default_max_servers', 5))
        users_list.append({'username': u, 'role': d['role'], 'max_servers': max_limit})
    return jsonify({'users': users_list})

@app.route('/admin/users/add', methods=['POST'])
@login_required
def admin_add_user():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'operator')
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    if username in CONFIG['users']:
        return jsonify({'error': 'User already exists'}), 400
    CONFIG['users'][username] = {
        'password': hashlib.sha256(password.encode()).hexdigest(),
        'role': role
    }
    save_config(CONFIG)
    return jsonify({'status': 'ok'})

@app.route('/admin/users/delete/<username>', methods=['POST'])
@login_required
def admin_delete_user(username):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    if username == 'admin' or username == session.get('username'):
        return jsonify({'error': 'Cannot delete current admin or default admin'}), 400
    if username in CONFIG['users']:
        del CONFIG['users'][username]
        if username in CONFIG['user_limits']:
            del CONFIG['user_limits'][username]
        save_config(CONFIG)
        return jsonify({'status': 'ok'})
    return jsonify({'error': 'User not found'}), 404

@app.route('/admin/users/change_password', methods=['POST'])
@login_required
def admin_change_user_password():
    target_user = request.form.get('username', '').strip()
    new_password = request.form.get('new_password', '').strip()
    if session.get('role') != 'admin' and target_user != session.get('username'):
        return jsonify({'error': 'Forbidden'}), 403
    if not target_user or not new_password:
        return jsonify({'error': 'Username and new password required'}), 400
    if target_user not in CONFIG['users']:
        return jsonify({'error': 'User not found'}), 404
    CONFIG['users'][target_user]['password'] = hashlib.sha256(new_password.encode()).hexdigest()
    save_config(CONFIG)
    return jsonify({'status': 'ok'})

@app.route('/admin/users/update_limit', methods=['POST'])
@login_required
def admin_update_user_limit():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    
    username = request.form.get('username', '').strip()
    max_servers = request.form.get('max_servers')
    
    if not username:
        return jsonify({'error': 'Username required'}), 400
    if username not in CONFIG['users']:
        return jsonify({'error': 'User not found'}), 404
    
    try:
        max_servers = int(max_servers)
        if max_servers < 1:
            max_servers = 1
    except (ValueError, TypeError):
        max_servers = CONFIG.get('default_max_servers', 5)
    
    CONFIG['user_limits'][username] = max_servers
    save_config(CONFIG)
    return jsonify({'status': 'ok', 'new_limit': max_servers})

@app.route('/admin/download_user_files/<username>')
@login_required
def admin_download_user_files(username):
    if session.get('role') != 'admin':
        flash('Forbidden: Only Admin can download user files.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    user_dir = os.path.join(UPLOAD_FOLDER, username)
    
    if not os.path.exists(user_dir):
        flash(f'User "{username}" has no uploaded files.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for root, dirs, files in os.walk(user_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, os.path.dirname(user_dir))
                zip_file.write(file_path, arcname)
    
    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name=f'{username}_files.zip',
        mimetype='application/zip'
    )

# ==================== FILE MANAGEMENT (shared) ====================
def check_server_permission(server_id):
    if server_id not in SERVERS:
        return False, "Server not found"
    
    server = SERVERS[server_id]
    current_user = session.get('username')
    is_admin = session.get('role') == 'admin'
    
    if server.get('owner') != current_user and not is_admin:
        return False, "Forbidden: Access denied"
    return True, ""

@app.route('/rename_file/<server_id>', methods=['POST'])
@login_required
def rename_file(server_id):
    try:
        perm, err = check_server_permission(server_id)
        if not perm:
            return jsonify({'error': err}), 403
        old_name = request.form.get('old_name')
        new_name = request.form.get('new_name')
        subpath = request.form.get('path', '')
        if not old_name or not new_name:
            return jsonify({'error': 'Missing names'}), 400
        subpath = subpath.replace('..', '')
        old_name = old_name.replace('..', '')
        new_name = new_name.replace('..', '')
        base_path = SERVERS[server_id]['path']
        old_path = os.path.join(base_path, subpath, old_name)
        new_path = os.path.join(base_path, subpath, new_name)
        if not os.path.exists(old_path):
            return jsonify({'error': 'File not found'}), 404
        if os.path.exists(new_path):
            return jsonify({'error': 'Destination already exists'}), 400
        os.rename(old_path, new_path)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/file_content/<server_id>')
@login_required
def file_content(server_id):
    try:
        perm, err = check_server_permission(server_id)
        if not perm:
            return jsonify({'error': err}), 403
        filename = request.args.get('filename')
        subpath = request.args.get('path', '')
        if not filename:
            return jsonify({'error': 'No filename'}), 400
        subpath = subpath.replace('..', '')
        filename = filename.replace('..', '')
        file_path = os.path.join(SERVERS[server_id]['path'], subpath, filename)
        if not os.path.isfile(file_path):
            return jsonify({'error': 'File not found'}), 404
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return jsonify({'content': content})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/save_file/<server_id>', methods=['POST'])
@login_required
def save_file(server_id):
    try:
        perm, err = check_server_permission(server_id)
        if not perm:
            return jsonify({'error': err}), 403
        filename = request.form.get('filename')
        subpath = request.form.get('path', '')
        content = request.form.get('content')
        if not filename or content is None:
            return jsonify({'error': 'Missing data'}), 400
        subpath = subpath.replace('..', '')
        filename = filename.replace('..', '')
        file_path = os.path.join(SERVERS[server_id]['path'], subpath, filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/create_file/<server_id>', methods=['POST'])
@login_required
def create_file(server_id):
    try:
        perm, err = check_server_permission(server_id)
        if not perm:
            return jsonify({'error': err}), 403
        filename = request.form.get('filename')
        subpath = request.form.get('path', '')
        content = request.form.get('content', '')
        if not filename:
            return jsonify({'error': 'Filename required'}), 400
        subpath = subpath.replace('..', '')
        filename = filename.replace('..', '')
        file_path = os.path.join(SERVERS[server_id]['path'], subpath, filename)
        if os.path.exists(file_path):
            return jsonify({'error': 'File already exists'}), 400
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/extract_archive/<server_id>/<filename>', methods=['POST'])
@login_required
def extract_archive(server_id, filename):
    try:
        perm, err = check_server_permission(server_id)
        if not perm:
            return jsonify({'error': err}), 403
        subpath = request.form.get('path', '')
        subpath = subpath.replace('..', '')
        filename = filename.replace('..', '')
        archive_path = os.path.join(SERVERS[server_id]['path'], subpath, filename)
        if not os.path.exists(archive_path):
            return jsonify({'error': 'Archive not found'}), 404
        extract_to = os.path.dirname(archive_path)
        if filename.lower().endswith('.zip'):
            with zipfile.ZipFile(archive_path, 'r') as z:
                z.extractall(extract_to)
        elif filename.lower().endswith('.7z'):
            extract_7z_archive(archive_path, extract_to)
        else:
            return jsonify({'error': 'Unsupported archive format'}), 400
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_logs/<server_id>')
@login_required
def get_logs(server_id):
    try:
        perm, err = check_server_permission(server_id)
        if not perm:
            return jsonify({'logs': f'Error: {err}'})
        if server_id in SERVERS:
            return jsonify({'logs': "\n".join(SERVERS[server_id]['logs'][-500:])})
        return jsonify({'logs': ''})
    except Exception as e:
        return jsonify({'logs': f'Error: {e}'})

@app.route('/send_input/<server_id>', methods=['POST'])
@login_required
def send_input(server_id):
    try:
        perm, err = check_server_permission(server_id)
        if not perm:
            return jsonify({'status': 'error', 'message': err}), 403
        cmd = request.form.get('command')
        if not cmd:
            return jsonify({'status': 'error', 'message': 'No command provided'})
        server = SERVERS[server_id]
        if not server['process']:
            return jsonify({'status': 'error', 'message': 'Process not running'})
        proc = server['process']
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.write(cmd + "\n")
            proc.stdin.flush()
            server['logs'].append(f">>> Input: {cmd}")
            return jsonify({'status': 'ok'})
        else:
            return jsonify({'status': 'error', 'message': 'stdin closed'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/files/<server_id>')
@login_required
def list_files(server_id):
    try:
        perm, err = check_server_permission(server_id)
        if not perm:
            return jsonify({'error': err}), 403
        subpath = request.args.get('path', '')
        if '..' in subpath:
            subpath = ''
        base_path = SERVERS[server_id]['path']
        full_path = os.path.join(base_path, subpath)
        if not os.path.realpath(full_path).startswith(os.path.realpath(base_path)):
            full_path = base_path
            subpath = ''
        if not os.path.exists(full_path):
            full_path = base_path
            subpath = ''
        files = []
        total_size = 0
        for item in os.listdir(full_path):
            item_path = os.path.join(full_path, item)
            is_file = os.path.isfile(item_path)
            size = 0
            if is_file:
                size = os.path.getsize(item_path)
                total_size += size
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size/1024:.1f} KB"
            else:
                size_str = f"{size/(1024*1024):.1f} MB"
            files.append({
                'name': item,
                'size': size_str,
                'raw_size': size,
                'type': 'file' if is_file else 'dir',
                'ext': os.path.splitext(item)[1].lower() if is_file else ''
            })
        files.sort(key=lambda x: (x['type'] != 'dir', x['name'].lower()))
        return jsonify({
            'files': files,
            'cmd': SERVERS[server_id]['cmd'],
            'cwd': SERVERS[server_id].get('cwd', ''),
            'auto_restart': SERVERS[server_id].get('auto_restart', False),
            'restart_interval': SERVERS[server_id].get('restart_interval', '1h'),
            'current_path': subpath,
            'total_size': str(total_size)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/upload/<server_id>', methods=['POST'])
@login_required
def upload_file(server_id):
    try:
        perm, err = check_server_permission(server_id)
        if not perm:
            return jsonify({'error': err}), 403
        file = request.files.get('file')
        subpath = request.form.get('path', '')
        if '..' in subpath:
            subpath = ''
        if not file or not file.filename:
            return jsonify({'error': 'No file provided'}), 400
        target_dir = os.path.join(SERVERS[server_id]['path'], subpath)
        if not os.path.realpath(target_dir).startswith(os.path.realpath(SERVERS[server_id]['path'])):
            return jsonify({'error': 'Invalid path'}), 400
        os.makedirs(target_dir, exist_ok=True)
        file_path = os.path.join(target_dir, file.filename)
        file.save(file_path)
        if file.filename.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(file_path, 'r') as z:
                    z.extractall(target_dir)
                return jsonify({'status': 'ok', 'message': 'File uploaded and extracted successfully'})
            except Exception as e:
                return jsonify({'status': 'ok', 'warning': f'File uploaded but extraction failed: {str(e)}'})
        elif file.filename.lower().endswith('.7z'):
            try:
                extract_7z_archive(file_path, target_dir)
                return jsonify({'status': 'ok', 'message': 'File uploaded and extracted successfully'})
            except Exception as e:
                return jsonify({'status': 'ok', 'warning': f'File uploaded but extraction failed: {str(e)}'})
        return jsonify({'status': 'ok', 'message': 'File uploaded successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/create_folder/<server_id>', methods=['POST'])
@login_required
def create_folder(server_id):
    try:
        perm, err = check_server_permission(server_id)
        if not perm:
            return jsonify({'error': err}), 403
        folder_name = request.form.get('name')
        subpath = request.form.get('path', '')
        if '..' in subpath:
            subpath = ''
        if not folder_name:
            return jsonify({'error': 'Folder name required'}), 400
        folder_name = folder_name.replace('..', '')
        target = os.path.join(SERVERS[server_id]['path'], subpath, folder_name)
        if not os.path.realpath(target).startswith(os.path.realpath(SERVERS[server_id]['path'])):
            return jsonify({'error': 'Invalid path'}), 400
        os.makedirs(target, exist_ok=True)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<server_id>/<filename>')
@login_required
def download_file(server_id, filename):
    try:
        perm, err = check_server_permission(server_id)
        if not perm:
            return err, 403
        subpath = request.args.get('path', '')
        if '..' in subpath or '..' in filename:
            return "Invalid path", 400
        file_path = os.path.join(SERVERS[server_id]['path'], subpath, filename)
        if not os.path.exists(file_path):
            return "File not found", 404
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        return str(e), 500

@app.route('/delete_file/<server_id>/<filename>')
@login_required
def delete_file(server_id, filename):
    try:
        perm, err = check_server_permission(server_id)
        if not perm:
            return jsonify({'error': err}), 403
        subpath = request.args.get('path', '')
        if '..' in subpath or '..' in filename:
            return jsonify({'error': 'Invalid path'}), 400
        file_path = os.path.join(SERVERS[server_id]['path'], subpath, filename)
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
        if os.path.isdir(file_path):
            shutil.rmtree(file_path)
        else:
            os.remove(file_path)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/update_settings/<server_id>', methods=['POST'])
@login_required
def update_settings(server_id):
    try:
        perm, err = check_server_permission(server_id)
        if not perm:
            return jsonify({'error': err}), 403
        cmd = request.form.get('cmd', '').strip()
        cwd = request.form.get('cwd', '').strip()
        auto_restart = request.form.get('auto_restart') == 'true'
        restart_interval = request.form.get('restart_interval', '1h')
        SERVERS[server_id]['cmd'] = cmd
        SERVERS[server_id]['cwd'] = cwd
        SERVERS[server_id]['auto_restart'] = auto_restart
        SERVERS[server_id]['restart_interval'] = restart_interval
        SERVERS[server_id]['logs'].append(f">>> Settings updated at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        save_servers()
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== PACKAGE MANAGEMENT (shared) ====================
@app.route('/install_pkg/<server_id>', methods=['POST'])
@login_required
def install_pkg(server_id):
    try:
        perm, err = check_server_permission(server_id)
        if not perm:
            return jsonify({'error': err}), 403
        pkg_type = request.form.get('type')
        pkg_name = request.form.get('name')
        if not pkg_name:
            return jsonify({'error': 'Package name required'}), 400
        cmd = ""
        if pkg_type == 'pip':
            cmd = f"pip install {pkg_name}"
        elif pkg_type == 'pkg':
            cmd = f"pkg install -y {pkg_name}"
        elif pkg_type == 'apt':
            cmd = f"apt-get install -y {pkg_name}"
        elif pkg_type == 'npm':
            cmd = f"npm install -g {pkg_name}"
        else:
            return jsonify({'error': 'Invalid package type'}), 400
        threading.Thread(target=run_install_command, args=(server_id, cmd), daemon=True).start()
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/uninstall_pkg/<server_id>', methods=['POST'])
@login_required
def uninstall_pkg(server_id):
    try:
        perm, err = check_server_permission(server_id)
        if not perm:
            return jsonify({'error': err}), 403
        pkg_type = request.form.get('type')
        pkg_name = request.form.get('name')
        if not pkg_name:
            return jsonify({'error': 'Package name required'}), 400
        cmd = ""
        if pkg_type == 'pip':
            cmd = f"pip uninstall -y {pkg_name}"
        elif pkg_type == 'pkg':
            cmd = f"pkg uninstall -y {pkg_name}"
        elif pkg_type == 'apt':
            cmd = f"apt-get remove -y {pkg_name}"
        elif pkg_type == 'npm':
            cmd = f"npm uninstall -g {pkg_name}"
        else:
            return jsonify({'error': 'Invalid package type'}), 400
        threading.Thread(target=run_install_command, args=(server_id, cmd), daemon=True).start()
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== TELEGRAM BOT (admin only) ====================
@app.route('/telegram_bot', methods=['POST'])
@login_required
def telegram_bot():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    try:
        token = request.form.get('token')
        if not token:
            return jsonify({'error': 'Token required'}), 400
        if ':' not in token or len(token) < 40:
            return jsonify({'error': 'Invalid token format'}), 400
        
        username = session['username']
        # For admin, no limit check; they can create unlimited bots
        timestamp = int(time.time())
        server_name = f"tg_bot_{timestamp}"
        server_path = os.path.join(UPLOAD_FOLDER, username, server_name)
        os.makedirs(server_path, exist_ok=True)
        bot_script = '''import asyncio
import requests
import time
import platform
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

BOT_TOKEN = "{}"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

START_TIME = time.time()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "🤖 *SHIHAB X HOSTING Telegram Bot*\\n\\n"
        "Send API request like:\\n"
        "`/api https://api.github.com`\\n\\n"
        "*Commands:*\\n"
        "/start - Show this message\\n"
        "/help - Show help\\n"
        "/api <url> - Check API endpoint\\n"
        "/ping - Check bot status\\n"
        "/uptime - Show bot uptime\\n"
        "/info - Show system info",
        parse_mode='Markdown'
    )

@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    await message.answer(
        "📚 *Available Commands:*\\n\\n"
        "🔹 `/start` - Welcome message\\n"
        "🔹 `/help` - Show this help\\n"
        "🔹 `/api <url>` - Check API endpoint\\n"
        "🔹 `/ping` - Check bot status\\n"
        "🔹 `/uptime` - Show bot uptime\\n"
        "🔹 `/info` - Show system info\\n\\n"
        "📌 *API Check Example:*\\n"
        "`/api https://api.github.com`",
        parse_mode='Markdown'
    )

@dp.message(Command("ping"))
async def ping(message: types.Message):
    await message.answer("🏓 Pong! Bot is alive!")

@dp.message(Command("uptime"))
async def uptime(message: types.Message):
    uptime_seconds = int(time.time() - START_TIME)
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60
    uptime_str = f"⏱ *Bot Uptime:*\\n"
    if days > 0:
        uptime_str += f"{days} days, "
    uptime_str += f"{hours}h {minutes}m {seconds}s"
    await message.answer(uptime_str, parse_mode='Markdown')

@dp.message(Command("info"))
async def info(message: types.Message):
    info_text = f"""
📊 *System Information*
• Platform: {platform.system()} {platform.release()}
• Python: {platform.python_version()}
• Bot Status: Active
• Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
• Host: SHIHAB X HOSTING (24/7 Uptime)
    """
    await message.answer(info_text, parse_mode='Markdown')

@dp.message(Command("api"))
async def api_check(message: types.Message):
    args = message.text.split(" ", 1)
    if len(args) < 2:
        await message.answer(
            "❌ *Usage:*\\n"
            "`/api <url>`\\n\\n"
            "📌 *Example:*\\n"
            "`/api https://api.github.com`",
            parse_mode='Markdown'
        )
        return
    url = args[1].strip()
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        r = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (SHIHAB X HOSTING Bot)'
        })
        try:
            import json
            response_json = r.json()
            text = json.dumps(response_json, indent=2, ensure_ascii=False)
        except:
            text = r.text
        if len(text) > 3500:
            text = text[:3500] + "\\n\\n... (response too long)"
        await message.answer(
            f"📡 *API Response:*\\n"
            f"• URL: `{url}`\\n"
            f"• Status: `{r.status_code}`\\n"
            f"• Time: `{r.elapsed.total_seconds():.2f}s`\\n\\n"
            f"```\\n{text}\\n```",
            parse_mode='Markdown'
        )
    except requests.exceptions.Timeout:
        await message.answer("❌ *Error:* Request timeout (15s)", parse_mode='Markdown')
    except requests.exceptions.ConnectionError:
        await message.answer("❌ *Error:* Connection failed", parse_mode='Markdown')
    except Exception as e:
        await message.answer(f"❌ *Error:* `{str(e)}`", parse_mode='Markdown')

async def main():
    print("✅ Bot Started Successfully!")
    me = await bot.get_me()
    print(f"🤖 Bot Username: @{me.username}")
    print(f"⏱ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
'''.format(token)
        script_path = os.path.join(server_path, "bot.py")
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(bot_script)
        with open(os.path.join(server_path, "requirements.txt"), 'w') as f:
            f.write("aiogram==3.4.1\\nrequests==2.31.0")
        SERVERS[server_name] = {
            'process': None,
            'cmd': 'pip install -r requirements.txt && python bot.py',
            'cwd': '',
            'logs': [
                f">>> Telegram Bot created by {username} at {time.strftime('%Y-%m-%d %H:%M:%S')}",
                f">>> Token: {token[:10]}...{token[-5:]}",
                ">>> Use 'Start' to launch the bot"
            ],
            'auto_restart': True,
            'restart_interval': '24h',
            'last_start_time': 0,
            'status': 'stopped',
            'path': server_path,
            'owner': username
        }
        save_servers()
        return jsonify({
            'status': 'ok', 
            'server_name': server_name,
            'message': 'Bot created successfully!'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== THEME & SETTINGS (admin only) ====================
@app.route('/update_config', methods=['POST'])
@login_required
def update_config():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    try:
        site_title = request.form.get('site_title')
        site_header = request.form.get('site_header')
        icon_url = request.form.get('icon_url')
        theme = request.form.get('theme')
        font_family = request.form.get('font_family')
        
        support_name = request.form.get('support_name')
        support_link = request.form.get('support_link')
        
        login_access_name = request.form.get('login_access_name')
        login_access_link = request.form.get('login_access_link')
        
        if site_title is not None:
            CONFIG['site_title'] = site_title
        if site_header is not None:
            CONFIG['site_header'] = site_header
        if icon_url is not None:
            CONFIG['icon_url'] = icon_url
        if theme and theme in CONFIG['colors']:
            CONFIG['theme'] = theme
        if font_family and font_family in CONFIG['fonts']:
            CONFIG['font_family'] = font_family
            
        if support_name is not None:
            CONFIG['support']['name'] = support_name
        if support_link is not None:
            CONFIG['support']['link'] = support_link
            
        if login_access_name is not None:
            CONFIG['login_access']['name'] = login_access_name
        if login_access_link is not None:
            CONFIG['login_access']['link'] = login_access_link
            
        save_config(CONFIG)
        return jsonify({'status': 'ok'})
    except Exception as e:
        print(f"Error updating config: {e}")
        return jsonify({'error': f'Failed to save config: {str(e)}'}), 500

ALLOWED_BG_EXTENSIONS = {'.mp4', '.webm', '.mov', '.jpg', '.jpeg', '.png', '.webp', '.gif'}

@app.route('/upload_background', methods=['POST'])
@login_required
def upload_background():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    try:
        media = request.files.get('background_file')
        if not media or not media.filename:
            return jsonify({'error': 'No background file selected'}), 400
        ext = os.path.splitext(media.filename)[1].lower()
        if ext not in ALLOWED_BG_EXTENSIONS:
            return jsonify({'error': 'Unsupported background format'}), 400
        bg_dir = os.path.join(STATIC_FOLDER, 'backgrounds')
        os.makedirs(bg_dir, exist_ok=True)
        safe_name = f"bg_{secrets.token_hex(8)}{ext}"
        target = os.path.join(bg_dir, safe_name)
        media.save(target)
        old_url = CONFIG.get('background', {}).get('url', '')
        if old_url.startswith('/static/backgrounds/'):
            old_file = os.path.join(BASE_DIR, old_url.lstrip('/').replace('/', os.sep))
            if os.path.isfile(old_file) and os.path.realpath(old_file).startswith(os.path.realpath(bg_dir)):
                try: os.remove(old_file)
                except OSError: pass
        CONFIG.setdefault('background', {})
        CONFIG['background']['url'] = f'/static/backgrounds/{safe_name}'
        save_config(CONFIG)
        return jsonify({'status': 'ok', 'url': CONFIG['background']['url']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/update_background', methods=['POST'])
@login_required
def update_background():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    try:
        bg_type = request.form.get('background_type', 'blackhole')
        allowed_types = {'black', 'blackhole', 'emoji', 'rain', 'image', 'video'}
        if bg_type not in allowed_types:
            return jsonify({'error': 'Invalid background type'}), 400
        CONFIG.setdefault('background', {})
        CONFIG['background']['type'] = bg_type
        CONFIG['background']['opacity'] = max(0.05, min(1.0, float(request.form.get('opacity', 0.82))))
        CONFIG['background']['speed'] = max(0.2, min(4.0, float(request.form.get('speed', 1.0))))
        CONFIG['background']['emoji'] = (request.form.get('emoji') or '❤️✨💎🔥⭐')[:200]
        CONFIG['background']['rain_count'] = max(5, min(80, int(request.form.get('rain_count', 28))))
        save_config(CONFIG)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/reset_background', methods=['POST'])
@login_required
def reset_background():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    try:
        old_url = CONFIG.get('background', {}).get('url', '')
        if old_url.startswith('/static/backgrounds/'):
            old_file = os.path.join(BASE_DIR, old_url.lstrip('/').replace('/', os.sep))
            bg_dir = os.path.join(STATIC_FOLDER, 'backgrounds')
            if os.path.isfile(old_file) and os.path.realpath(old_file).startswith(os.path.realpath(bg_dir)):
                try: os.remove(old_file)
                except OSError: pass
        CONFIG['background'] = DEFAULT_CONFIG['background'].copy()
        save_config(CONFIG)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    try:
        current = request.form.get('current_password')
        new = request.form.get('new_password')
        if not current or not new:
            return jsonify({'error': 'All fields required'}), 400
        username = session.get('username')
        if username not in CONFIG['users']:
            return jsonify({'error': 'User not found'}), 404
        current_hashed = hashlib.sha256(current.encode()).hexdigest()
        if CONFIG['users'][username]['password'] != current_hashed:
            return jsonify({'error': 'Current password incorrect'}), 403
        CONFIG['users'][username]['password'] = hashlib.sha256(new.encode()).hexdigest()
        save_config(CONFIG)
        return jsonify({'status': 'ok', 'message': 'Password updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/server_info/<server_id>')
@login_required
def server_info(server_id):
    try:
        perm, err = check_server_permission(server_id)
        if not perm:
            return jsonify({'error': err}), 403
        s = SERVERS[server_id]
        uptime = 0
        if s['status'] == 'running' and s['last_start_time'] > 0:
            uptime = int(time.time() - s['last_start_time'])
        return jsonify({
            'status': s['status'],
            'auto_restart': s.get('auto_restart', False),
            'restart_interval': s.get('restart_interval', '1h'),
            'last_start_time': s.get('last_start_time', 0),
            'uptime': uptime
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/system_stats')
@login_required
def system_stats():
    try:
        cpu, ram, disk = get_system_stats()
        return jsonify({
            'cpu': cpu,
            'ram': ram,
            'disk': disk
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/ping")
def ping():
    return "alive"

@app.route("/json")
def json_alive():
    return jsonify({
        "status": "alive",
        "time": time.time(),
        "version": "3.0.0"
    })

@app.errorhandler(404)
def not_found(e):
    if session.get('logged_in'):
        return redirect(url_for('user_dashboard') if session.get('role') != 'admin' else url_for('admin_dashboard'))
    return redirect(url_for('login'))

@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    port = int(os.environ.get("PORT", 30099))
    debug = os.environ.get("DEBUG", "False").lower() == "true"
    print("=" * 50)
    print("SHIHAB X HOSTING - Starting...")
    print("=" * 50)
    print(f"Port: {port}")
    print(f"Default Admin User: admin / Password: admin")
    print("=" * 50)
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)