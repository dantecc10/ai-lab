#!/usr/bin/env python3
"""
AI Lab — GitHub Permanent Activity & Actions Monitor Daemon
Monitorea continuamente repositorios propios, compartidos y de organizaciones colaboradoras.
Detecta en tiempo real:
  - Nuevos commits y pushes de colaboradores.
  - Estado de ejecuciones de GitHub Actions (CI/CD: builds exitosos, fallos, cancelaciones).
  - Pull Requests, Issues y Revisiones de código.
  - Notificaciones de la bandeja de entrada de GitHub.
Envía notificaciones visuales nativas en el escritorio mediante notify-send y registra todo en SQLite.
"""

import os
import sys
import time
import json
import sqlite3
import argparse
import logging
import subprocess
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# Rutas del sistema
DATA_DIR = Path.home() / ".local" / "share" / "ai-lab"
DB_PATH = DATA_DIR / "github_monitor.db"
LOG_PATH = DATA_DIR / "github_monitor.log"

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("GitHubMonitor")


class GitHubClient:
    """Cliente HTTP optimizado para GitHub REST API utilizando token de GitHub CLI."""

    def __init__(self):
        self.token = self._get_token()
        self.base_url = "https://api.github.com"

    def _get_token(self) -> str:
        """Obtiene el token de autenticación desde el keyring de gh cli o variable de entorno."""
        env_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if env_token:
            return env_token.strip()

        try:
            res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception as e:
            logger.warning(f"No se pudo obtener token de 'gh auth token': {e}")
        return ""

    def request(self, endpoint: str, params: Optional[Dict[str, Any]] = None, etag: Optional[str] = None) -> Tuple[int, Any, Dict[str, str]]:
        """Realiza una petición a la API de GitHub."""
        url = f"{self.base_url}{endpoint}"
        if params:
            query = "&".join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()])
            url = f"{url}?{query}"

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-Lab-GitHub-Monitor/2.0 (Pop_OS/Linux)"
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if etag:
            headers["If-None-Match"] = etag

        req = urllib.request.Request(url, headers=headers, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                status = response.status
                resp_headers = dict(response.headers)
                body = response.read().decode("utf-8")
                data = json.loads(body) if body else None
                return status, data, resp_headers
        except urllib.error.HTTPError as e:
            resp_headers = dict(e.headers)
            if e.code == 304:
                return 304, None, resp_headers
            body = e.read().decode("utf-8", errors="ignore")
            try:
                data = json.loads(body)
            except Exception:
                data = {"message": body}
            return e.code, data, resp_headers
        except Exception as e:
            logger.error(f"Error de red al consultar {endpoint}: {e}")
            return 500, {"error": str(e)}, {}


class GitHubMonitor:
    """Motor central de auditoría y monitoreo permanente de GitHub."""

    def __init__(self, check_interval_sec: int = 60):
        self.interval = check_interval_sec
        self.client = GitHubClient()
        self.running = False
        self._init_db()

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(DB_PATH), timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Inicializa las tablas de seguimiento en SQLite."""
        with self._get_db() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS watched_repos (
                repo_name TEXT PRIMARY KEY,       -- e.g. 'dantecc10/ai-lab'
                owner TEXT NOT NULL,
                name TEXT NOT NULL,
                is_owner INTEGER DEFAULT 0,
                is_custom INTEGER DEFAULT 0,
                permissions TEXT,
                last_pushed_at TEXT,
                last_checked_at TEXT,
                is_active INTEGER DEFAULT 1,
                etag_commits TEXT,
                etag_runs TEXT
            );

            CREATE TABLE IF NOT EXISTS seen_commits (
                sha TEXT PRIMARY KEY,
                repo_name TEXT NOT NULL,
                branch TEXT,
                author_name TEXT,
                author_login TEXT,
                message TEXT,
                committed_at TEXT,
                notified_at TEXT
            );

            CREATE TABLE IF NOT EXISTS seen_workflow_runs (
                run_id INTEGER PRIMARY KEY,
                repo_name TEXT NOT NULL,
                workflow_name TEXT,
                run_number INTEGER,
                event TEXT,
                head_branch TEXT,
                head_sha TEXT,
                status TEXT,
                conclusion TEXT,
                actor TEXT,
                html_url TEXT,
                updated_at TEXT,
                notified_at TEXT
            );

            CREATE TABLE IF NOT EXISTS seen_notifications (
                notification_id TEXT PRIMARY KEY,
                repo_name TEXT,
                reason TEXT,
                subject_type TEXT,
                subject_title TEXT,
                subject_url TEXT,
                unread INTEGER DEFAULT 1,
                updated_at TEXT,
                notified_at TEXT
            );

            CREATE TABLE IF NOT EXISTS notification_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL,          -- 'commit', 'action_failed', 'action_success', 'pr', 'notification'
                repo_name TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                urgency TEXT DEFAULT 'normal',
                status TEXT DEFAULT 'delivered'
            );
            """)
            conn.commit()

    def send_desktop_notification(self, title: str, body: str, urgency: str = "normal", icon: str = "software-update-available", event_type: str = "general", repo_name: str = ""):
        """Emite una notificación nativa en el escritorio de Pop!_OS / GNOME / COSMIC."""
        try:
            cmd = [
                "notify-send",
                "-a", "AI Lab GitHub Monitor",
                "-u", urgency,
                "-t", "8000" if urgency == "critical" else "5000",
                "-i", icon,
                title,
                body
            ]
            subprocess.run(cmd, check=False, timeout=5)
            logger.info(f"🔔 [Notificación Desktop] ({urgency.upper()}) {title} — {body}")

            with self._get_db() as conn:
                conn.execute("""
                INSERT INTO notification_history (event_type, repo_name, title, message, urgency)
                VALUES (?, ?, ?, ?, ?)
                """, (event_type, repo_name, title, body, urgency))
                conn.commit()

        except Exception as e:
            logger.error(f"Error al enviar notificación de escritorio: {e}")

    def sync_repositories(self):
        """Descubre automáticamente todos los repositorios accesibles (propios, organizaciones y colaboraciones)."""
        logger.info("🔄 Sincronizando catálogo de repositorios accesibles en GitHub...")
        status, repos, _ = self.client.request(
            "/user/repos",
            params={
                "affiliation": "owner,collaborator,organization_member",
                "sort": "pushed",
                "per_page": 100
            }
        )

        if status != 200 or not isinstance(repos, list):
            logger.warning(f"No se pudieron sincronizar repositorios (HTTP {status}): {repos}")
            return

        with self._get_db() as conn:
            for r in repos:
                full_name = r.get("full_name")
                if not full_name:
                    continue
                owner = r.get("owner", {}).get("login", "")
                name = r.get("name", "")
                is_owner = 1 if owner.lower() == "dantecc10" else 0
                pushed_at = r.get("pushed_at", "")
                perms_str = json.dumps(r.get("permissions", {}))

                conn.execute("""
                INSERT INTO watched_repos (repo_name, owner, name, is_owner, permissions, last_pushed_at, last_checked_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'), 1)
                ON CONFLICT(repo_name) DO UPDATE SET
                    permissions = excluded.permissions,
                    last_pushed_at = excluded.last_pushed_at
                """, (full_name, owner, name, is_owner, perms_str, pushed_at))
            conn.commit()

        logger.info(f"✅ Catálogo de repositorios actualizado ({len(repos)} repositorios activos).")

    def watch_repository(self, repo_name: str) -> str:
        """Agrega un repositorio específico a la lista de monitoreo activo."""
        repo_name = repo_name.strip()
        status, data, _ = self.client.request(f"/repos/{repo_name}")
        if status != 200:
            return f"Error: No se encontró el repositorio '{repo_name}' o no tienes acceso (HTTP {status})."

        owner = data.get("owner", {}).get("login", "")
        name = data.get("name", "")
        is_owner = 1 if owner.lower() == "dantecc10" else 0
        pushed_at = data.get("pushed_at", "")

        with self._get_db() as conn:
            conn.execute("""
            INSERT INTO watched_repos (repo_name, owner, name, is_owner, is_custom, last_pushed_at, is_active)
            VALUES (?, ?, ?, ?, 1, ?, 1)
            ON CONFLICT(repo_name) DO UPDATE SET is_active = 1, is_custom = 1, last_pushed_at = excluded.last_pushed_at
            """, (repo_name, owner, name, is_owner, pushed_at))
            conn.commit()

        return f"Repositorio '{repo_name}' agregado exitosamente al monitoreo permanente."

    def unwatch_repository(self, repo_name: str) -> str:
        """Desactiva el monitoreo de un repositorio."""
        repo_name = repo_name.strip()
        with self._get_db() as conn:
            cur = conn.execute("UPDATE watched_repos SET is_active = 0 WHERE repo_name = ?", (repo_name,))
            conn.commit()
            if cur.rowcount > 0:
                return f"Monitoreo desactivado para '{repo_name}'."
            return f"El repositorio '{repo_name}' no estaba registrado."

    def check_github_notifications(self):
        """Revisa la bandeja de notificaciones oficial de GitHub (/notifications)."""
        status, notifications, _ = self.client.request("/notifications", params={"all": "false"})
        if status != 200 or not isinstance(notifications, list):
            return

        with self._get_db() as conn:
            cur = conn.execute("SELECT COUNT(*) as count FROM seen_notifications")
            is_initial_run = (cur.fetchone()["count"] == 0)

            for notif in notifications:
                notif_id = str(notif.get("id"))
                repo_full = notif.get("repository", {}).get("full_name", "")
                reason = notif.get("reason", "")
                subject = notif.get("subject", {})
                title = subject.get("title", "")
                subtype = subject.get("type", "")
                subject_url = subject.get("url", "")
                updated_at = notif.get("updated_at", "")

                if subtype == "CheckSuite" and reason == "ci_activity":
                    conn.execute("""
                    INSERT OR IGNORE INTO seen_notifications (notification_id, repo_name, reason, subject_type, subject_title, subject_url, unread, updated_at, notified_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?, datetime('now'))
                    """, (notif_id, repo_full, reason, subtype, title, subject_url, updated_at))
                    continue

                exists = conn.execute("SELECT notification_id FROM seen_notifications WHERE notification_id = ?", (notif_id,)).fetchone()
                if not exists:
                    now_str = datetime.now().isoformat()
                    conn.execute("""
                    INSERT INTO seen_notifications (notification_id, repo_name, reason, subject_type, subject_title, subject_url, unread, updated_at, notified_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """, (notif_id, repo_full, reason, subtype, title, subject_url, updated_at, None if is_initial_run else now_str))

                    if not is_initial_run:
                        urgency = "normal"
                        icon = "mail-unread"
                        if reason in ["mention", "author", "assign"]:
                            urgency = "normal"
                            icon = "avatar-default"
                        elif reason == "review_requested":
                            urgency = "critical"
                            icon = "dialog-question"

                        header = f"📬 GitHub [{subtype}]: {repo_full}"
                        body = f"Motivo: {reason}\n{title}"
                        self.send_desktop_notification(header, body, urgency=urgency, icon=icon, event_type="notification", repo_name=repo_full)
            conn.commit()

    def check_repository_commits(self, repo_name: str):
        """Verifica si hay nuevos commits en un repositorio específico."""
        status, commits, _ = self.client.request(f"/repos/{repo_name}/commits", params={"per_page": 5})
        if status != 200 or not isinstance(commits, list):
            return

        with self._get_db() as conn:
            cur = conn.execute("SELECT COUNT(*) as count FROM seen_commits WHERE repo_name = ?", (repo_name,))
            is_initial_run = (cur.fetchone()["count"] == 0)

            new_commits = []
            for c in commits:
                sha = c.get("sha", "")
                commit_info = c.get("commit", {})
                author_info = c.get("author") or {}
                author_name = commit_info.get("author", {}).get("name", "Desconocido")
                author_login = author_info.get("login", author_name)
                message = commit_info.get("message", "").strip().split("\n")[0]
                committed_at = commit_info.get("author", {}).get("date", "")

                exists = conn.execute("SELECT sha FROM seen_commits WHERE sha = ?", (sha,)).fetchone()
                if not exists:
                    now_str = datetime.now().isoformat()
                    conn.execute("""
                    INSERT INTO seen_commits (sha, repo_name, branch, author_name, author_login, message, committed_at, notified_at)
                    VALUES (?, ?, 'main', ?, ?, ?, ?, ?)
                    """, (sha, repo_name, author_name, author_login, message, committed_at, None if is_initial_run else now_str))
                    if not is_initial_run:
                        new_commits.append({
                            "sha": sha[:7],
                            "author": author_login or author_name,
                            "message": message
                        })
            conn.commit()

            if new_commits:
                if len(new_commits) == 1:
                    c = new_commits[0]
                    title = f"🚀 Nuevo Commit en {repo_name}"
                    body = f"👤 {c['author']} ({c['sha']}):\n{c['message']}"
                else:
                    first = new_commits[0]
                    title = f"🚀 {len(new_commits)} Nuevos Commits en {repo_name}"
                    body = f"👤 Último de {first['author']}: {first['message']}\n(+{len(new_commits)-1} commits adicionales)"

                self.send_desktop_notification(title, body, urgency="normal", icon="git", event_type="commit", repo_name=repo_name)

    def check_repository_actions(self, repo_name: str):
        """Verifica el estado de ejecuciones de GitHub Actions (Builds, Tests, Deployments)."""
        status, data, _ = self.client.request(f"/repos/{repo_name}/actions/runs", params={"per_page": 8})
        if status != 200 or not isinstance(data, dict):
            return

        runs = data.get("workflow_runs", [])
        if not isinstance(runs, list):
            return

        with self._get_db() as conn:
            cur = conn.execute("SELECT COUNT(*) as count FROM seen_workflow_runs WHERE repo_name = ?", (repo_name,))
            is_initial_run = (cur.fetchone()["count"] == 0)

            for run in runs:
                run_id = run.get("id")
                workflow_name = run.get("name", "Workflow")
                run_number = run.get("run_number", 0)
                event = run.get("event", "push")
                head_branch = run.get("head_branch", "main")
                head_sha = (run.get("head_sha") or "")[:7]
                run_status = run.get("status", "")
                conclusion = run.get("conclusion") or ""
                actor = run.get("actor", {}).get("login", "Desconocido")
                html_url = run.get("html_url", "")
                updated_at = run.get("updated_at", "")

                row = conn.execute("SELECT status, conclusion, notified_at FROM seen_workflow_runs WHERE run_id = ?", (run_id,)).fetchone()

                now_str = datetime.now().isoformat()
                if not row:
                    conn.execute("""
                    INSERT INTO seen_workflow_runs (run_id, repo_name, workflow_name, run_number, event, head_branch, head_sha, status, conclusion, actor, html_url, updated_at, notified_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (run_id, repo_name, workflow_name, run_number, event, head_branch, head_sha, run_status, conclusion, actor, html_url, updated_at, None if is_initial_run else now_str))

                    if not is_initial_run and run_status == "completed":
                        self._notify_action_result(repo_name, workflow_name, run_number, head_branch, head_sha, conclusion, actor, event)
                else:
                    prev_status = row["status"]
                    prev_conclusion = row["conclusion"]
                    if prev_status != "completed" and run_status == "completed":
                        conn.execute("""
                        UPDATE seen_workflow_runs
                        SET status = ?, conclusion = ?, updated_at = ?, notified_at = ?
                        WHERE run_id = ?
                        """, (run_status, conclusion, updated_at, now_str, run_id))
                        self._notify_action_result(repo_name, workflow_name, run_number, head_branch, head_sha, conclusion, actor, event)
            conn.commit()

    def _notify_action_result(self, repo_name: str, workflow_name: str, run_number: int, branch: str, sha: str, conclusion: str, actor: str, event: str):
        """Despacha la notificación correspondiente al resultado de un flujo de CI/CD."""
        if conclusion == "success":
            title = f"✅ CI Exitoso: {repo_name}"
            body = f"Workflow: '{workflow_name}' (#{run_number})\nRama: {branch} ({sha}) • Autor: {actor}"
            self.send_desktop_notification(title, body, urgency="normal", icon="emblem-default", event_type="action_success", repo_name=repo_name)
        elif conclusion == "failure":
            title = f"❌ CI Falló: {repo_name}"
            body = f"Workflow: '{workflow_name}' (#{run_number})\nRama: {branch} ({sha}) • Disparado por: {actor} ({event})"
            self.send_desktop_notification(title, body, urgency="critical", icon="dialog-error", event_type="action_failed", repo_name=repo_name)
        elif conclusion == "cancelled":
            title = f"⚠️ CI Cancelado: {repo_name}"
            body = f"Workflow: '{workflow_name}' (#{run_number}) en {branch}"
            self.send_desktop_notification(title, body, urgency="low", icon="dialog-warning", event_type="action_cancelled", repo_name=repo_name)

    def get_active_priority_repos(self, limit: int = 25) -> List[sqlite3.Row]:
        """Selecciona los repositorios activos prioritarios (custom o con actividad reciente)."""
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        with self._get_db() as conn:
            return conn.execute("""
            SELECT repo_name, is_owner, is_custom, last_pushed_at
            FROM watched_repos
            WHERE is_active = 1 AND (is_custom = 1 OR last_pushed_at >= ? OR repo_name LIKE 'dantecc10/%' OR repo_name LIKE 'brigadadigitalmorena/%')
            ORDER BY is_custom DESC, last_pushed_at DESC
            LIMIT ?
            """, (cutoff_date, limit)).fetchall()

    def _audit_single_repo(self, repo_name: str):
        """Audita un único repositorio (commits + actions)."""
        try:
            self.check_repository_commits(repo_name)
            self.check_repository_actions(repo_name)
            with self._get_db() as conn:
                conn.execute("UPDATE watched_repos SET last_checked_at = datetime('now') WHERE repo_name = ?", (repo_name,))
                conn.commit()
        except Exception as e:
            logger.error(f"Error auditando {repo_name}: {e}")

    def run_check_cycle(self):
        """Ejecuta una ronda de verificación concurrente sobre la bandeja y los repositorios prioritarios."""
        try:
            self.check_github_notifications()
        except Exception as e:
            logger.error(f"Error revisando notificaciones generales: {e}")

        repos = self.get_active_priority_repos(limit=30)
        repo_names = [r["repo_name"] for r in repos]

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(self._audit_single_repo, name): name for name in repo_names}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Excepción en hilo de auditoría para {futures[future]}: {e}")

        logger.info(f"🏁 Ciclo de monitoreo completado ({len(repo_names)} repos prioritarios auditados en paralelo).")

    def run_daemon(self):
        """Bucle infinito del servicio en segundo plano."""
        self.running = True
        logger.info(f"🚀 Iniciando GitHub Monitor Daemon (intervalo: {self.interval}s)...")
        self.send_desktop_notification(
            "🛰️ AI Lab GitHub Monitor Activo",
            f"Monitoreando repositorios propios, organizaciones y GitHub Actions cada {self.interval}s.",
            urgency="low",
            icon="dialog-information",
            event_type="daemon_start"
        )

        # Sincronización inicial de repositorios
        self.sync_repositories()

        # Primer ciclo
        self.run_check_cycle()

        cycle_count = 0
        while self.running:
            try:
                time.sleep(self.interval)
                cycle_count += 1

                # Re-sincronizar catálogo de repositorios cada 15 minutos (15 ciclos de 60s)
                if cycle_count % 15 == 0:
                    self.sync_repositories()

                self.run_check_cycle()
            except KeyboardInterrupt:
                logger.info("Detención solicitada por el usuario.")
                self.running = False
                break
            except Exception as e:
                logger.error(f"Error inesperado en ciclo del daemon: {e}")
                time.sleep(10)

    def get_status_report(self) -> Dict[str, Any]:
        """Genera un reporte detallado del estado del monitor para CLI o MCP."""
        with self._get_db() as conn:
            watched_count = conn.execute("SELECT COUNT(*) as c FROM watched_repos WHERE is_active = 1").fetchone()["c"]
            commits_count = conn.execute("SELECT COUNT(*) as c FROM seen_commits").fetchone()["c"]
            runs_count = conn.execute("SELECT COUNT(*) as c FROM seen_workflow_runs").fetchone()["c"]
            notifs_count = conn.execute("SELECT COUNT(*) as c FROM notification_history").fetchone()["c"]

            recent_alerts = conn.execute("""
            SELECT timestamp, event_type, repo_name, title, message, urgency
            FROM notification_history
            ORDER BY id DESC LIMIT 10
            """).fetchall()

            recent_actions = conn.execute("""
            SELECT repo_name, workflow_name, run_number, status, conclusion, actor, updated_at
            FROM seen_workflow_runs
            ORDER BY run_id DESC LIMIT 10
            """).fetchall()

            active_repos = self.get_active_priority_repos(limit=30)

            return {
                "active_repositories_count": watched_count,
                "tracked_commits_count": commits_count,
                "tracked_workflow_runs_count": runs_count,
                "total_notifications_sent": notifs_count,
                "repositories": [dict(r) for r in active_repos],
                "recent_actions": [dict(a) for a in recent_actions],
                "recent_alerts": [dict(al) for al in recent_alerts]
            }


# ── Interfaz de Línea de Comandos ───────────────────────────
def main():
    parser = argparse.ArgumentParser(description="AI Lab GitHub Permanent Activity & Actions Monitor")
    parser.add_argument("--daemon", action="store_true", help="Ejecutar como servicio daemon en segundo plano")
    parser.add_argument("--check-now", action="store_true", help="Ejecutar una auditoría inmediata y mostrar resultados")
    parser.add_argument("--sync-repos", action="store_true", help="Descubrir y sincronizar catálogo de repositorios desde GitHub")
    parser.add_argument("--list", action="store_true", help="Listar todos los repositorios monitoreados")
    parser.add_argument("--status", action="store_true", help="Mostrar reporte general de telemetría y alertas recientes")
    parser.add_argument("--watch", type=str, metavar="OWNER/REPO", help="Agregar un repositorio específico al monitoreo permanente")
    parser.add_argument("--unwatch", type=str, metavar="OWNER/REPO", help="Desactivar monitoreo de un repositorio")
    parser.add_argument("--interval", type=int, default=60, help="Intervalo en segundos para el modo daemon (por defecto 60s)")

    args = parser.parse_args()
    monitor = GitHubMonitor(check_interval_sec=args.interval)

    if args.daemon:
        monitor.run_daemon()
    elif args.sync_repos:
        monitor.sync_repositories()
    elif args.check_now:
        monitor.sync_repositories()
        monitor.run_check_cycle()
        print("\n✅ Auditoría inmediata finalizada con éxito.")
    elif args.watch:
        res = monitor.watch_repository(args.watch)
        print(res)
    elif args.unwatch:
        res = monitor.unwatch_repository(args.unwatch)
        print(res)
    elif args.list:
        with monitor._get_db() as conn:
            rows = conn.execute("SELECT repo_name, is_owner, is_custom, last_pushed_at, last_checked_at FROM watched_repos WHERE is_active = 1 ORDER BY is_custom DESC, is_owner DESC, last_pushed_at DESC").fetchall()
            print(f"\n📂 Repositorios Monitoreados Activamente ({len(rows)}):")
            print("-" * 75)
            for r in rows:
                tag = "👑 Propio" if r["is_owner"] else ("📌 Custom" if r["is_custom"] else "👥 Colaboración / Org")
                print(f" • {r['repo_name']:<40} [{tag}] (Último push: {r['last_pushed_at'][:10] if r['last_pushed_at'] else 'N/A'})")
            print()
    elif args.status:
        report = monitor.get_status_report()
        print("\n" + "=" * 60)
        print("🛰️  REPORTE DE MONITOREO GITHUB — AI LAB")
        print("=" * 60)
        print(f" • Repositorios activos monitoreados: {report['active_repositories_count']}")
        print(f" • Commits registrados:               {report['tracked_commits_count']}")
        print(f" • Workflow Runs (Actions) auditados: {report['tracked_workflow_runs_count']}")
        print(f" • Notificaciones de escritorio:      {report['total_notifications_sent']}")
        print("\n🚀 Últimas Alertas de Escritorio:")
        if report["recent_alerts"]:
            for a in report["recent_alerts"][:5]:
                print(f"  [{a['timestamp']}] ({a['urgency'].upper()}) {a['title']} -> {a['message']}")
        else:
            print("  (Sin alertas recientes registradas)")
        print("\n⚡ Últimos Workflow Runs de GitHub Actions:")
        if report["recent_actions"]:
            for r in report["recent_actions"][:5]:
                status_icon = "✅" if r["conclusion"] == "success" else ("❌" if r["conclusion"] == "failure" else "⏳")
                print(f"  {status_icon} {r['repo_name']} | {r['workflow_name']} (#{r['run_number']}): {r['status']}/{r['conclusion']} por {r['actor']}")
        else:
            print("  (Sin workflow runs recientes registrados)")
        print("=" * 60 + "\n")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
