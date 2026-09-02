#!/usr/bin/env python3
"""
AI Lab — Git Repository Auditor & Backup Sentinel
Audita masivamente todos los repositorios en /media/darkseid/DATA/Repos.
Detecta:
  - Cambios sin commitear (uncommitted/dirty)
  - Archivos sin seguimiento (untracked)
  - Commits locales sin subir al remoto (unpushed/ahead)
  - Repositorios sin remote (sin respaldo externo)
"""

import os
import sys
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Dict, Any

REPOS_DIR = Path("/media/darkseid/DATA/Repos")


@dataclass
class RepoStatus:
    name: str
    path: Path
    branch: str
    has_uncommitted: bool
    uncommitted_count: int
    has_untracked: bool
    untracked_count: int
    unpushed_commits: int
    has_remote: bool
    remote_url: str
    last_commit_date: str
    is_clean: bool


def check_single_repo(repo_path: Path) -> RepoStatus | None:
    """Inspecciona un repositorio individual usando comandos git rápidos."""
    if not (repo_path / ".git").exists():
        return None

    try:
        # 1. Rama actual
        res_branch = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=3
        )
        branch = res_branch.stdout.strip() or "HEAD (detached)"

        # 2. Estado de cambios locales (porcelain)
        res_status = subprocess.run(
            ["git", "-C", str(repo_path), "status", "--porcelain"],
            capture_output=True, text=True, timeout=3
        )
        lines = [l for l in res_status.stdout.split("\n") if l.strip()]
        untracked = [l for l in lines if l.startswith("??")]
        uncommitted = [l for l in lines if not l.startswith("??")]

        # 3. Remotos
        res_remote = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=2
        )
        has_remote = (res_remote.returncode == 0 and bool(res_remote.stdout.strip()))
        remote_url = res_remote.stdout.strip() if has_remote else "Sin remote"

        # 4. Commits por subir (ahead)
        unpushed_commits = 0
        if has_remote:
            res_ahead = subprocess.run(
                ["git", "-C", str(repo_path), "rev-list", "@{u}..HEAD", "--count"],
                capture_output=True, text=True, timeout=3
            )
            if res_ahead.returncode == 0:
                try:
                    unpushed_commits = int(res_ahead.stdout.strip())
                except ValueError:
                    unpushed_commits = 0

        # 5. Último commit date
        res_date = subprocess.run(
            ["git", "-C", str(repo_path), "log", "-1", "--format=%cd", "--date=relative"],
            capture_output=True, text=True, timeout=2
        )
        last_date = res_date.stdout.strip() or "Sin commits"

        is_clean = (len(uncommitted) == 0 and len(untracked) == 0 and unpushed_commits == 0)

        return RepoStatus(
            name=repo_path.name,
            path=repo_path,
            branch=branch,
            has_uncommitted=len(uncommitted) > 0,
            uncommitted_count=len(uncommitted),
            has_untracked=len(untracked) > 0,
            untracked_count=len(untracked),
            unpushed_commits=unpushed_commits,
            has_remote=has_remote,
            remote_url=remote_url,
            last_commit_date=last_date,
            is_clean=is_clean
        )
    except Exception as e:
        return None


class GitRepositoryAuditor:
    """Escanea y audita masivamente todos los repositorios en el directorio principal."""

    def __init__(self, base_dir: Path = REPOS_DIR):
        self.base_dir = Path(base_dir).resolve()

    def discover_repos(self) -> List[Path]:
        """Encuentra todos los directorios que contienen .git."""
        if not self.base_dir.exists():
            return []
        
        repos = []
        try:
            for item in self.base_dir.iterdir():
                if item.is_dir() and (item / ".git").exists():
                    repos.append(item)
        except Exception:
            pass
        return sorted(repos)

    def audit_all(self, max_workers: int = 16) -> Dict[str, Any]:
        """Ejecuta la auditoría en paralelo."""
        repo_paths = self.discover_repos()
        if not repo_paths:
            return {
                "total": 0,
                "clean": [],
                "dirty": [],
                "unpushed": [],
                "no_remote": [],
                "error": f"No se encontraron repositorios o el directorio {self.base_dir} no está montado."
            }

        results: List[RepoStatus] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_repo = {executor.submit(check_single_repo, p): p for p in repo_paths}
            for future in as_completed(future_to_repo):
                res = future.result()
                if res:
                    results.append(res)

        results.sort(key=lambda r: r.name.lower())

        dirty = [r for r in results if r.has_uncommitted or r.has_untracked]
        unpushed = [r for r in results if r.unpushed_commits > 0]
        no_remote = [r for r in results if not r.has_remote]
        clean = [r for r in results if r.is_clean]

        return {
            "total": len(results),
            "clean_count": len(clean),
            "dirty_count": len(dirty),
            "unpushed_count": len(unpushed),
            "no_remote_count": len(no_remote),
            "dirty": dirty,
            "unpushed": unpushed,
            "no_remote": no_remote,
            "clean": clean
        }

    def generate_report(self, max_items: int = 15) -> str:
        """Genera un reporte formateado en Markdown listo para Telegram o pantalla."""
        data = self.audit_all()
        if data.get("error"):
            return f"⚠️ {data['error']}"

        total = data["total"]
        dirty = data["dirty"]
        unpushed = data["unpushed"]
        no_remote = data["no_remote"]
        clean_count = data["clean_count"]

        lines = [
            f"🛡️ *Auditoría de Repositorios Git (`{self.base_dir}`)*\n",
            f"📊 **Resumen General:**",
            f"• **Total de Repositorios:** `{total}`",
            f"• 🟢 **Al día y limpios:** `{clean_count}`",
            f"• 📝 **Con cambios sin commitear:** `{len(dirty)}`",
            f"• 🚀 **Con commits locales sin subir (unpushed):** `{len(unpushed)}`",
            f"• 🌐 **Sin repositorio remoto (solo local):** `{len(no_remote)}`\n"
        ]

        if dirty:
            lines.append("📝 *Repositorios con Cambios Pendientes (Uncommitted / Untracked):*")
            for r in dirty[:max_items]:
                details = []
                if r.has_uncommitted:
                    details.append(f"{r.uncommitted_count} modif.")
                if r.has_untracked:
                    details.append(f"{r.untracked_count} nuevos")
                lines.append(f"• `{r.name}` ({', '.join(details)}) [{r.branch}]")
            if len(dirty) > max_items:
                lines.append(f"  _...y {len(dirty) - max_items} repositorios más._\n")
            else:
                lines.append("")

        if unpushed:
            lines.append("🚀 *Repositorios con Commits Locales por Subir (Ahead):*")
            for r in unpushed[:max_items]:
                lines.append(f"• `{r.name}`: `{r.unpushed_commits}` commit(s) pendientes de push [{r.branch}]")
            if len(unpushed) > max_items:
                lines.append(f"  _...y {len(unpushed) - max_items} repositorios más._\n")
            else:
                lines.append("")

        if not dirty and not unpushed:
            lines.append("✨ **¡Todo tu acervo técnico está limpio y respaldado al 100%!**")

        return "\n".join(lines)


if __name__ == "__main__":
    auditor = GitRepositoryAuditor()
    print(auditor.generate_report(max_items=25))
