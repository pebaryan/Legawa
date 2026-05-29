"""Legawa Explainer Video — Manim CE script.

Scenes:
  1. The Problem — stack of RUU documents
  2. What Legawa Does — 4 agent cards
  3. How It Works — flow diagram
  4. Free & Open — tokens + links

Rendered with: manim -qm script.py Scene1_Problem Scene2_Agents Scene3_Flow Scene4_Closing
"""

from manim import *

# ── Palette (Warm Academic) ──────────────────────────────────────────────
BG = "#1a1a2e"
TITLE = "#eaeaea"
BODY = "#cccccc"
PRIMARY = "#ff6b6b"
SECONDARY = "#ffd93d"
ACCENT = "#6bcb77"
MUTED = "#666666"
MONO = "monospace"

# ── Helpers ──────────────────────────────────────────────────────────────

def T(text, size=36, color=TITLE, weight=NORMAL):
    """Shorthand for monospace Text."""
    return Text(text, font_size=size, font=MONO, color=color, weight=weight)


def card_box(width=2.2, height=1.2, color=PRIMARY):
    """Rounded rect for agent cards."""
    return RoundedRectangle(
        width=width, height=height,
        corner_radius=0.15,
        stroke_color=color, stroke_width=2.5,
        fill_color=color, fill_opacity=0.12,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Scene 1 — The Problem
# ═══════════════════════════════════════════════════════════════════════════

class Scene1_Problem(Scene):
    def construct(self):
        self.camera.background_color = BG

        # Papers piling up
        papers = VGroup()
        labels = ["RUU", "RUU", "RUU", "RUU", "RUU", "RUU"]
        colors = [PRIMARY, SECONDARY, ACCENT, PRIMARY, SECONDARY, ACCENT]
        for i, (label, c) in enumerate(zip(labels[:6], colors[:6])):
            w, h = 2.6 - i * 0.15, 3.2 - i * 0.15
            x_shift = i * 0.06
            y_shift = i * 0.08 - 1.0
            paper = Rectangle(
                width=w, height=h,
                stroke_color=c, stroke_width=2,
                fill_color=c, fill_opacity=0.08,
            ).shift(RIGHT * x_shift + UP * y_shift)
            text = T(label, size=18, color=c).move_to(paper)
            papers.add(paper, text)

        self.play(
            LaggedStart(*[FadeIn(p, shift=UP * 0.3, scale=0.9) for p in papers],
                        lag_ratio=0.12),
            run_time=2.5,
        )
        self.wait(0.5)

        # Stressed legislator text
        stress = T("?", size=72, color=PRIMARY, weight=BOLD).shift(RIGHT * 3.2 + UP * 1.0)
        self.play(Write(stress), run_time=0.5)
        self.wait(0.3)

        # Problem text above the stack
        problem_text = T(
            "Ratusan RUU setiap tahun...\nberhari-hari riset per dokumen",
            size=26, color=BODY,
        ).to_edge(UP, buff=0.5)
        self.play(Write(problem_text), run_time=1.2)
        self.wait(1.5)

        # Fade out to Legawa logo
        logo = T("🏛️  Legawa", size=56, color=SECONDARY, weight=BOLD)
        subtitle = T("Multi-Agent AI untuk Legislator", size=24, color=MUTED).next_to(logo, DOWN)

        self.play(
            FadeOut(VGroup(*papers, stress, problem_text)),
            run_time=0.8,
        )
        self.play(Write(logo), run_time=1.0)
        self.play(Write(subtitle), run_time=0.8)
        self.wait(1.5)
        self.play(FadeOut(VGroup(logo, subtitle)), run_time=0.5)


# ═══════════════════════════════════════════════════════════════════════════
# Scene 2 — What Legawa Does
# ═══════════════════════════════════════════════════════════════════════════

class Scene2_Agents(Scene):
    def construct(self):
        self.camera.background_color = BG

        title = T("Empat Agen dalam Satu Asisten", size=40, color=TITLE, weight=BOLD)
        title.to_edge(UP, buff=0.5)
        self.play(Write(title), run_time=0.8)
        self.wait(0.3)

        # 4 agent cards in a 2x2 grid
        agents = [
            ("📄 Analisis\nRUU", PRIMARY, "Analisis pasal-per-pasal\nlengkap sitasi"),
            ("🔍 Riset\nHukum", ACCENT, "Cari peraturan di\npasal.id"),
            ("✍️ Draf\nDokumen", SECONDARY, "Pidato, naskah akademik,\nmemo kebijakan"),
            ("📬 Surat\nKonstituen", PRIMARY, "Triase & draft\nbalasan"),
        ]

        positions = [
            LEFT * 3 + UP * 0.5,
            RIGHT * 3 + UP * 0.5,
            LEFT * 3 + DOWN * 1.8,
            RIGHT * 3 + DOWN * 1.8,
        ]

        cards = VGroup()
        for (emoji_name, color, desc), pos in zip(agents, positions):
            box = RoundedRectangle(
                width=4.5, height=2.2,
                corner_radius=0.15,
                stroke_color=color, stroke_width=2.5,
                fill_color=color, fill_opacity=0.1,
            ).move_to(pos)

            name_text = T(emoji_name, size=30, color=color, weight=BOLD)
            name_text.move_to(box).shift(UP * 0.3)

            desc_text = T(desc, size=18, color=BODY)
            desc_text.next_to(name_text, DOWN, buff=0.3)

            cards.add(VGroup(box, name_text, desc_text))

        # Animate in one by one
        for card in cards:
            self.play(FadeIn(card, shift=UP * 0.3, scale=0.95), run_time=0.6)
            self.wait(0.15)

        self.wait(1.0)

        # Tagline
        tag = T("Small models, big adventure 🏕️", size=24, color=SECONDARY)
        tag.to_edge(DOWN, buff=0.4)
        self.play(Write(tag), run_time=0.8)
        self.wait(1.5)

        self.play(FadeOut(VGroup(title, cards, tag)), run_time=0.5)


# ═══════════════════════════════════════════════════════════════════════════
# Scene 3 — How It Works (Flow Diagram)
# ═══════════════════════════════════════════════════════════════════════════

class Scene3_Flow(Scene):
    def construct(self):
        self.camera.background_color = BG

        title = T("Bagaimana Cara Kerjanya?", size=36, color=TITLE, weight=BOLD)
        title.to_edge(UP, buff=0.4)
        self.play(Write(title), run_time=0.6)
        self.wait(0.2)

        def make_box(text_lines, color, w=2.2, h=1.0):
            """Helper: box with centered text."""
            box = RoundedRectangle(
                width=w, height=h,
                corner_radius=0.12,
                stroke_color=color, stroke_width=2,
                fill_color=color, fill_opacity=0.1,
            )
            txt = T(text_lines, size=18, color=TITLE)
            txt.move_to(box)
            return VGroup(box, txt)

        def arrow_between(left_obj, right_obj, color=MUTED):
            """Arrow from right edge of left_obj to left edge of right_obj."""
            start = left_obj.get_right() + RIGHT * 0.15
            end = right_obj.get_left() + LEFT * 0.15
            arr = Arrow(
                start, end,
                stroke_width=2.5,
                stroke_color=color,
                max_tip_length_to_length_ratio=0.08,
            )
            return arr

        # Row 1: Input
        input_box = make_box("📄\nInput RUU", ACCENT, w=2.0, h=1.2)
        input_box.shift(LEFT * 5.5 + UP * 0.5)

        # Row 1: BIG LLM
        big_box = make_box("🧠 BIG\nQwen3.5-27B", PRIMARY, w=2.2, h=1.2)
        big_box.shift(LEFT * 2.0 + UP * 0.5)

        # Row 1: pasal.id
        pasal_box = make_box("📜\npasal.id", SECONDARY, w=2.0, h=1.2)
        pasal_box.shift(RIGHT * 1.2 + UP * 0.5)

        # Row 2: SMALL LLM
        small_box = make_box("🧠 SMALL\nQwen3.5-9B", PRIMARY, w=2.2, h=1.2)
        small_box.shift(LEFT * 1.0 + DOWN * 1.3)

        # Row 2: Output
        output_box = make_box("✅\nHasil Analisis", ACCENT, w=2.0, h=1.2)
        output_box.shift(RIGHT * 3.5 + DOWN * 1.3)

        # Animate in
        self.play(FadeIn(input_box, shift=RIGHT * 0.5), run_time=0.6)
        self.wait(0.15)
        self.play(FadeIn(big_box, shift=RIGHT * 0.5), run_time=0.6)
        self.wait(0.15)

        # Arrow: input → BIG
        arr1 = arrow_between(input_box, big_box)
        self.play(Create(arr1), run_time=0.3)

        self.play(FadeIn(pasal_box, shift=RIGHT * 0.5), run_time=0.6)
        arr2 = arrow_between(big_box, pasal_box)
        self.play(Create(arr2), run_time=0.3)
        self.wait(0.3)

        self.play(FadeIn(small_box, shift=UP * 0.5), run_time=0.6)
        # Arrow: BIG → SMALL (down-left)
        arr3 = Arrow(
            big_box.get_bottom() + DOWN * 0.15,
            small_box.get_top() + UP * 0.15,
            stroke_width=2.5, stroke_color=MUTED,
            max_tip_length_to_length_ratio=0.08,
        )
        self.play(Create(arr3), run_time=0.3)

        # Arrow: SMALL → Output (right)
        arr4 = Arrow(
            small_box.get_right() + RIGHT * 0.15,
            output_box.get_left() + LEFT * 0.15,
            stroke_width=2.5, stroke_color=MUTED,
            max_tip_length_to_length_ratio=0.08,
        )
        self.play(FadeIn(output_box, shift=RIGHT * 0.5), run_time=0.6)
        self.play(Create(arr4), run_time=0.3)

        self.wait(0.5)

        # Arrow: pasal.id → SMALL (feed back)
        arr5 = Arrow(
            pasal_box.get_bottom() + DOWN * 0.15,
            small_box.get_right() + RIGHT * 0.5,
            stroke_width=2, stroke_color=SECONDARY,
            max_tip_length_to_length_ratio=0.08,
        )
        # Curve it by adding a path
        self.play(Create(arr5), run_time=0.4)

        # Value text
        value = T("Hasil lengkap dalam hitungan menit ⚡", size=28, color=SECONDARY, weight=BOLD)
        value.to_edge(DOWN, buff=0.5)
        self.play(Write(value), run_time=0.8)
        self.wait(2.0)

        self.play(FadeOut(VGroup(
            title, input_box, big_box, pasal_box, small_box, output_box,
            arr1, arr2, arr3, arr4, arr5, value,
        )), run_time=0.5)


# ═══════════════════════════════════════════════════════════════════════════
# Scene 4 — Free & Open (Closing)
# ═══════════════════════════════════════════════════════════════════════════

class Scene4_Closing(Scene):
    def construct(self):
        self.camera.background_color = BG

        # Token icons — spread wider
        hf_token = T("🔑 HF Token", size=32, color=PRIMARY, weight=BOLD)
        pasal_token = T("📜 pasal.id Token", size=32, color=SECONDARY, weight=BOLD)

        hf_token.shift(LEFT * 3.5 + UP * 0.8)
        pasal_token.shift(RIGHT * 3.5 + UP * 0.8)

        self.play(FadeIn(hf_token, shift=UP * 0.5), run_time=0.6)
        self.wait(0.2)
        self.play(FadeIn(pasal_token, shift=UP * 0.5), run_time=0.6)
        self.wait(0.3)

        # Tagline — centered below both tokens
        byo = T("Bawa token sendiri. Buka di GitHub.", size=26, color=BODY)
        byo.shift(DOWN * 0.5)
        self.play(Write(byo), run_time=0.8)
        self.wait(0.3)

        # Links
        gh = T("github.com/pebaryan/Legawa", size=20, color=ACCENT)
        hf = T("build-small-hackathon/legawa", size=20, color=ACCENT)
        gh.to_edge(DOWN, buff=0.8)
        hf.next_to(gh, DOWN, buff=0.2)

        self.play(
            Write(gh), Write(hf),
            run_time=0.6,
        )
        self.wait(0.5)

        # Final brand
        final = T("🏛️ Legawa — small models, big adventure 🏕️", size=34, color=SECONDARY, weight=BOLD)
        final.to_edge(UP, buff=1.5)
        self.play(Write(final), run_time=1.0)
        self.wait(2.0)

        # Clean exit
        self.play(*[FadeOut(mob) for mob in self.mobjects], run_time=0.5)
