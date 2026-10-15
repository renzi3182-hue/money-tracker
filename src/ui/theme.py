"""Token del design system Soft Glass, stessi valori di code/macro-cycle-tracker/src/ui/theme.py e .streamlit/config.toml.

Copia e non import: i due software si deployano separati."""
import altair as alt

TOKENS = {
    "dark": {
        "bg": "#0F1720", "surface": "#172330", "raised": "#1E2D3D", "fg": "#EAF2F5", "muted": "#8FA6B2",
        "line": "#25384A", "accent": "#5EEAD4", "on-accent": "#062B26",
        "r-gold": "#7BE0A4", "r-defl": "#8AB4FF", "r-refl": "#FFC878", "r-stag": "#FF9DA7",
        "shadow": "0 8px 24px rgba(0,0,0,.35)",
    },
    "light": {
        "bg": "#F3F8F8", "surface": "#FFFFFF", "raised": "#E6F0F1", "fg": "#0F1720", "muted": "#4F6472",
        "line": "#D3E2E6", "accent": "#0A7F70", "on-accent": "#FFFFFF",
        "r-gold": "#177A4D", "r-defl": "#2F6DB5", "r-refl": "#8F5A05", "r-stag": "#C0394B",
        "shadow": "0 4px 16px rgba(15,23,32,.08)",
    },
}
# Ordine categoriale da chartCategoricalColors in .streamlit/config.toml
CATEGORICAL = {
    "dark": ["#5EEAD4", "#8AB4FF", "#FFC878", "#FF9DA7", "#7BE0A4", "#C4A8FF", "#8FA6B2"],
    "light": ["#0A7F70", "#2F6DB5", "#8F5A05", "#C0394B", "#177A4D", "#6B4FB8", "#4F6472"],
}


def hex_color(mode: str, token: str) -> str:
    return TOKENS.get(mode, TOKENS["dark"])[token]


def categorical(mode: str) -> list[str]:
    return CATEGORICAL.get(mode, CATEGORICAL["dark"])


def chart(c: alt.Chart, mode: str, height: int = 300) -> alt.Chart:
    """Stile comune dei grafici, come _chart in macro-cycle-tracker/src/ui/tool_pages.py."""
    muted, line = hex_color(mode, "muted"), hex_color(mode, "line")
    return (c.properties(height=height, background="transparent")
            .configure_view(strokeWidth=0)
            .configure_axis(labelColor=muted, titleColor=muted, gridColor=line, domainColor=line, tickColor=line,
                            labelFont="DM Mono", titleFont="Plus Jakarta Sans", titleFontWeight=500)
            .configure_legend(labelColor=muted, titleColor=muted, orient="top", labelFont="Plus Jakarta Sans"))


def page_css(mode: str) -> str:
    t = TOKENS.get(mode, TOKENS["dark"])
    return ("<style>:root { " + " ".join(f"--{k}: {v};" for k, v in t.items()) + " }"
            "[data-testid='stMetricValue'] { font-family: 'DM Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }"
            "[data-testid='stMetric'] { background: var(--surface); border: 1px solid var(--line); border-radius: 18px;"
            " padding: 16px 20px; box-shadow: var(--shadow); }"
            # Telefono (sotto 640px Streamlit impila le colonne): meno spazio vuoto, metriche impilate più basse
            "@media (max-width: 640px) {"
            " [data-testid='stMainBlockContainer'] { padding: 4rem 1rem 3rem !important; }"
            " h1 { font-size: 28px !important; }"
            " [data-testid='stMetric'] { padding: 10px 14px; border-radius: 14px; }"
            " [data-testid='stMetricValue'] { font-size: 1.6rem !important; } }</style>")
