//! The storyboard scene library: seven scene types composed from typed spec
//! parameters, rendered on the shared dark theme.

mod candlestick;
mod comparison;
mod intro;
mod metric;
mod outro;
mod quote;
mod timeline;

use fframes::{
    AudioMap, Color, Duration, FFramesContext, FontQuery, Frame, Overlap, Scene, Scenes, Svgr,
    TextOverflow, Video,
};

use crate::spec;
use crate::theme;

#[derive(Debug)]
pub struct StoryboardScene {
    pub spec: spec::SceneSpec,
    pub index: usize,
    pub accent: String,
}

impl Scene for StoryboardScene {
    fn duration(&self) -> Duration<'_> {
        Duration::Seconds(self.spec.duration_seconds)
    }

    fn overlap(&self) -> Overlap {
        if self.spec.is_fade() {
            Overlap::Previous(0.4)
        } else {
            Overlap::None
        }
    }

    fn name(&self) -> &'static str {
        match self.spec.kind.as_str() {
            "intro" => "Intro",
            "metric" => "Metric",
            "candlestick" => "Candlestick",
            "comparison" => "Comparison",
            "timeline" => "Timeline",
            "quote" => "Quote",
            "outro" => "Outro",
            _ => "Scene",
        }
    }

    fn render_frame<'a>(&'a self, mut frame: Frame, ctx: &FFramesContext<'a, '_>) -> Svgr<'a> {
        match self.spec.kind.as_str() {
            "intro" => intro::render(self, &mut frame, ctx),
            "metric" => metric::render(self, &mut frame, ctx),
            "candlestick" => candlestick::render(self, &mut frame, ctx),
            "comparison" => comparison::render(self, &mut frame, ctx),
            "timeline" => timeline::render(self, &mut frame, ctx),
            "quote" => quote::render(self, &mut frame, ctx),
            "outro" => outro::render(self, &mut frame, ctx),
            _ => fframes::svgr!(<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080" />),
        }
    }
}

#[derive(Debug)]
pub struct StoryboardVideo {
    pub scenes: Vec<StoryboardScene>,
}

impl Video for StoryboardVideo {
    const FPS: usize = 30;
    const WIDTH: usize = 1920;
    const HEIGHT: usize = 1080;
    const BACKGROUND_COLOR: Color = Color::BLACK;

    fn duration(&self) -> Duration<'_> {
        Duration::Auto
    }

    fn audio(&self) -> AudioMap<'_> {
        AudioMap::none()
    }

    fn define_scenes(&self) -> Scenes<'_> {
        let scenes: Vec<&dyn Scene> = self.scenes.iter().map(|scene| scene as &dyn Scene).collect();
        Scenes::from(scenes)
    }

    fn render_frame<'a>(&'a self, frame: Frame, ctx: &FFramesContext<'a, '_>) -> Svgr<'a> {
        ctx.render_scenes(&frame)
    }
}

/// Build the renderable video from a validated storyboard.
pub fn build_video(storyboard: spec::Storyboard) -> Result<StoryboardVideo, String> {
    let accent = storyboard.style.accent_color()?;
    let scenes = storyboard
        .scenes
        .into_iter()
        .enumerate()
        .map(|(index, scene)| StoryboardScene { spec: scene, index, accent: accent.clone() })
        .collect();
    Ok(StoryboardVideo { scenes })
}

/// Fit a single-line label to a pixel width (ellipsis) using the live font db.
pub(super) fn fit<'a>(
    frame: &mut Frame,
    ctx: &FFramesContext<'a, '_>,
    text: &'a str,
    size: usize,
    weight: u16,
    max_width: f32,
) -> String {
    let font = FontQuery { family: theme::SANS, size, weight, ..Default::default() };
    frame
        .text_fit(ctx, font, text, max_width.max(24.0) as usize, TextOverflow::Ellipsis)
        .map(|fitted| fitted.into_owned())
        .unwrap_or_else(|| text.to_owned())
}
