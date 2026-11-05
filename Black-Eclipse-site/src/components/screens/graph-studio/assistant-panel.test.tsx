import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AssistantPanel } from './assistant-panel';

// The vitest environment is `node`, so this is an SSR smoke test: the panel must
// render its empty state and the run/fix affordance without any browser APIs.
describe('AssistantPanel', () => {
  it('renders the empty state and the run/fix prompt', () => {
    const html = renderToStaticMarkup(<AssistantPanel />);
    expect(html).toContain('Assistant');
    expect(html).toContain('Build on this workflow');
    expect(html).toContain('Run it and fix any errors');
    expect(html).toContain('Auto-apply');
  });
});
