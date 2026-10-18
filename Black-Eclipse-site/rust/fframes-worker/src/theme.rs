//! Visual constants and shared building blocks for the storyboard scene library.

use fframes::animation::Easing;
use fframes::{Frame, Svgr};

pub const W: f32 = 1920.0;
pub const MARGIN: f32 = 160.0;

pub const SANS: &str = "Segoe UI";
pub const MONO: &str = "Consolas";

pub const FG: &str = "#f8fafc";
pub const MUTED: &str = "#94a3b8";
pub const DIM: &str = "#64748b";
pub const LINE: &str = "#1e293b";
pub const PANEL: &str = "#0e0e18";
pub const GREEN: &str = "#22c55e";
pub const RED: &str = "#ef4444";
pub const DEFAULT_ACCENT: &str = "#3b82f6";

/// The shared dark gradient painted under every scene. The id is unique per
/// scene because two scenes composite into ONE document during a fade overlap.
pub fn background<'a>(scene_index: usize) -> Svgr<'a> {
    let gradient_id = format!("sb-bg-{scene_index}");
    let gradient_url = format!("url(#{gradient_id})");
    fframes::svgr!(
        <g>
            <defs>
                <linearGradient id={gradient_id} x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0" stop-color="#0a0a12" />
                    <stop offset="1" stop-color="#141126" />
                </linearGradient>
            </defs>
            <rect width="1920" height="1080" fill={gradient_url} />
        </g>
    )
}

/// The content-scene header: an accent rail plus the scene title.
pub fn header<'a>(frame: &mut Frame, title: &'a str, accent: &'a str) -> Svgr<'a> {
    let bar_opacity = frame.animate(&fframes::timeline!(
        at 0.15 => 0.7, animate 0.0 => 1.0, Easing::EaseOut,
    ));
    let title_opacity = frame.animate(&fframes::timeline!(
        at 0.2 => 0.8, animate 0.0 => 1.0, Easing::EaseOut,
    ));
    let title_dy = frame.animate(&fframes::timeline!(
        at 0.2 => 0.8, animate 14.0 => 0.0, Easing::EaseOut,
    ));
    fframes::svgr!(
        <g>
            <rect x="160" y="112" width="44" height="7" rx="3.5" fill={accent} opacity={bar_opacity} />
            <text
                x="160" y={196.0 + title_dy}
                font-family="Segoe UI" font-size="56" font-weight="600" fill="#f8fafc"
                opacity={title_opacity}
            >
                {title}
            </text>
        </g>
    )
}

/// A rounded dark panel.
pub fn panel<'a>(x: f32, y: f32, w: f32, h: f32, stroke: &'a str, stroke_width: f32) -> Svgr<'a> {
    fframes::svgr!(
        <rect
            x={x} y={y} width={w} height={h} rx="24"
            fill={PANEL} stroke={stroke} stroke-width={stroke_width}
        />
    )
}

/// Compact display for price-like numbers (`68,240.5`-free, plain decimals).
pub fn fmt_number(value: f64) -> String {
    if value.abs() >= 1000.0 {
        format!("{value:.0}")
    } else {
        format!("{value:.2}")
    }
}

/// The per-scene data-provenance footer for bound scenes (Phase 5): the source
/// line, and an explicit STALE marker when the gateway flagged the data.
pub fn evidence_footer<'a>(
    frame: &mut Frame,
    evidence: Option<&'a crate::spec::SceneEvidence>,
) -> Svgr<'a> {
    let Some(evidence) = evidence else {
        return Svgr::empty();
    };
    let line = format!("Source: {}", evidence.source_line);
    let opacity: f32 = frame.animate(&fframes::timeline!(
        at 0.6 => 1.2, animate 0.0 => 1.0, Easing::EaseOut,
    ));
    let stale_opacity: f32 = if evidence.stale { opacity } else { 0.0 };
    fframes::svgr!(
        <g opacity={opacity}>
            <rect x="160" y="1000" width="96" height="30" rx="6" fill="#3a2a0a" opacity={stale_opacity} />
            <text
                x="208" y="1021" text-anchor="middle" font-family={MONO} font-size="19"
                fill="#fbbf24" opacity={stale_opacity}
            >
                "STALE"
            </text>
            <text x="160" y="1048" font-family={MONO} font-size="21" fill={DIM}>{line}</text>
        </g>
    )
}
