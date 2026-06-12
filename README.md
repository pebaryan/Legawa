---
title: Legawa
emoji: 🏛️
colorFrom: indigo
colorTo: gray
sdk: gradio
app_file: app.py
pinned: false
license: mit
short_description: Triase surat warga & riset hukum untuk staf DPR/DPRD
tags:
  - track:backyard
  - backyard-ai
  - multi-agent
  - indonesia
  - legal
---

# 🏛️ Legawa

**Asisten multi-agen untuk staf legislator Indonesia (DPR/DPRD) — Backyard AI track.**

Kantor legislator kebanjiran dokumen: RUU ratusan halaman, surat warga menumpuk, memo
harus jadi hari ini. Legawa memakai empat agen AI kecil (2× Qwen3.5-9B = 18B params,
jauh di bawah batas 32B) untuk analisis RUU, riset hukum, penyusunan naskah, dan triase
surat konstituen — dengan sitasi yang diverifikasi ke [pasal.id](https://pasal.id) dan
aktivitas tiap agen terlihat live di UI.

▶️ **[Video demo (51 detik)](https://www.youtube.com/watch?v=jgYXyij1P9Q)**

Fitur etika, demokrasi & HAM dibangun dari masukan **Taufik Basari** (anggota DPR RI
2019–2024) — setiap output diperiksa terhadap 4 nilai: kedaulatan rakyat, prinsip
demokrasi, HAM, dan etika politik.

## ✨ Fitur

| Tab | Agen | Kegunaan |
|-----|------|----------|
| 📄 **Analisis RUU** | `analis_ruu` | Upload/tempel teks RUU → analisis pasal-per-pasal + deteksi konflik |
| 🔍 **Riset Hukum** | `peneliti` | Topik → ekspansi query → pencarian paralel di [pasal.id](https://pasal.id) → memo riset |
| ✍️ **Draf Dokumen** | `penyusun` | Pidato, naskah akademik, memo kebijakan, siaran pers |
| 📬 **Surat Konstituen** | `surat` | Triase surat + draft balasan resmi |

## 🧠 Model

Dua instance Qwen3.5-9B (18B total, batas hackathon 32B) via Hugging Face Inference API
atau endpoint llama.cpp/vLLM sendiri:

- **BIG**: sintesis, drafting, analisis mendalam
- **SMALL**: klasifikasi, ekstraksi, ekspansi query

Pemisahan SMALL/BIG ini bukan sekadar kepatuhan batas parameter — routing per-tugas
membuat pipeline tetap cepat dan murah, dan panel **Aktivitas Agen** menampilkan
hand-off antar agen secara real time.

## 🔧 Konfigurasi

Buka tab **⚙️ Pengaturan** untuk mengubah endpoint LLM atau token pasal.id.
Default menggunakan HF Inference API (gratis, tanpa API key untuk kuota kecil).

## 🔗 Tautan

- [GitHub](https://github.com/pebaryan/Legawa)
- [pasal.id](https://pasal.id)
- [Build Small Hackathon](https://huggingface.co/build-small-hackathon)

---

*🏕️ Build Small Hackathon 2026 — small models, big adventure*
