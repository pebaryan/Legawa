"""
app.py — Legawa Gradio Space for Build Small Hackathon.

Runs the 4 agent workflows (analis_ruu, peneliti, penyusun, surat)
inside a Gradio web UI instead of the Typer CLI. Default LLM backend
is HF Inference API (zero-config demo); users can override in Settings.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Ensure the src/ package is importable on HF Spaces
_src = Path(__file__).resolve().parent / "src"
if _src.exists() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import gradio as gr

from legawa.agents import analis_ruu, peneliti, penyusun, surat
from legawa.config import LLMConfig, Settings, load_settings
from legawa.llm import LLM, LLMPool
from legawa.tools.cache import CachingPasalClient
from legawa.tools.pasal import PasalClient

# ── Default HF Inference API config (zero-config demo) ──────────────────
# These map to HF's free Inference API, which is OpenAI-compatible.
# Users can override via the Settings tab or by setting env vars on the Space.
HF_BIG_URL = os.environ.get(
    "HF_BIG_URL",
    "https://api-inference.huggingface.co/models/Qwen/Qwen3-30B-A3B/v1",
)
HF_SMALL_URL = os.environ.get(
    "HF_SMALL_URL",
    "https://api-inference.huggingface.co/models/Qwen/Qwen3-8B/v1",
)
# HF Inference API doesn't require a token for free-tier browsing, but
# setting HF_TOKEN as a Space secret bumps your rate limit significantly.
HF_TOKEN = os.environ.get("HF_TOKEN", "")

BUILD_INFO = "Build Small Hackathon 2026 · legawa v0.1"


# ── Bootstrap: create settings + pool given user overrides ──────────────
def build_pool(
    big_url: str = "",
    big_key: str = "",
    big_model: str = "",
    small_url: str = "",
    small_key: str = "",
    small_model: str = "",
    pasal_token: str = "",
    temperature: float = 0.3,
    max_tokens: int = 4096,
    strict_citations: bool = True,
) -> tuple[LLMPool, CachingPasalClient]:
    """Build an LLMPool + CachingPasalClient from user-provided overrides.

    Falls through to env vars / HF defaults for anything left blank.
    """
    settings = load_settings()

    # Pasal token: prefer user input, then env
    pasal_token = pasal_token or settings.pasal_token

    # Rebuild settings with overrides
    big_cfg = LLMConfig(
        base_url=big_url or getattr(settings.big, "base_url", HF_BIG_URL),
        api_key=big_key or HF_TOKEN or settings.big.api_key,
        model=big_model or settings.big.model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    small_cfg = LLMConfig(
        base_url=small_url or getattr(settings.small, "base_url", HF_SMALL_URL),
        api_key=small_key or HF_TOKEN or settings.small.api_key,
        model=small_model or settings.small.model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # Patch the settings dataclass
    override_settings = Settings(
        pasal_token=pasal_token or "",
        pasal_base_url=settings.pasal_base_url,
        big=big_cfg,
        small=small_cfg,
        run_date=settings.run_date,
        corpus_watermark=settings.corpus_watermark,
        strict_citations=strict_citations,
    )

    pool = LLMPool(override_settings)
    raw = PasalClient(override_settings)
    pasal = CachingPasalClient(raw)
    return pool, pasal


# ── Agent wrappers (called by Gradio) ───────────────────────────────────

def agent_analyze(
    source: str,
    big_url: str,
    big_key: str,
    small_url: str,
    small_key: str,
    pasal_token: str,
    progress=gr.Progress(),
) -> str:
    if not source.strip():
        return "Masukkan teks RUU atau upload file PDF."
    progress(0.1, desc="Memuat model & koneksi...")
    pool, pasal = build_pool(
        big_url=big_url, big_key=big_key,
        small_url=small_url, small_key=small_key,
        pasal_token=pasal_token,
    )
    try:
        progress(0.3, desc="Menganalisis RUU...")
        result = analis_ruu.analyze(pool, pasal, source)
        progress(1.0, desc="Selesai!")
        return result.output
    except Exception as e:
        return f"**Error:** {e}"
    finally:
        pasal.close()


def agent_research(
    topic: str,
    big_url: str,
    big_key: str,
    small_url: str,
    small_key: str,
    pasal_token: str,
    progress=gr.Progress(),
) -> str:
    if not topic.strip():
        return "Masukkan topik riset hukum."
    progress(0.1, desc="Memuat model & koneksi...")
    pool, pasal = build_pool(
        big_url=big_url, big_key=big_key,
        small_url=small_url, small_key=small_key,
        pasal_token=pasal_token,
    )
    try:
        progress(0.2, desc="Ekspansi query...")
        progress(0.5, desc="Mencari peraturan...")
        output = peneliti.research(pool, pasal, topic)
        progress(1.0, desc="Selesai!")
        return output
    except Exception as e:
        return f"**Error:** {e}"
    finally:
        pasal.close()


def agent_draft(
    kind: str,
    topic: str,
    extra_instructions: str,
    with_research: bool,
    big_url: str,
    big_key: str,
    small_url: str,
    small_key: str,
    pasal_token: str,
    progress=gr.Progress(),
) -> str:
    if not topic.strip():
        return "Masukkan topik."
    progress(0.1, desc="Memuat model & koneksi...")
    pool, pasal = build_pool(
        big_url=big_url, big_key=big_key,
        small_url=small_url, small_key=small_key,
        pasal_token=pasal_token,
    )
    try:
        progress(0.3, desc="Menyusun naskah...")
        output = penyusun.draft(
            pool, pasal, kind, topic,
            with_research=with_research,
            extra_instructions=extra_instructions or None,
        )
        progress(1.0, desc="Selesai!")
        return output
    except Exception as e:
        return f"**Error:** {e}"
    finally:
        pasal.close()


def agent_surat(
    surat_text: str,
    verify_law: bool,
    big_url: str,
    big_key: str,
    small_url: str,
    small_key: str,
    pasal_token: str,
    progress=gr.Progress(),
) -> str:
    if not surat_text.strip():
        return "Masukkan teks surat konstituen."
    progress(0.1, desc="Memuat model & koneksi...")
    pool, pasal = build_pool(
        big_url=big_url, big_key=big_key,
        small_url=small_url, small_key=small_key,
        pasal_token=pasal_token,
    )
    try:
        progress(0.3, desc="Triase surat...")
        result = surat.reply(
            pool, pasal, surat_text,
            verify_law=verify_law,
        )
        progress(1.0, desc="Selesai!")
        return surat.format_report(result)
    except Exception as e:
        return f"**Error:** {e}"
    finally:
        pasal.close()


def agent_health(
    big_url: str,
    big_key: str,
    small_url: str,
    small_key: str,
    pasal_token: str,
) -> str:
    """Quick connectivity check for all services."""
    lines: list[str] = []
    pool, pasal = build_pool(
        big_url=big_url, big_key=big_key,
        small_url=small_url, small_key=small_key,
        pasal_token=pasal_token,
    )
    try:
        # Check BIG LLM
        try:
            resp = pool.big.chat(
                [{"role": "user", "content": "Jawab dengan satu kata: OK"}],
                max_tokens=10,
            )
            lines.append(f"✅ **BIG LLM** ({pool.big.cfg.model[:30]}...): {resp.strip()}")
        except Exception as e:
            lines.append(f"❌ **BIG LLM**: {e}")

        # Check SMALL LLM
        try:
            resp = pool.small.chat(
                [{"role": "user", "content": "Jawab dengan satu kata: OK"}],
                max_tokens=10,
            )
            lines.append(f"✅ **SMALL LLM** ({pool.small.cfg.model[:30]}...): {resp.strip()}")
        except Exception as e:
            lines.append(f"❌ **SMALL LLM**: {e}")

        # Check pasal.id
        try:
            result = pasal.search("ketenagakerjaan", limit=1)
            count = len(result.get("results", result.get("hits", [])))
            lines.append(f"✅ **pasal.id**: {count} hasil untuk 'ketenagakerjaan'")
        except Exception as e:
            lines.append(f"❌ **pasal.id**: {e}")

        lines.append(f"\n{BUILD_INFO}")
        return "\n\n".join(lines)
    finally:
        pasal.close()


# ── File upload helper for analis_ruu ───────────────────────────────────

def handle_file_upload(file: tempfile.NamedTemporaryFile | None) -> str:
    if file is None:
        return ""
    path = Path(file.name)
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8")


# ── Build Gradio UI ─────────────────────────────────────────────────────

CSS = """
/* Space is compact and readable */
.container { max-width: 960px; margin: 0 auto; }
footer { display: none !important; }
.dark table { color: #e0e0e0; }
"""


def build_app() -> gr.Blocks:
    with gr.Blocks(
        css=CSS,
        title="Legawa — Asisten Legislatif",
        theme=gr.themes.Soft(),
    ) as app:
        gr.Markdown(
            f"# 🏛️ Legawa\n"
            f"Asisten multi-agen untuk legislator Indonesia (DPR/DPRD)\n"
            f"*{BUILD_INFO}*"
        )

        # ── Hidden state for connection config shared across tabs ──────
        big_url = gr.Textbox(label="BIG LLM URL", value=HF_BIG_URL, visible=False)
        big_key = gr.Textbox(label="BIG LLM API Key", value=HF_TOKEN, visible=False)
        small_url = gr.Textbox(label="SMALL LLM URL", value=HF_SMALL_URL, visible=False)
        small_key = gr.Textbox(label="SMALL LLM API Key", value=HF_TOKEN, visible=False)
        pasal_token = gr.Textbox(
            label="pasal.id Token",
            value=os.environ.get("PASAL_API_TOKEN", ""),
            visible=False,
        )

        with gr.Tabs():
            # ─── Tab 1: Analisis RUU ──────────────────────────────────
            with gr.TabItem("📄 Analisis RUU"):
                gr.Markdown(
                    "Upload atau tempel teks RUU untuk dianalisis pasal-per-pasal."
                )
                with gr.Row():
                    with gr.Column(scale=2):
                        ruu_text = gr.Textbox(
                            label="Teks RUU",
                            placeholder="Tempel teks RUU di sini, atau upload file...",
                            lines=12,
                        )
                    with gr.Column(scale=1):
                        ruu_file = gr.File(
                            label="Upload PDF/TXT",
                            file_types=[".pdf", ".txt", ".md"],
                        )
                with gr.Row():
                    ruu_btn = gr.Button("Analisis RUU", variant="primary", size="lg")
                ruu_out = gr.Markdown(label="Hasil Analisis")
                ruu_file.change(
                    fn=handle_file_upload,
                    inputs=[ruu_file],
                    outputs=[ruu_text],
                )
                ruu_btn.click(
                    fn=agent_analyze,
                    inputs=[
                        ruu_text, big_url, big_key,
                        small_url, small_key, pasal_token,
                    ],
                    outputs=[ruu_out],
                )

            # ─── Tab 2: Riset Hukum ────────────────────────────────────
            with gr.TabItem("🔍 Riset Hukum"):
                gr.Markdown("Cari peraturan terkait topik tertentu di pasal.id.")
                with gr.Row():
                    riset_topic = gr.Textbox(
                        label="Topik Riset",
                        placeholder="Contoh: perlindungan data pribadi sektor kesehatan",
                        lines=3,
                        scale=3,
                    )
                with gr.Row():
                    riset_btn = gr.Button("Riset Hukum", variant="primary", size="lg")
                riset_out = gr.Markdown(label="Memo Riset")
                riset_btn.click(
                    fn=agent_research,
                    inputs=[
                        riset_topic, big_url, big_key,
                        small_url, small_key, pasal_token,
                    ],
                    outputs=[riset_out],
                )

            # ─── Tab 3: Draf Dokumen ──────────────────────────────────
            with gr.TabItem("✍️ Draf Dokumen"):
                gr.Markdown("Susun pidato, naskah akademik, memo kebijakan, atau siaran pers.")
                with gr.Row():
                    draft_kind = gr.Dropdown(
                        label="Jenis Dokumen",
                        choices=[
                            ("Pidato", "pidato"),
                            ("Naskah Akademik", "naskah_akademik"),
                            ("Memo Kebijakan", "memo_kebijakan"),
                            ("Siaran Pers", "siaran_pers"),
                        ],
                        value="memo_kebijakan",
                    )
                    draft_topic = gr.Textbox(
                        label="Topik",
                        placeholder="Contoh: urgensi RUU Masyarakat Adat",
                        lines=2,
                        scale=2,
                    )
                with gr.Row():
                    draft_extra = gr.Textbox(
                        label="Instruksi Tambahan (opsional)",
                        placeholder="fokus pada aspek fiskal...",
                        lines=2,
                        scale=2,
                    )
                with gr.Row():
                    draft_research = gr.Checkbox(
                        label="Sertakan riset hukum pendukung",
                        value=True,
                    )
                with gr.Row():
                    draft_btn = gr.Button("Susun Naskah", variant="primary", size="lg")
                draft_out = gr.Markdown(label="Draf Dokumen")
                draft_btn.click(
                    fn=agent_draft,
                    inputs=[
                        draft_kind, draft_topic, draft_extra,
                        draft_research,
                        big_url, big_key, small_url, small_key,
                        pasal_token,
                    ],
                    outputs=[draft_out],
                )

            # ─── Tab 4: Surat Konstituen ───────────────────────────────
            with gr.TabItem("📬 Surat Konstituen"):
                gr.Markdown(
                    "Tempel surat/email dari konstituen untuk triase dan draft balasan."
                )
                surat_text = gr.Textbox(
                    label="Surat Konstituen",
                    placeholder="Tempel surat konstituen di sini...",
                    lines=10,
                )
                with gr.Row():
                    surat_verify = gr.Checkbox(
                        label="Verifikasi peraturan yang disebut di pasal.id",
                        value=True,
                    )
                with gr.Row():
                    surat_btn = gr.Button("Triase & Balas", variant="primary", size="lg")
                surat_out = gr.Markdown(label="Hasil")
                surat_btn.click(
                    fn=agent_surat,
                    inputs=[
                        surat_text, surat_verify,
                        big_url, big_key, small_url, small_key,
                        pasal_token,
                    ],
                    outputs=[surat_out],
                )

            # ─── Tab 5: Pengaturan ──────────────────────────────────────
            with gr.TabItem("⚙️ Pengaturan"):
                gr.Markdown(
                    "Konfigurasi koneksi LLM dan pasal.id. "
                    "Kosongkan untuk menggunakan default (HF Inference API)."
                )
                with gr.Group():
                    gr.Markdown("### 🧠 LLM BIG (sintesis, drafting)")
                    s_big_url = gr.Textbox(label="URL", value=HF_BIG_URL)
                    s_big_key = gr.Textbox(
                        label="API Key",
                        type="password",
                        value=HF_TOKEN,
                    )
                    s_big_model = gr.Textbox(
                        label="Model Name",
                        value="Qwen3-30B-A3B",
                    )
                with gr.Group():
                    gr.Markdown("### 🧠 LLM SMALL (klasifikasi, ekstraksi)")
                    s_small_url = gr.Textbox(label="URL", value=HF_SMALL_URL)
                    s_small_key = gr.Textbox(
                        label="API Key",
                        type="password",
                        value=HF_TOKEN,
                    )
                    s_small_model = gr.Textbox(
                        label="Model Name",
                        value="Qwen3-8B",
                    )
                with gr.Group():
                    gr.Markdown("### 📜 pasal.id")
                    s_pasal_token = gr.Textbox(
                        label="API Token",
                        type="password",
                        value=os.environ.get("PASAL_API_TOKEN", ""),
                    )
                with gr.Group():
                    gr.Markdown("### ⚙️ Lainnya")
                    s_temp = gr.Slider(
                        label="Temperature",
                        minimum=0.0, maximum=1.0, step=0.05, value=0.3,
                    )
                    s_max_tokens = gr.Slider(
                        label="Max Tokens",
                        minimum=512, maximum=8192, step=256, value=4096,
                    )
                    s_strict = gr.Checkbox(
                        label="Strict citations (tolak draft jika sitasi tidak terverifikasi)",
                        value=True,
                    )
                with gr.Row():
                    save_btn = gr.Button("Simpan & Uji Koneksi", variant="primary")
                health_out = gr.Markdown(label="Status Koneksi")

                def save_settings(
                    bu, bk, bm, su, sk, sm, pt, temp, mt, strict,
                ):
                    # Push settings to the hidden state boxes
                    return bu, bk, su, sk, pt, gr.update()

                # Save button writes to hidden state AND runs health check
                save_btn.click(
                    fn=lambda bu, bk, bm, su, sk, sm, pt, temp, mt, strict: (
                        bu, bk, su, sk, pt,
                        agent_health(bu, bk, su, sk, pt),
                    ),
                    inputs=[
                        s_big_url, s_big_key, s_big_model,
                        s_small_url, s_small_key, s_small_model,
                        s_pasal_token, s_temp, s_max_tokens, s_strict,
                    ],
                    outputs=[big_url, big_key, small_url, small_key, pasal_token, health_out],
                )

        gr.Markdown(
            f"---\n"
            f"**Legawa** — *small models, big adventure* 🏕️ | "
            f"[GitHub](https://github.com/pebaryan/Legawa) | "
            f"[pasal.id](https://pasal.id)"
        )

    return app


# ── Entry point ─────────────────────────────────────────────────────────

app = build_app()

if __name__ == "__main__":
    app.launch()
