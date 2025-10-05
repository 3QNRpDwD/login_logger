"""
Secure Login Vault

Features implemented:
- Uses SQLCipher (if available) for an encrypted SQLite DB (tries sqlcipher3 / pysqlcipher3 / sqlcipher3-binary).
- If SQLCipher is not available, falls back to plain sqlite3 + per-password encryption using cryptography.Fernet with a key derived from the master password via PBKDF2.
- Tkinter GUI (ttk) with a modern-ish look, a list of entries, add/edit/delete, and a "Show password" action that shows a progress bar while decrypting.
- Embedded Flask web UI (served on 127.0.0.1 only). The web UI lists accounts; clicking "Show" requests the server to decrypt that single password and returns it; the web UI shows a progress animation while waiting.

Notes:
- You MUST provide a master password on startup. The master password is NOT stored; it's used to open the SQLCipher DB (PRAGMA key) or derive the Fernet key.
- If you want real SQLCipher usage, install a Python wheel that includes SQLCipher (sqlcipher3-binary or pysqlcipher3) and have SQLCipher available on your system. Otherwise the fallback is used.

Dependencies:
- cryptography
- flask
- (optional) sqlcipher3 / pysqlcipher3 / sqlcipher3-binary

Run: python login_vault.py

"""

import os
import sys
import json
import time
import threading
import traceback
import re
from datetime import datetime
import base64
import time
import socket
import webbrowser
import subprocess



try:
    # prefer sqlcipher3 (coleifer) / sqlcipher3-binary
    from sqlcipher3 import dbapi2 as sqlcipher_dbapi
    SQLCIPHER_PYTHON_MODULE = 'sqlcipher3'
except Exception:
    try:
        from pysqlcipher3 import dbapi2 as sqlcipher_dbapi
        SQLCIPHER_PYTHON_MODULE = 'pysqlcipher3'
    except Exception:
        sqlcipher_dbapi = None
        SQLCIPHER_PYTHON_MODULE = None

import sqlite3
from getpass import getpass

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet

from tkinter import Tk, Toplevel, StringVar, messagebox, simpledialog, filedialog
from tkinter import ttk
import tkinter as tk

# Flask and web server
from flask import Flask, jsonify, request, render_template, abort


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


# --------------------------- Vault backend ---------------------------

META_FILE = "vault_meta.json"
DB_FILE = "vault.db"
FALLBACK_DB_FILE = "vault_plain.db"
CACHE_FILE = "vault.cache"

SALT_SIZE = 16
KDF_ITER = 390000

BOOTSTRAP_CDN = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css"

class VaultError(Exception):
    pass

class Vault:
    """Abstraction over either an SQLCipher-backed DB or a sqlite3 fallback using Fernet encryption per-password."""

    def __init__(self, master_password: str):
        self.master = master_password
        self.use_sqlcipher = False
        self.conn = None
        self.backend = None  # 'sqlcipher' or 'fallback'
        self.fernet = None
        self.meta = {}

        # Decide approach
        if sqlcipher_dbapi is not None:
            try:
                # try opening DB with SQLCipher
                self.conn = sqlcipher_dbapi.connect(DB_FILE)
                cur = self.conn.cursor()
                # set key using provided master password
                # Use PRAGMA key - SQLCipher understands passphrase
                cur.execute("PRAGMA key = ?;", (self.master,))
                # try a simple query to see if the key works or DB needs creation
                try:
                    cur.execute("SELECT count(*) FROM sqlite_master;")
                    cur.fetchall()
                except Exception:
                    # maybe DB not initialized or key mismatch; we'll proceed and create tables
                    pass

                self.use_sqlcipher = True
                self.backend = 'sqlcipher'
                self._ensure_tables_sqlcipher()
                return
            except Exception as e:
                # If SQLCipher import present but key wrong or other problem, fallback
                print("SQLCipher available but could not initialize; falling back to encrypted sqlite.\nReason:", e)
                traceback.print_exc()

        # Fallback: sqlite + per-password Fernet derived from master password
        self.backend = 'fallback'
        # load or create metadata (salt)
        if os.path.exists(META_FILE):
            with open(META_FILE, 'r') as f:
                self.meta = json.load(f)
            salt = bytes.fromhex(self.meta.get('salt'))
        else:
            salt = os.urandom(SALT_SIZE)
            self.meta = {
                'salt': salt.hex(),
                'version': 1
            }
            with open(META_FILE, 'w') as f:
                json.dump(self.meta, f)

        # derive a Fernet key from master password
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=KDF_ITER,
            backend=default_backend()
        )
        key = kdf.derive(self.master.encode())
        fkey = base64_urlsafe_from_bytes(key)
        self.fernet = Fernet(fkey)

        self.conn = sqlite3.connect(FALLBACK_DB_FILE, check_same_thread=False)
        self._ensure_tables_fallback()

    def _ensure_tables_sqlcipher(self):
        cur = self.conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY, platform TEXT, username TEXT, password TEXT, note TEXT, created_at TEXT);")
        self.conn.commit()

    def _ensure_tables_fallback(self):
        cur = self.conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY, platform TEXT, username TEXT, password TEXT, note TEXT, created_at TEXT);")
        self.conn.commit()

    def add_account(self, platform, username, password, note="", created_at=None):
        ts = created_at or datetime.utcnow().isoformat()
        if self.backend == 'sqlcipher':
            cur = self.conn.cursor()
            cur.execute("INSERT INTO accounts (platform, username, password, note, created_at) VALUES (?, ?, ?, ?, ?)", (platform, username, password, note, ts))
            self.conn.commit()
            return cur.lastrowid
        else:
            # encrypt the password with Fernet
            token = self.fernet.encrypt(base64.b64encode(password.encode())).decode()
            cur = self.conn.cursor()
            cur.execute("INSERT INTO accounts (platform, username, password, note, created_at) VALUES (?, ?, ?, ?, ?)", (platform, username, token, note, ts))
            self.conn.commit()
            return cur.lastrowid

    def list_accounts(self):
        cur = self.conn.cursor()
        cur.execute("SELECT id, platform, username, created_at, note FROM accounts ORDER BY platform COLLATE NOCASE;")
        rows = cur.fetchall()
        return [{'id': r[0], 'platform': r[1], 'username': r[2], 'created_at': r[3], 'note': r[4]} for r in rows]

    def get_account(self, id_):
        cur = self.conn.cursor()
        cur.execute("SELECT id, platform, username, password, note, created_at FROM accounts WHERE id=?", (id_,))
        r = cur.fetchone()
        if not r:
            return None
        return {'id': r[0], 'platform': r[1], 'username': r[2], 'password': r[3], 'note': r[4], 'created_at': r[5]}

    def decrypt_password(self, id_):
        # return plaintext password for given id
        rec = self.get_account(id_)
        print("decrypt_password", rec)
        if not rec:
            raise VaultError('Not found')
        if self.backend == 'sqlcipher':
            # in SQLCipher mode we stored plaintext password already (DB itself is encrypted)
            return rec['password']
        else:
            token = rec['password']
            print("decrypt_password", token)
            try:
                return base64.b64decode(self.fernet.decrypt(token.encode()).decode()).decode()
            except Exception as e:
                raise VaultError('Decryption failed')

    def delete_account(self, id_):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM accounts WHERE id=?", (id_,))
        self.conn.commit()

    def update_account(self, id_, platform, username, password, note=""):
        if password is None:
            # keep existing
            password = self.decrypt_password(id_)
        if self.backend == 'sqlcipher':
            cur = self.conn.cursor()
            cur.execute("UPDATE accounts SET platform=?, username=?, password=?, note=? WHERE id=?", (platform, username, password, note, id_))
            self.conn.commit()
        else:
            token = self.fernet.encrypt(base64.b64encode(password.encode())).decode()
            cur = self.conn.cursor()
            cur.execute("UPDATE accounts SET platform=?, username=?, password=?, note=? WHERE id=?", (platform, username, token, note, id_))
            self.conn.commit()

# --------------------------- Utilities ---------------------------

def base64_urlsafe_from_bytes(b: bytes) -> bytes:
    """Convert 32 bytes to a Fernet key (base64 urlsafe)"""
    return base64.urlsafe_b64encode(b)

# --------------------------- Caching ---------------------------

class PasswordCacher:
    def __init__(self):
        self.machine_id = self._get_machine_id()
        self.fernet = None
        if self.machine_id:
            try:
                # Derive a key from the machine ID
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=b'vault-cache-salt', # Fixed salt is fine here
                    iterations=100000,
                    backend=default_backend()
                )
                key = kdf.derive(self.machine_id.encode())
                self.fernet = Fernet(base64.urlsafe_b64encode(key))
            except Exception as e:
                print(f"Could not initialize password cacher: {e}")

    def _get_machine_id(self):
        if sys.platform == 'win32':
            try:
                return subprocess.check_output('wmic csproduct get uuid').decode().split('\n')[1].strip()
            except Exception:
                try:
                    return subprocess.check_output('wmic path win32_logicaldisk where "DeviceID=\'C:\'" get VolumeSerialNumber').decode().split('\n')[1].strip()
                except Exception as e:
                    print(f"Could not get machine ID for caching: {e}")
                    return None
        else:
            print("Password caching is currently only supported on Windows.")
            return None

    def get_cached_password(self):
        if not self.fernet or not os.path.exists(CACHE_FILE):
            return None
        try:
            with open(CACHE_FILE, 'rb') as f:
                token = f.read()
            decrypted_pw = self.fernet.decrypt(token)
            return decrypted_pw.decode()
        except Exception as e:
            print(f"Failed to read cached password: {e}")
            if os.path.exists(CACHE_FILE):
                os.remove(CACHE_FILE)
            return None

    def cache_password(self, password):
        if not self.fernet:
            return
        try:
            token = self.fernet.encrypt(password.encode())
            with open(CACHE_FILE, 'wb') as f:
                f.write(token)
            print("Password has been cached.")
        except Exception as e:
            print(f"Failed to cache password: {e}")

    def ask_and_cache(self, password):
        root = Tk()
        root.withdraw()
        should_cache = messagebox.askyesno(
            "Cache Password",
            "Do you want to cache the master password for automatic login on this computer?\n\n"
            "Warning: This is convenient but less secure. The password will be stored in an encrypted file on this machine.",
            parent=root
        )
        root.destroy()
        if should_cache:
            self.cache_password(password)


# --------------------------- GUI ---------------------------

class VaultGUI:
    def __init__(self, vault: Vault):
        self.vault = vault
        self.root = Tk()
        self.root.title("Secure Login Vault")
        self.root.geometry("920x600")
        self.style = ttk.Style(self.root)
        self._accounts_hash = None
        # use clam and configure styles
        try:
            self.style.theme_use('clam')
        except Exception:
            pass
        self._setup_styles()
        self._build_ui()
        self._refresh_list()
        self.flask_thread = None
        self.flask_app = None
        self._check_for_updates()

    def _setup_styles(self):
        self.style.configure('TFrame', background='#f8f9fa')
        self.style.configure('TLabel', background='#f8f9fa')
        self.style.configure('Header.TLabel', font=('Segoe UI', 18, 'bold'))
        self.style.configure('Accent.TButton', font=('Segoe UI', 10, 'bold'))

    def _build_ui(self):
        # panes
        left = ttk.Frame(self.root, width=320)
        left.pack(side='left', fill='y', padx=12, pady=12)
        right = ttk.Frame(self.root)
        right.pack(side='right', expand=True, fill='both', padx=12, pady=12)

        ttk.Label(left, text='Vault', style='Header.TLabel').pack(anchor='w')
        self.search_var = StringVar()
        sbox = ttk.Entry(left, textvariable=self.search_var)
        sbox.pack(fill='x', pady=(8,6))
        sbox.bind('<KeyRelease>', lambda e: self._refresh_list())

        self.accounts_list = tk.Listbox(left, height=25)
        self.accounts_list.pack(fill='both', expand=True)
        self.accounts_list.bind('<<ListboxSelect>>', lambda e: self._on_select())

        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill='x', pady=8)
        ttk.Button(btn_frame, text='Add', command=self._add_entry).pack(side='left', expand=True, fill='x')
        ttk.Button(btn_frame, text='Import', command=self._import_html).pack(side='left', expand=True, fill='x')
        ttk.Button(btn_frame, text='Migrate', command=self._migrate_data).pack(side='left', expand=True, fill='x')
        ttk.Button(btn_frame, text='Edit', command=self._edit_entry).pack(side='left', expand=True, fill='x')
        ttk.Button(btn_frame, text='Delete', command=self._delete_entry).pack(side='left', expand=True, fill='x')

        # Right: details
        ttk.Label(right, text='Details', style='Header.TLabel').pack(anchor='w')
        details = ttk.Frame(right)
        details.pack(fill='both', expand=True, pady=(8,0))

        self.platform_var = StringVar()
        self.username_var = StringVar()
        self.note_var = StringVar()

        ttk.Label(details, text='Platform').pack(anchor='w')
        ttk.Entry(details, textvariable=self.platform_var, state='readonly').pack(fill='x')
        ttk.Label(details, text='Username').pack(anchor='w', pady=(8,0))
        ttk.Entry(details, textvariable=self.username_var, state='readonly').pack(fill='x')
        ttk.Label(details, text='Note').pack(anchor='w', pady=(8,0))
        ttk.Entry(details, textvariable=self.note_var, state='readonly').pack(fill='x')

        action_frame = ttk.Frame(right)
        action_frame.pack(fill='x', pady=12)
        ttk.Button(action_frame, text='Show password', style='Accent.TButton', command=self._show_password).pack(side='left')
        ttk.Button(action_frame, text='Run local web UI', command=self._run_web_ui).pack(side='left', padx=8)
        ttk.Button(action_frame, text='Export to HTML', command=self._export_html).pack(side='left', padx=8)

    def _check_for_updates(self):
        try:
            accounts = self.vault.list_accounts()
            new_hash = json.dumps(accounts)
            if new_hash != self._accounts_hash:
                self._accounts_hash = new_hash
                self._refresh_list()
        except Exception as e:
            print(f"Error checking for updates: {e}")
        finally:
            self.root.after(2000, self._check_for_updates)

    def _refresh_list(self, *_):
        query = self.search_var.get().lower()
        self.accounts_list.delete(0, 'end')
        self._accounts = self.vault.list_accounts()
        self._accounts_hash = json.dumps(self._accounts)
        for a in self._accounts:
            label = f"{a['platform']} — {a['username']}"
            if query and query not in label.lower():
                continue
            self.accounts_list.insert('end', label)

    def _on_select(self):
        idx = self.accounts_list.curselection()
        if not idx:
            return
        i = idx[0]
        rec = self._accounts[i]
        self.platform_var.set(rec['platform'])
        self.username_var.set(rec['username'])
        self.note_var.set(rec.get('note') or '')
        self._selected_id = rec['id']

    def _migrate_data(self):
        path = filedialog.askopenfilename(
            title="Select old JSON file to migrate",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return

        modal = Toplevel(self.root)
        modal.title('Migrating...')
        modal.geometry('360x120')
        modal.transient(self.root)
        ttk.Label(modal, text='Reading migration file...').pack(pady=8)
        pb = ttk.Progressbar(modal, mode='determinate', maximum=100)
        pb.pack(fill='x', padx=12, pady=6)
        progress_var = StringVar()
        ttk.Label(modal, textvariable=progress_var).pack(pady=4)

        def do_migration():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data_to_migrate = json.load(f)
                
                total = len(data_to_migrate)
                pb['maximum'] = total

                existing_accounts = self.vault.list_accounts()
                existing_set = {(acc['platform'], acc['username']) for acc in existing_accounts}
                
                added_count = 0
                skipped_count = 0

                for i, (platform, details) in enumerate(data_to_migrate.items()):
                    progress_var.set(f'Processing {i+1}/{total}')
                    pb['value'] = i + 1

                    username = details.get('username')
                    password = details.get('password')

                    if not (username and password):
                        skipped_count += 1
                        continue

                    if (platform, username) in existing_set:
                        skipped_count += 1
                        continue
                    
                    # Convert timestamp if it exists
                    created_at_iso = None
                    if 'timestamp' in details:
                        try:
                            # Old format: "2024-08-08 14:38:04"
                            dt_obj = datetime.strptime(details['timestamp'], '%Y-%m-%d %H:%M:%S')
                            created_at_iso = dt_obj.isoformat()
                        except (ValueError, TypeError):
                            pass # Ignore invalid timestamps

                    self.vault.add_account(
                        platform=platform,
                        username=username,
                        password=password,
                        created_at=created_at_iso
                    )
                    added_count += 1
                
                modal.destroy()
                summary = f"Migration complete.\nAdded: {added_count}\nSkipped (duplicates/invalid): {skipped_count}."
                messagebox.showinfo("Migration Complete", summary)
                self._refresh_list()

            except Exception as e:
                modal.destroy()
                messagebox.showerror("Migration Failed", f'An error occurred: {e}')

        threading.Thread(target=do_migration, daemon=True).start()

    def _import_html(self):
        path = filedialog.askopenfilename(
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")]
        )
        if not path:
            return

        modal = Toplevel(self.root)
        modal.title('Importing...')
        modal.geometry('360x120')
        modal.transient(self.root)
        ttk.Label(modal, text='Reading import file...').pack(pady=8)
        pb = ttk.Progressbar(modal, mode='determinate', maximum=100)
        pb.pack(fill='x', padx=12, pady=6)
        progress_var = StringVar()
        ttk.Label(modal, textvariable=progress_var).pack(pady=4)

        def do_import():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    html_content = f.read()

                match = re.search(r'const accounts = (.*?);', html_content, re.DOTALL)
                if not match:
                    modal.destroy()
                    messagebox.showerror("Error", "Could not find account data in the file.")
                    return

                json_data = match.group(1)
                imported_accounts = json.loads(json_data)
                total = len(imported_accounts)
                pb['maximum'] = total

                existing_accounts = self.vault.list_accounts()
                existing_set = {(acc['platform'], acc['username']) for acc in existing_accounts}
                
                added_count = 0
                skipped_count = 0

                for i, acc in enumerate(imported_accounts):
                    progress_var.set(f'Processing {i+1}/{total}')
                    pb['value'] = i + 1

                    if (acc['platform'], acc['username']) in existing_set:
                        skipped_count += 1
                        continue
                    
                    self.vault.add_account(
                        platform=acc['platform'],
                        username=acc['username'],
                        password=acc['password'],
                        note=acc.get('note', '')
                    )
                    added_count += 1
                
                modal.destroy()
                summary = f"Import complete.\nAdded: {added_count}\nSkipped (duplicates): {skipped_count}."
                messagebox.showinfo("Import Complete", summary)
                self._refresh_list()

            except Exception as e:
                modal.destroy()
                messagebox.showerror("Import Failed", f'An error occurred: {e}')

        threading.Thread(target=do_import, daemon=True).start()

    def _add_entry(self):
        dlg = EntryDialog(self.root, "Add entry")
        if dlg.result:
            platform, username, password, note = dlg.result
            self.vault.add_account(platform, username, password, note)
            self._refresh_list()

    def _edit_entry(self):
        if not hasattr(self, '_selected_id'):
            messagebox.showinfo('Info', 'Select an entry first')
            return
        rec = self.vault.get_account(self._selected_id)
        dlg = EntryDialog(self.root, "Edit entry", (rec['platform'], rec['username'], None, rec.get('note') or ''))
        if dlg.result:
            print("_edit_entry", dlg.result)
            platform, username, password, note = dlg.result
            # if password is None (user left blank), keep existing
            self.vault.update_account(self._selected_id, platform, username, password, note)
            self._refresh_list()

    def _delete_entry(self):
        if not hasattr(self, '_selected_id'):
            messagebox.showinfo('Info', 'Select an entry first')
            return
        if messagebox.askyesno('Confirm', 'Delete selected entry?'):
            self.vault.delete_account(self._selected_id)
            self._refresh_list()

    def _show_password(self):
        if not hasattr(self, '_selected_id'):
            messagebox.showinfo('Info', 'Select an entry first')
            return
        # show a modal with a progress bar, then reveal password
        modal = Toplevel(self.root)
        modal.title('Decrypting...')
        modal.geometry('360x120')
        modal.transient(self.root)
        ttk.Label(modal, text='Decrypting password...').pack(pady=8)
        pb = ttk.Progressbar(modal, mode='indeterminate')
        pb.pack(fill='x', padx=12, pady=6)
        pb.start(10)

        def do_decrypt():
            try:
                # simulate a short delay for UI effect
                time.sleep(0.6)
                pw = self.vault.decrypt_password(self._selected_id)
                pb.stop()
                modal.destroy()
                # show result in a simple dialog
                messagebox.showinfo('Password', f'Password: {pw}')
            except Exception as e:
                pb.stop()
                modal.destroy()
                messagebox.showerror('Error', str(e))

        threading.Thread(target=do_decrypt, daemon=True).start()

    def _run_web_ui(self):
        if self.flask_thread and self.flask_thread.is_alive():
            messagebox.showinfo('Info', 'Web UI already running at http://127.0.0.1:5000')
            return
        self.flask_app = create_flask_app(self.vault)

        def run_app():
            # only bind to localhost for safety
            self.flask_app.run(host='127.0.0.1', port=5000, debug=False, threaded=True, use_reloader=False)

        def wait_for_port(host, port, timeout=5.0):
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    with socket.create_connection((host, port), timeout=0.5):
                        return True
                except OSError:
                    time.sleep(0.1)
            return False

        self.flask_thread = threading.Thread(target=run_app, daemon=True)
        self.flask_thread.start()

        if wait_for_port('127.0.0.1', 5000, timeout=5.0):
            webbrowser.open_new_tab('http://127.0.0.1:5000')
            messagebox.showinfo('Web UI', 'Web UI launched at http://127.0.0.1:5000')
        else:
            messagebox.showwarning('Web UI', '서버 시작에 실패했거나 포트가 열리지 않았습니다.')

    def _export_html(self):
        modal = Toplevel(self.root)
        modal.title('Exporting...')
        modal.geometry('360x120')
        modal.transient(self.root)
        ttk.Label(modal, text='Preparing export file...').pack(pady=8)
        pb = ttk.Progressbar(modal, mode='determinate', maximum=100)
        pb.pack(fill='x', padx=12, pady=6)
        progress_var = StringVar()
        ttk.Label(modal, textvariable=progress_var).pack(pady=4)

        def do_export():
            try:
                accounts = self.vault.list_accounts()
                total = len(accounts)
                pb['maximum'] = total
                
                accounts_with_passwords = []
                progress_var.set(f'Decrypting 0/{total}')

                for i, acc in enumerate(accounts):
                    try:
                        password = self.vault.decrypt_password(acc['id'])
                        acc['password'] = password
                        accounts_with_passwords.append(acc)
                    except Exception:
                        continue # Skip if a password fails
                    finally:
                        pb['value'] = i + 1
                        progress_var.set(f'Decrypting {i+1}/{total}')
                
                # Manually render the template
                template_path = resource_path(os.path.join('templates', 'export_template.html'))
                with open(template_path, 'r', encoding='utf-8') as f:
                    template_str = f.read()

                generation_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                rendered_html = template_str.replace('{{ accounts_json | safe }}', json.dumps(accounts_with_passwords))
                rendered_html = rendered_html.replace('{{ generation_date }}', generation_date)

                modal.destroy()

                save_path = filedialog.asksaveasfilename(
                    defaultextension=".html",
                    filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
                    title="Save Vault Export"
                )
                
                if save_path:
                    with open(save_path, 'w', encoding='utf-8') as f:
                        f.write(rendered_html)
                    messagebox.showinfo('Success', f'Vault exported successfully to {save_path}')

            except Exception as e:
                modal.destroy()
                messagebox.showerror('Export Failed', f'An error occurred: {e}')

        threading.Thread(target=do_export, daemon=True).start()


    def run(self):
        self.root.mainloop()


class EntryDialog(simpledialog.Dialog):
    def __init__(self, parent, title, initial=None):
        self.initial = initial
        super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text='Platform').grid(row=0, column=0, sticky='w')
        self.platform_e = ttk.Entry(master)
        self.platform_e.grid(row=0, column=1, sticky='ew')
        ttk.Label(master, text='Username').grid(row=1, column=0, sticky='w')
        self.user_e = ttk.Entry(master)
        self.user_e.grid(row=1, column=1, sticky='ew')
        ttk.Label(master, text='Password (leave blank to keep existing)').grid(row=2, column=0, sticky='w')
        self.pw_e = ttk.Entry(master, show='*')
        self.pw_e.grid(row=2, column=1, sticky='ew')
        ttk.Label(master, text='Note').grid(row=3, column=0, sticky='w')
        self.note_e = ttk.Entry(master)
        self.note_e.grid(row=3, column=1, sticky='ew')
        if self.initial:
            self.platform_e.insert(0, self.initial[0])
            self.user_e.insert(0, self.initial[1])
            # password left blank intentionally
            self.note_e.insert(0, self.initial[3])
        return self.platform_e

    def apply(self):
        pw = self.pw_e.get().strip() or None
        self.result = (self.platform_e.get(), self.user_e.get(), pw, self.note_e.get())
        
# --------------------------- Flask web UI --------------------------


def create_flask_app(vault: Vault):
    # Get the directory where this script is located
    template_folder = resource_path('templates')
    
    app = Flask(__name__, template_folder=template_folder)
    
    # Add logging
    import logging
    logging.basicConfig(level=logging.INFO)
    
    @app.route('/')
    def index():
        return render_template('index.html', bootstrap_cdn=BOOTSTRAP_CDN)

    @app.route('/api/ping', methods=['GET', 'POST'])
    def api_ping():
        """Health check endpoint"""
        return jsonify({'status': 'ok', 'message': 'Server is running'})

    @app.route('/api/list')
    def api_list():
        try:
            accounts = vault.list_accounts()
            app.logger.info(f"Returning {len(accounts)} accounts")
            return jsonify(accounts)
        except Exception as e:
            app.logger.error(f"Error in /api/list: {e}")
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/decrypt', methods=['POST'])
    def api_decrypt():
        id_ = request.args.get('id', type=int)
        if id_ is None:
            app.logger.error("Missing id parameter")
            return jsonify({'error': 'Missing id parameter'}), 400
        try:
            # Add a small delay for visual feedback
            time.sleep(0.3)
            # decrypt -- this uses the in-memory master password
            pw = vault.decrypt_password(id_)
            app.logger.info(f"Successfully decrypted password for id {id_}")
            return jsonify({'password': pw})
        except VaultError as e:
            app.logger.error(f"Vault error for id {id_}: {e}")
            return jsonify({'error': str(e)}), 404
        except Exception as e:
            app.logger.error(f"Error decrypting password for id {id_}: {e}")
            traceback.print_exc()
            return jsonify({'error': 'Decryption failed'}), 500

    @app.route('/api/add', methods=['POST'])
    def api_add():
        data = request.json
        if not data or not all(k in data for k in ['platform', 'username', 'password']):
            app.logger.error("Missing fields in add request")
            return jsonify({'error': 'Missing required fields: platform, username, password'}), 400
        try:
            new_id = vault.add_account(
                platform=data['platform'],
                username=data['username'],
                password=data['password'],
                note=data.get('note', '')
            )
            app.logger.info(f"Added new account with id {new_id}")
            return jsonify({'status': 'ok', 'id': new_id}), 201
        except Exception as e:
            app.logger.error(f"Error in /api/add: {e}")
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/edit/<int:id_>', methods=['POST'])
    def api_edit(id_):
        data = request.json
        if not data or not all(k in data for k in ['platform', 'username']):
            app.logger.error(f"Missing fields in edit request for id {id_}")
            return jsonify({'error': 'Missing required fields: platform, username'}), 400
        try:
            password = data.get('password')
            if not password or not password.strip(): # If password is empty, None, or just whitespace
                password = None  # keep existing

            vault.update_account(
                id_=id_,
                platform=data['platform'],
                username=data['username'],
                password=password,
                note=data.get('note', '')
            )
            app.logger.info(f"Updated account id {id_}")
            return jsonify({'status': 'ok'})
        except Exception as e:
            app.logger.error(f"Error in /api/edit/{id_}: {e}")
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/delete/<int:id_>', methods=['POST'])
    def api_delete(id_):
        try:
            vault.delete_account(id_)
            app.logger.info(f"Deleted account id {id_}")
            return jsonify({'status': 'ok'})
        except Exception as e:
            app.logger.error(f"Error in /api/delete/{id_}: {e}")
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/export')
    def api_export():
        try:
            accounts = vault.list_accounts()
            accounts_with_passwords = []
            for acc in accounts:
                try:
                    password = vault.decrypt_password(acc['id'])
                    acc['password'] = password
                    accounts_with_passwords.append(acc)
                except Exception:
                    app.logger.error(f"Could not decrypt password for account id {acc['id']} during export.")
                    continue
            
            generation_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            return render_template('export_template.html', accounts_json=json.dumps(accounts_with_passwords), generation_date=generation_date)
        except Exception as e:
            app.logger.error(f"Error in /api/export: {e}")
            traceback.print_exc()
            return "Error generating export file.", 500

    @app.route('/api/import', methods=['POST'])
    def api_import():
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        try:
            html_content = file.read().decode('utf-8')
            
            match = re.search(r'const accounts = (.*?);', html_content, re.DOTALL)
            if not match:
                return jsonify({'error': 'Could not find account data in the file.'}), 400
            
            json_data = match.group(1)
            imported_accounts = json.loads(json_data)

            # Check for duplicates
            existing_accounts = vault.list_accounts()
            existing_set = {(acc['platform'], acc['username']) for acc in existing_accounts}
            
            added_count = 0
            skipped_count = 0

            for acc in imported_accounts:
                if (acc['platform'], acc['username']) in existing_set:
                    skipped_count += 1
                    continue
                
                vault.add_account(
                    platform=acc['platform'],
                    username=acc['username'],
                    password=acc['password'], # Password in export is already plaintext
                    note=acc.get('note', '')
                )
                added_count += 1
            
            summary = f"Import complete. Added: {added_count}, Skipped (duplicates): {skipped_count}."
            app.logger.info(summary)
            return jsonify({'status': 'ok', 'message': summary})

        except Exception as e:
            app.logger.error(f"Error in /api/import: {e}")
            traceback.print_exc()
            return jsonify({'error': 'An error occurred during import.'}), 500

    return app

# --------------------------- Main ---------------------------

def prompt_master():
    root = Tk()
    root.withdraw()
    mp = simpledialog.askstring('Master password', 'Enter master password for the vault:', show='*', parent=root)
    root.destroy()
    if not mp:
        print('Master password required. Exiting.')
        sys.exit(1)
    return mp

if __name__ == '__main__':
    vault = None
    cacher = PasswordCacher()

    # Try cached password first
    cached_mp = cacher.get_cached_password()
    if cached_mp:
        try:
            print("Attempting login with cached password...")
            v = Vault(cached_mp)
            v.list_accounts() # Verify password by trying to read data
            vault = v
            print("Successfully logged in with cached password.")
        except Exception as e:
            print(f"Cached password was invalid, deleting cache. Reason: {e}")
            if os.path.exists(CACHE_FILE):
                os.remove(CACHE_FILE)
    
    # If no vault yet, prompt user
    if not vault:
        mp = prompt_master()
        if not mp:
            # User cancelled password prompt
            sys.exit(1)
        
        try:
            vault = Vault(mp)
            vault.list_accounts() # Verify password
            
            # If successful, cache the password automatically
            if cacher.fernet: # Check if caching is supported
                cacher.cache_password(mp)

        except Exception as e:
            root = Tk()
            root.withdraw()
            messagebox.showerror("Login Failed", f"Failed to open vault. The password may be incorrect or the database is corrupt.\n\nError: {e}")
            root.destroy()
            sys.exit(1)

    if not vault:
        print("Could not initialize vault. Exiting.")
        sys.exit(1)

    gui = VaultGUI(vault)
    gui.run()
