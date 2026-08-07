from PyQt6.QtGui import QColor

class Theme:
    """Theme manager for Lessan AI."""
    
    # Galaxy Diamond Nebula palette
    BG          = "#030212"
    BG_GRAD     = "#0d0824"
    NEBULA_A    = "#1c0b44"
    NEBULA_B    = "#062433"
    NEBULA_C    = "#3b0a3a"

    PANEL       = "#0f0c26"
    PANEL_GLASS = "#161239"
    CARD        = "#1b1749"
    BORDER      = "#292363"
    BORDER_L    = "#4139a3"
    GLOW        = "#7c6cff"

    PRIMARY     = "#8b5cf6"
    PRIMARY_L   = "#c4b5fd"
    PRIMARY_D   = "#6d28d9"
    ACCENT      = "#22d3ee"
    ACCENT_L    = "#8cf1ff"
    SUCCESS     = "#34d399"
    SUCCESS_L   = "#8ff5d8"
    WARNING     = "#ffd166"
    WARNING_L   = "#ffe9ad"
    ERROR       = "#ff5c8a"
    ERROR_L     = "#ff9dbb"
    ERROR_D     = "#c9204f"

    MAGENTA     = "#ff7ac6"
    GOLD        = "#ffd700"

    PRISM = [
        "#8b5cf6", "#22d3ee", "#ff7ac6", "#ffd166",
        "#34d399", "#7c6cff", "#ff5c8a", "#67e8f9",
    ]

    TEXT        = "#f4f1ff"
    TEXT_D      = "#bdb7ec"
    TEXT_M      = "#847dc0"
    TEXT_DIM    = "#4d478a"
    WHITE       = "#ffffff"

    SPECULAR    = "#ffffff"
    RIM         = "#dcd3ff"
    SHADOW      = "#000000"

    GLASS       = "#10f1ccea"
    GLASS_B     = "#5fbe5212"
    GRAD_START  = "#8b5cf6"
    GRAD_END    = "#22d3ee"

    MUTED_C     = "#ff5c8a"
    SPEAKING_C  = "#ff7ac6"

    @staticmethod
    def qcol(h: str, a: int = 255) -> QColor:
        c = QColor(h)
        c.setAlpha(max(0, min(255, a)))
        return c

# Global instance
theme = Theme()