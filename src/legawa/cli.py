"""legawa CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape

# Windows legacy console defaults to cp1252 which can't encode '✓', '→', etc.
# Reconfigure stdio to UTF-8 with a tolerant fallback so output never crashes.
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, OSError):
            pass

from .agents import analis_ruu, peneliti, penyusun, surat
from .config import load_settings
from .llm import LLMPool
from .tools.cache import CachingPasalClient
from .tools.pasal import PasalClient


app = typer.Typer(
    name="legawa",
    help="Asisten multi-agen untuk legislator Indonesia (DPR/DPRD).",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _bootstrap(use_cache: bool = True) -> tuple[LLMPool, PasalClient | CachingPasalClient]:
    settings = load_settings()
    pool = LLMPool(settings)
    raw = PasalClient(settings)
    pasal = CachingPasalClient(raw) if use_cache else raw
    return pool, pasal


def _emit(text: str, out: Optional[Path]) -> None:
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        console.print(f"[green]→ ditulis ke {out}[/green]")
    console.print(Markdown(text))


@app.command()
def analyze(
    source: str = typer.Argument(..., help="Path ke RUU (PDF/TXT) atau teks RUU langsung."),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Tulis hasil ke file Markdown."),
) -> None:
    """Analisis RUU: ringkasan, pasal-per-pasal, konflik dengan UU existing."""
    pool, pasal = _bootstrap()
    try:
        result = analis_ruu.analyze(pool, pasal, source, console=console)
    finally:
        pasal.close()
    _emit(result.output, out)


@app.command()
def research(
    topic: str = typer.Argument(..., help="Topik riset hukum (Bahasa Indonesia)."),
    out: Optional[Path] = typer.Option(None, "--out", "-o"),
) -> None:
    """Peneliti hukum: ekspansi query, pencarian paralel pasal.id, sintesis memo."""
    pool, pasal = _bootstrap()
    try:
        memo = peneliti.research(pool, pasal, topic, console=console)
    finally:
        pasal.close()
    _emit(memo, out)


@app.command()
def draft(
    kind: str = typer.Argument(..., help="Jenis: pidato | naskah_akademik | memo_kebijakan | siaran_pers"),
    topic: str = typer.Argument(..., help="Topik / pokok bahasan."),
    no_research: bool = typer.Option(False, "--no-research", help="Lewati basis riset."),
    instruksi: Optional[str] = typer.Option(None, "--instruksi", "-i", help="Instruksi tambahan."),
    out: Optional[Path] = typer.Option(None, "--out", "-o"),
) -> None:
    """Penyusun Naskah: pidato, naskah akademik, memo, siaran pers."""
    pool, pasal = _bootstrap()
    try:
        text = penyusun.draft(
            pool,
            pasal,
            kind=kind,  # type: ignore[arg-type]
            topic=topic,
            with_research=not no_research,
            extra_instructions=instruksi,
            console=console,
        )
    finally:
        pasal.close()
    _emit(text, out)


@app.command(name="surat")
def surat_cmd(
    source: str = typer.Argument(..., help="Path ke file surat (txt/md) atau teks surat langsung."),
    triase_only: bool = typer.Option(False, "--triase-only", help="Hanya triase, tanpa draft balasan."),
    no_verify: bool = typer.Option(False, "--no-verify", help="Lewati verifikasi peraturan ke pasal.id."),
    out: Optional[Path] = typer.Option(None, "--out", "-o"),
) -> None:
    """Triase surat konstituen + draft balasan formal."""
    p = Path(source)
    text = p.read_text(encoding="utf-8") if p.exists() and p.is_file() else source

    pool, pasal = _bootstrap()
    try:
        if triase_only:
            result = surat.triage(pool, text, console=console)
        else:
            result = surat.reply(pool, pasal, text, verify_law=not no_verify, console=console)
    finally:
        pasal.close()
    _emit(surat.format_report(result), out)


cache_app = typer.Typer(help="Kelola cache pasal.id (SQLite).", no_args_is_help=True)
app.add_typer(cache_app, name="cache")


@cache_app.command("stats")
def cache_stats() -> None:
    """Tampilkan jumlah entri & ukuran cache."""
    _, pasal = _bootstrap(use_cache=True)
    try:
        s = pasal.stats()  # type: ignore[union-attr]
    finally:
        pasal.close()
    console.print(s)


@cache_app.command("purge")
def cache_purge() -> None:
    """Hapus entri cache yang sudah expired."""
    _, pasal = _bootstrap(use_cache=True)
    try:
        n = pasal.purge_expired()  # type: ignore[union-attr]
    finally:
        pasal.close()
    console.print(f"[green]purged {n} expired entries[/green]")


@app.command()
def health() -> None:
    """Cek koneksi ke pasal.id dan kedua endpoint llama.cpp."""
    settings = load_settings()
    console.print(f"[dim]pasal.id  : {settings.pasal_base_url}[/dim]")
    console.print(f"[dim]LLM big   : {settings.big.base_url}  ({settings.big.model})[/dim]")
    console.print(f"[dim]LLM small : {settings.small.base_url}  ({settings.small.model})[/dim]")

    pool = LLMPool(settings)
    for label, llm in [("big", pool.big), ("small", pool.small)]:
        try:
            reply = llm.chat(
                [
                    {
                        "role": "system",
                        "content": "Balas singkat dan langsung tanpa berpikir panjang.",
                    },
                    {"role": "user", "content": "Jawab dengan satu kata: OK"},
                ],
                max_tokens=256,
                temperature=0.0,
            )
            # llm.chat already strips <think>...</think>; reply may still be empty
            # if the entire token budget was consumed by reasoning.
            visible = reply.strip()
            if not visible:
                console.print(
                    f"[yellow]! {label}: balasan kosong setelah strip thinking "
                    f"(naikkan max_tokens atau matikan thinking mode di llama.cpp)[/yellow]"
                )
            else:
                console.print(f"[green]OK {label}: {escape(visible[:60])}[/green]")
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]FAIL {label}: {escape(str(e))}[/red]")

    try:
        with PasalClient(settings) as pasal:
            r = pasal.search("ketenagakerjaan", limit=1)
        total = r.get("total") or len(r.get("results", []) or [])
        console.print(f"[green]OK pasal.id: query 'ketenagakerjaan' -> {total} hit[/green]")
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]FAIL pasal.id: {escape(str(e))}[/red]")


if __name__ == "__main__":
    app()
