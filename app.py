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
from legawa.tools.cache import CachingPasalClient
from legawa.tools.pasal import PasalClient

# ── Default HF Inference API config (zero-config demo) ──────────────────
# Uses huggingface_hub's InferenceClient (works reliably on HF Spaces).
# Users can override via the Settings tab to use custom endpoints.
HF_BIG_MODEL = os.environ.get("HF_BIG_MODEL", "Qwen/Qwen3.5-27B")
HF_SMALL_MODEL = os.environ.get("HF_SMALL_MODEL", "Qwen/Qwen3.5-9B")
HF_TOKEN = os.environ.get("HF_TOKEN", "")

BUILD_INFO = "Build Small Hackathon 2026 · legawa v0.1"


def _is_hf_default(url_or_model: str) -> bool:
    """True if this is a model ID (no ://) or a default HF Inference API endpoint."""
    return "://" not in url_or_model or "huggingface.co/models/" in url_or_model


def _model_id_from_url(url: str) -> str:
    """Extract model ID from HF Inference API URL."""
    # URL format: https://api-inference.huggingface.co/models/{model_id}/v1
    if "/models/" in url:
        return url.split("/models/")[1].split("/v1")[0]
    return url


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
) -> tuple:
    """Build an LLM pool + CachingPasalClient from user-provided overrides.

    Uses HFLLMPool (InferenceClient) for HF endpoints,
    LLMPool (OpenAI client) for custom endpoints.
    Falls through to env vars / HF defaults for anything left blank.
    """
    from datetime import date

    # Resolve Pasal token: user input → env var → empty
    pasal_token = pasal_token or os.environ.get("PASAL_API_TOKEN", "")

    # Resolve BIG endpoint: user input → env var → HF default
    resolved_big_url = big_url or os.environ.get("LLM_BIG_URL", "")
    resolved_big_key = big_key or os.environ.get("LLM_BIG_API_KEY", HF_TOKEN)
    resolved_big_model = big_model or os.environ.get("LLM_BIG_MODEL", HF_BIG_MODEL)

    # Resolve SMALL endpoint: user input → env var → HF default
    resolved_small_url = small_url or os.environ.get("LLM_SMALL_URL", "")
    resolved_small_key = small_key or os.environ.get("LLM_SMALL_API_KEY", HF_TOKEN)
    resolved_small_model = small_model or os.environ.get("LLM_SMALL_MODEL", HF_SMALL_MODEL)

    run_date = os.environ.get("LEGAWA_RUN_DATE", date.today().isoformat())

    # Decide which backend to use
    if not resolved_big_url or _is_hf_default(resolved_big_url):
        # --- HF Inference Client (default, works reliably) ---
        from hf_llm import HFLLMPool

        big_mid = _model_id_from_url(resolved_big_url) if resolved_big_url else resolved_big_model
        small_mid = _model_id_from_url(resolved_small_url) if resolved_small_url else resolved_small_model
        pool = HFLLMPool(big_mid, small_mid, token=resolved_big_key)
        pool.settings.run_date = run_date
        pool.settings.corpus_watermark = os.environ.get("PASAL_CORPUS_WATERMARK", "")
        pool.settings.strict_citations = strict_citations
    else:
        # --- OpenAI client (custom endpoint, e.g. llama.cpp) ---
        from legawa.config import LLMConfig, Settings

        big_cfg = LLMConfig(
            base_url=resolved_big_url,
            api_key=resolved_big_key,
            model=resolved_big_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        small_cfg = LLMConfig(
            base_url=resolved_small_url,
            api_key=resolved_small_key,
            model=resolved_small_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        override_settings = Settings(
            pasal_token=pasal_token,
            pasal_base_url=os.environ.get("PASAL_BASE_URL", "https://pasal.id/api/v1"),
            big=big_cfg,
            small=small_cfg,
            run_date=run_date,
            corpus_watermark=os.environ.get("PASAL_CORPUS_WATERMARK", ""),
            strict_citations=strict_citations,
        )
        from legawa.llm import LLMPool
        pool = LLMPool(override_settings)

    raw = PasalClient(
        _pasal_settings(pasal_token)
    )
    pasal = CachingPasalClient(raw)
    return pool, pasal


def _pasal_settings(pasal_token: str) -> Settings:
    """Build a minimal Settings just for PasalClient."""
    from legawa.config import LLMConfig, Settings
    dummy = LLMConfig(base_url="", api_key="", model="", temperature=0.3, max_tokens=4096)
    return Settings(
        pasal_token=pasal_token,
        pasal_base_url=os.environ.get("PASAL_BASE_URL", "https://pasal.id/api/v1"),
        big=dummy, small=dummy,
        run_date="", corpus_watermark="", strict_citations=False,
    )

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
        # NOTE: values start empty; build_pool falls back to env vars.
        # This avoids embedding secrets in the page HTML/JS.
        big_url = gr.Textbox(label="BIG LLM Model", value=HF_BIG_MODEL, visible=False)
        big_key = gr.Textbox(label="BIG LLM API Key", value="", visible=False)
        small_url = gr.Textbox(label="SMALL LLM Model", value=HF_SMALL_MODEL, visible=False)
        small_key = gr.Textbox(label="SMALL LLM API Key", value="", visible=False)
        pasal_token = gr.Textbox(
            label="pasal.id Token",
            value="",
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
                    s_big_url = gr.Textbox(label="Model ID / URL", value=HF_BIG_MODEL)
                    s_big_key = gr.Textbox(
                        label="API Key",
                        type="password",
                        value="",
                        placeholder="Kosongkan untuk pakai HF_TOKEN dari environment",
                    )
                    s_big_model = gr.Textbox(
                        label="Model Name",
                        value="Qwen3-32B",
                    )
                with gr.Group():
                    gr.Markdown("### 🧠 LLM SMALL (klasifikasi, ekstraksi)")
                    s_small_url = gr.Textbox(label="Model ID / URL", value=HF_SMALL_MODEL)
                    s_small_key = gr.Textbox(
                        label="API Key",
                        type="password",
                        value="",
                        placeholder="Kosongkan untuk pakai HF_TOKEN dari environment",
                    )
                    s_small_model = gr.Textbox(
                        label="Model Name",
                        value="Qwen3.5-9B",
                    )
                with gr.Group():
                    gr.Markdown("### 📜 pasal.id")
                    s_pasal_token = gr.Textbox(
                        label="API Token",
                        type="password",
                        value="",
                        placeholder="Kosongkan untuk pakai PASAL_API_TOKEN dari environment",
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
app.queue(default_concurrency_limit=5)

if __name__ == "__main__":
    app.launch()
