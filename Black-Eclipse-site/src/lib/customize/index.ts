// Customization kernel — one layout engine for every customizable page.
// Pages register a PageDefinition and consume useCustomize(); shared visuals
// (WidthPicker, TemplateMiniGrid) live in components.tsx.
export * from './types';
export * from './layout';
export * from './use-customize';
export * from './components';
export * from './fund-page-def';
export * from './coach-mark';