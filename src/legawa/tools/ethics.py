"""Ethics verifier — post-processing guardrails for democratic values & HAM.

Checks agent output against 4 democratic values (people's sovereignty, democracy,
human rights, political ethics) and appends a considerations section if missing.

Inspired by feedback from Taufik Basari, S.H., S.Hum., LL.M.
(DPR RI 2019–2024).
"""

from __future__ import annotations

from typing import Any

VERIFIER_PROMPT = """\
Periksa apakah analisis berikut sudah mempertimbangkan 4 nilai demokrasi & HAM ini:
1. **Kedaulatan Rakyat** — partisipasi publik, kepentingan rakyat
2. **Prinsip Demokrasi** — checks and balances, abuse of power
3. **Hak Asasi Manusia** — dampak HAM, hak-hak terdampak
4. **Etika Politik** — do's and don'ts, transparansi, akuntabilitas

Jika KEEMPAT nilai sudah dibahas di dalam teks, balas hanya dengan: OK
Jika ADA yang belum dibahas, hasilkan bagian "### ⚖️ Pertimbangan Etika & HAM"
dalam Bahasa Indonesia yang mencakup nilai-nilai yang kurang. Output markdown."""


def ethics_verify(
    output: str,
    llm: Any,
    *,
    temperature: float = 0.2,
    max_tokens: int = 512,
) -> str:
    """Post-process agent output: append ethics considerations if missing.

    Args:
        output: The agent's raw markdown output.
        llm: An object with a .chat() method (HFLLM or legawa LLM).

    Returns:
        Original output, possibly with an appended ethics section.
    """
    if not output.strip():
        return output

    try:
        resp = llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": VERIFIER_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        "Berikut adalah output analisis yang sudah dihasilkan.\n"
                        "Periksa nilai-nilai demokrasi & HAM:\n\n"
                        f"{output[:4000]}"
                    ),
                },
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = (resp or "").strip()
        if not text or text.upper().startswith("OK"):
            return output  # all values already covered

        # Append the ethics section
        return output.rstrip() + "\n\n---\n" + text

    except Exception:
        # Fail-safe: return original output on any error
        return output
