import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { StrategyStudioScreen } from './strategy-studio-screen';

describe('StrategyStudioScreen', () => {
  it('renders the AI thesis input and the paper guardrail', () => {
    const html = renderToStaticMarkup(<StrategyStudioScreen />);
    expect(html).toContain('Draft with AI');
    expect(html).toContain('Paper deployment');
    expect(html).toContain('Approve and deploy to paper');
    expect(html).toContain('Every fill, metric and drawdown is computed by the Eclipse quant engine');
  });

  it('renders the workspace rails: library, stages, data coverage and experiments', () => {
    const html = renderToStaticMarkup(<StrategyStudioScreen />);
    expect(html).toContain('Saved strategies');
    expect(html).toContain('Data coverage');
    expect(html).toContain('Experiments');
    expect(html).toContain('Idea');
    expect(html).toContain('Prove');
    expect(html).toContain('paper only');
  });

  it('offers templates that are labelled as examples', () => {
    const html = renderToStaticMarkup(<StrategyStudioScreen />);
    expect(html).toContain('Start from a template');
    expect(html).toContain('Templates are examples, not recommendations.');
  });

  it('offers a share link and a project binding', () => {
    const html = renderToStaticMarkup(<StrategyStudioScreen />);
    expect(html).toContain('Share');
    expect(html).toContain('Project');
    expect(html).toContain('Save and run a strategy first');
  });

  it('offers an opt-in provider check beside the stored catalogue', () => {
    const html = renderToStaticMarkup(<StrategyStudioScreen />);
    expect(html).toContain('Check providers');
    expect(html).toContain('contacts providers');
  });

  it('offers a portfolio backtest over saved strategies', () => {
    const html = renderToStaticMarkup(<StrategyStudioScreen />);
    expect(html).toContain('Portfolio backtest');
    expect(html).toContain('Select at least two strategies.');
  });

  it('renders a compact summary for small screens', () => {
    const html = renderToStaticMarkup(<StrategyStudioScreen />);
    expect(html).toContain('Strategy summary');
  });

  it('states that a paper deployment is not forward-looking', () => {
    const html = renderToStaticMarkup(<StrategyStudioScreen />);
    expect(html).toContain('it is not forward-looking');
  });
});
