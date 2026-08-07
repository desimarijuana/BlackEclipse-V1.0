# Contributing to BlackEclipse

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

1. Fork and clone the repository
2. Run `npm install`
3. Run `npm run dev` and open http://localhost:3000

No API keys or database are required — the app runs on demo data.

## Code Style

- TypeScript, strict mode
- Components live in `src/components/` organized by domain (`screens/`, `layout/`, `chat/`, `ui/`)
- Reusable UI primitives go in `src/components/ui/`
- Use named exports, not default exports
- Run `npm run lint` before committing

## Pull Request Process

1. Ensure your code builds: `npm run build`
2. Update the README if your change affects usage
3. Add tests for new logic where practical
4. Your PR will be reviewed

## Reporting Issues

- Include the browser/OS you're using
- Describe the expected vs. actual behavior
- If it's a visual bug, a screenshot helps
