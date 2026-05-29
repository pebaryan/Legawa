# Legawa Explainer Video — Plan

## Narrative Arc
Problem → Solution → Architecture → Value

## Scenes

### Scene 1: The Problem (15s)
- Tall stack of papers labeled "RUU" piles up
- A stressed legislator figure with question mark
- Text: "Ratusan RUU setiap tahun... berhari-hari riset per dokumen"
- Exit: papers fade, revealing Legawa logo

### Scene 2: What Legawa Does (25s)
- 4 agent cards appear one by one:
  - 📄 Analisis RUU — pasal-per-pasal analysis
  - 🔍 Riset Hukum — search pasal.id
  - ✍️ Draf Dokumen — draft speeches/policy memos
  - 📬 Surat Konstituen — triage constituent letters
- Each card slides in with a brief label
- Final title: "Multi-Agent AI untuk Legislator"

### Scene 3: How It Works (30s)
- Flow diagram from left to right:
  1. Input (RUU text / PDF)
  2. BIG LLM (Qwen3.5-27B) — synthesis & analysis
  3. SMALL LLM (Qwen3.5-9B) — classification & extraction
  4. pasal.id — legal database search
  5. Output — analysis with citations
- Animated arrows connect each box
- Final text appears: "Hasil lengkap dalam hitungan menit"

### Scene 4: Free & Open (15s)
- Two tokens float in: HF Token + pasal.id Token
- Text: "Bawa token sendiri. Buka di GitHub."
- GitHub link + HF Space link at bottom
- Closing: "Legawa — small models, big adventure 🏕️"

## Color Palette (Warm Academic)
| Role | Color | Hex |
|------|-------|-----|
| Background | Dark navy | `#1a1a2e` |
| Title text | Warm white | `#eaeaea` |
| Primary accent | Coral | `#ff6b6b` |
| Secondary | Gold | `#ffd93d` |
| Accent | Mint | `#6bcb77` |
| Muted | Grey | `#888888` |

## Technical Notes
- No LaTeX available — use Text() with monospace font
- Resolution: 1280x720 (manim -qm)
- FPS: 30
- No audio/voiceover — text-based explainer with captions
- Each scene independently renderable
