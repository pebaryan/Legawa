---
title: Legawa
emoji: 🏛️
colorFrom: indigo
colorTo: slate
sdk: gradio
sdk_version: 5.0
app_file: app.py
pinned: false
license: mit
---

# 🏛️ Legawa

**Asisten multi-agen untuk legislator Indonesia (DPR/DPRD).**

Tiga agen AI berbasis Qwen3 (≤32B params) yang membantu anggota legislatif dan staf ahli
dalam pekerjaan sehari-hari: analisis RUU, riset hukum, penyusunan naskah, dan triase surat konstituen.

## ✨ Fitur

| Tab | Agen | Kegunaan |
|-----|------|----------|
| 📄 **Analisis RUU** | `analis_ruu` | Upload/tempel teks RUU → analisis pasal-per-pasal + deteksi konflik |
| 🔍 **Riset Hukum** | `peneliti` | Topik → ekspansi query → pencarian paralel di [pasal.id](https://pasal.id) → memo riset |
| ✍️ **Draf Dokumen** | `penyusun` | Pidato, naskah akademik, memo kebijakan, siaran pers |
| 📬 **Surat Konstituen** | `surat` | Triase surat + draft balasan resmi |

## 🧠 Model

Dua instance Qwen3 (≤32B total) via Hugging Face Inference API atau llama.cpp lokal:

- **BIG** (~30B): sintesis, drafting, analisis mendalam
- **SMALL** (~8B): klasifikasi, ekstraksi, ekspansi query

## 🔧 Konfigurasi

Buka tab **⚙️ Pengaturan** untuk mengubah endpoint LLM atau token pasal.id.
Default menggunakan HF Inference API (gratis, tanpa API key untuk kuota kecil).

## 🔗 Tautan

- [GitHub](https://github.com/pebaryan/Legawa)
- [pasal.id](https://pasal.id)
- [Build Small Hackathon](https://huggingface.co/build-small-hackathon)

---

*🏕️ Build Small Hackathon 2026 — small models, big adventure*
