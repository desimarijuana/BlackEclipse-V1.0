// ── UI Engineering — public API ──────────────────────────────────────────────
// The pure, framework-agnostic foundation of Eclipse's AI-native UI layer:
// the component catalog (what can be composed), the declarative blueprint
// (what is composed), the mutation engine (how it changes), revisions/diff
// (how it is audited and recovered) and the durable store. The agent tools and
// the UI Builder both build on this surface.
export * from './catalog';
export * from './blueprint';
export * from './patches';
export * from './revisions';
export * from './store';
