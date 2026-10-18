//! The storyboard project spec (schemaVersion 2).
//!
//! The Python layer authors and fully validates specs (`video/spec.py`); this
//! module re-checks the load-bearing bounds so a malformed or hand-edited spec
//! can never panic a render — it becomes a clear, non-zero-exit error instead.

use std::path::Path;

use serde::Deserialize;

pub const SCHEMA_VERSION: u32 = 3;
pub const MIN_SCENES: usize = 1;
pub const MAX_SCENES: usize = 12;
pub const MIN_SCENE_SECONDS: f32 = 1.0;
pub const MAX_SCENE_SECONDS: f32 = 30.0;
pub const MAX_TOTAL_SECONDS: f32 = 300.0;
pub const KINDS: [&str; 7] = [
    "intro", "metric", "candlestick", "comparison", "timeline", "quote", "outro",
];

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Storyboard {
    pub schema_version: u32,
    pub format: String,
    #[serde(default)]
    pub style: Style,
    pub scenes: Vec<SceneSpec>,
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct Style {
    #[serde(default)]
    pub theme: Option<String>,
    #[serde(default)]
    pub accent: Option<String>,
}

impl Style {
    /// The accent color, validated as `#RRGGBB` (invalid values refuse the spec).
    pub fn accent_color(&self) -> Result<String, String> {
        match &self.accent {
            None => Ok(crate::theme::DEFAULT_ACCENT.to_string()),
            Some(value) if is_hex_color(value) => Ok(value.clone()),
            Some(value) => Err(format!("style.accent must be #RRGGBB, got {value:?}")),
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SceneSpec {
    #[serde(rename = "type")]
    pub kind: String,
    pub duration_seconds: f32,
    #[serde(default)]
    pub transition: Option<String>,
    // intro / outro
    pub title: Option<String>,
    pub subtitle: Option<String>,
    // metric
    #[serde(default)]
    pub metrics: Vec<Metric>,
    // candlestick
    pub symbol: Option<String>,
    #[serde(default)]
    pub candles: Vec<Candle>,
    // comparison
    pub left: Option<PaneData>,
    pub right: Option<PaneData>,
    pub winner: Option<String>,
    // timeline
    #[serde(default)]
    pub events: Vec<EventItem>,
    // quote
    pub text: Option<String>,
    pub attribution: Option<String>,
    // resolver-attached provenance for bound scenes (schemaVersion 3)
    pub evidence: Option<SceneEvidence>,
}

/// The data-provenance footer the resolver attaches to scenes whose figures
/// came from the Market Data Gateway. The worker only DRAWS it — the resolver
/// owns the truth.
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SceneEvidence {
    pub source_line: String,
    #[serde(default)]
    pub stale: bool,
    #[serde(default)]
    pub sources: Vec<String>,
}

impl SceneSpec {
    pub fn is_fade(&self) -> bool {
        matches!(self.transition.as_deref(), Some("fade"))
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct Candle {
    #[allow(clippy::struct_field_names)]
    pub o: f64,
    pub h: f64,
    pub l: f64,
    pub c: f64,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Metric {
    pub label: String,
    pub value: String,
    pub delta: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PaneData {
    pub label: String,
    pub value: String,
    pub detail: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct EventItem {
    pub label: String,
    pub detail: Option<String>,
}

fn is_hex_color(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() == 7
        && bytes[0] == b'#'
        && bytes[1..].iter().all(|b| b.is_ascii_hexdigit())
}

pub fn load(path: &Path) -> Result<Storyboard, String> {
    let text = std::fs::read_to_string(path)
        .map_err(|error| format!("cannot read the project spec {path:?}: {error}"))?;
    let storyboard: Storyboard = serde_json::from_str(&text)
        .map_err(|error| format!("invalid project spec JSON: {error}"))?;
    storyboard.validate()?;
    Ok(storyboard)
}

impl Storyboard {
    pub fn validate(&self) -> Result<(), String> {
        if !(2..=SCHEMA_VERSION).contains(&self.schema_version) {
            return Err(format!(
                "unsupported schemaVersion {} (this worker renders schemaVersion 2 and {SCHEMA_VERSION})",
                self.schema_version
            ));
        }
        if self.format != "landscape" {
            return Err(format!(
                "unsupported format {:?} (only `landscape` — 1920x1080@30 — is implemented)",
                self.format
            ));
        }
        if let Some(theme) = self.style.theme.as_deref() {
            if theme != "dark" {
                return Err(format!("unsupported theme {theme:?} (only `dark` is implemented)"));
            }
        }
        if self.scenes.len() < MIN_SCENES || self.scenes.len() > MAX_SCENES {
            return Err(format!(
                "a storyboard needs {MIN_SCENES}-{MAX_SCENES} scenes, got {}",
                self.scenes.len()
            ));
        }
        let mut total = 0.0_f32;
        for (index, scene) in self.scenes.iter().enumerate() {
            scene.validate(index)?;
            total += scene.duration_seconds;
        }
        if total > MAX_TOTAL_SECONDS {
            return Err(format!(
                "the storyboard totals {total:.1}s; the cap is {MAX_TOTAL_SECONDS:.0}s"
            ));
        }
        Ok(())
    }
}

impl SceneSpec {
    fn validate(&self, index: usize) -> Result<(), String> {
        let at = |detail: &str| format!("scenes[{index}]: {detail}");
        if !KINDS.contains(&self.kind.as_str()) {
            return Err(at(&format!("unknown scene type {:?}", self.kind)));
        }
        if !(MIN_SCENE_SECONDS..=MAX_SCENE_SECONDS).contains(&self.duration_seconds)
            || !self.duration_seconds.is_finite()
        {
            return Err(at(&format!(
                "durationSeconds must be {MIN_SCENE_SECONDS}-{MAX_SCENE_SECONDS}, got {}",
                self.duration_seconds
            )));
        }
        if self.is_fade() || self.transition.is_none() || self.transition.as_deref() == Some("cut") {
        } else {
            return Err(at(&format!(
                "unknown transition {:?} (use `cut` or `fade`)",
                self.transition.as_deref().unwrap_or("")
            )));
        }
        let has = |value: &Option<String>| {
            value.as_deref().map(str::trim).is_some_and(|text| !text.is_empty())
        };
        match self.kind.as_str() {
            "intro" | "outro" => {
                if !has(&self.title) {
                    return Err(at("a title is required"));
                }
            }
            "metric" => {
                if !has(&self.title) {
                    return Err(at("a title is required"));
                }
                if self.metrics.is_empty() || self.metrics.len() > 4 {
                    return Err(at("metrics must contain 1-4 entries"));
                }
                for (metric_index, metric) in self.metrics.iter().enumerate() {
                    if metric.label.trim().is_empty() || metric.value.trim().is_empty() {
                        return Err(at(&format!("metrics[{metric_index}] needs a label and a value")));
                    }
                }
            }
            "candlestick" => {
                if !has(&self.title) {
                    return Err(at("a title is required"));
                }
                if !has(&self.symbol) {
                    return Err(at("a symbol is required"));
                }
                if self.candles.len() < 2 || self.candles.len() > 60 {
                    return Err(at("candles must contain 2-60 entries"));
                }
                for (candle_index, candle) in self.candles.iter().enumerate() {
                    let values = [candle.o, candle.h, candle.l, candle.c];
                    if values.iter().any(|value| !value.is_finite()) {
                        return Err(at(&format!("candles[{candle_index}] has a non-finite value")));
                    }
                    if candle.h < candle.o.max(candle.c) || candle.l > candle.o.min(candle.c) {
                        return Err(at(&format!(
                            "candles[{candle_index}] is inconsistent (h >= max(o,c), l <= min(o,c))"
                        )));
                    }
                }
            }
            "comparison" => {
                if !has(&self.title) {
                    return Err(at("a title is required"));
                }
                if self.left.is_none() || self.right.is_none() {
                    return Err(at("both `left` and `right` panes are required"));
                }
                if let Some(winner) = self.winner.as_deref() {
                    if winner != "left" && winner != "right" {
                        return Err(at(&format!("winner must be `left` or `right`, got {winner:?}")));
                    }
                }
            }
            "timeline" => {
                if !has(&self.title) {
                    return Err(at("a title is required"));
                }
                if self.events.len() < 2 || self.events.len() > 6 {
                    return Err(at("events must contain 2-6 entries"));
                }
                for (event_index, event) in self.events.iter().enumerate() {
                    if event.label.trim().is_empty() {
                        return Err(at(&format!("events[{event_index}] needs a label")));
                    }
                }
            }
            "quote" => {
                if !has(&self.text) {
                    return Err(at("quote text is required"));
                }
            }
            _ => {}
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scene(kind: &str) -> SceneSpec {
        SceneSpec {
            kind: kind.to_string(),
            duration_seconds: 3.0,
            transition: None,
            title: Some("Title".into()),
            subtitle: None,
            metrics: Vec::new(),
            symbol: Some("BTC".into()),
            candles: Vec::new(),
            left: None,
            right: None,
            winner: None,
            events: Vec::new(),
            text: Some("Quote".into()),
            attribution: None,
            evidence: None,
        }
    }

    #[test]
    fn accepts_v2_and_v3_and_rejects_the_rest() {
        let mut storyboard = Storyboard {
            schema_version: 2,
            format: "landscape".into(),
            style: Style::default(),
            scenes: vec![scene("intro")],
        };
        assert!(storyboard.validate().is_ok());
        storyboard.schema_version = 3;
        storyboard.scenes[0].evidence = Some(SceneEvidence {
            source_line: "yahoo · daily · retrieved 2026-10-18 03:12 UTC".into(),
            stale: true,
            sources: vec!["yahoo · daily · retrieved 2026-10-18 03:12 UTC".into()],
        });
        assert!(storyboard.validate().is_ok());
        storyboard.schema_version = 4;
        assert!(storyboard.validate().is_err());
    }

    #[test]
    fn rejects_unknown_kind_and_hex() {
        let mut storyboard = Storyboard {
            schema_version: 2,
            format: "landscape".into(),
            style: Style::default(),
            scenes: vec![scene("unknown")],
        };
        assert!(storyboard.validate().is_err());
        storyboard.scenes[0].kind = "intro".into();
        assert!(storyboard.validate().is_ok());
        storyboard.style.accent = Some("blue".into());
        assert!(storyboard.style.accent_color().is_err());
        storyboard.style.accent = Some("#3b82f6".into());
        assert_eq!(storyboard.style.accent_color().unwrap(), "#3b82f6");
    }
}
