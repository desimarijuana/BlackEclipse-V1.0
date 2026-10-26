import { describe, expect, it } from 'vitest';
import { parseColumns } from './store';

describe('user data table columns', () => {
  it('parses valid columns and assigns stable ids/type fallbacks', () => {
    const columns = parseColumns(JSON.stringify([
      { id: 'a', name: 'Name', type: 'string' },
      { name: 'Qty', type: 'number' },
      { id: 'a', name: 'Duplicate id', type: 'not-a-type' },
    ]));
    expect(columns).toHaveLength(3);
    expect(columns[0]).toEqual({ id: 'a', name: 'Name', type: 'string' });
    expect(columns[1].name).toBe('Qty');
    expect(columns[1].type).toBe('number');
    expect(columns[1].id).not.toBe('a');
    expect(columns[2].id).not.toBe('a');
    expect(columns[2].type).toBe('string');
  });

  it('drops malformed rows and survives corrupt JSON', () => {
    expect(parseColumns('{not json')).toEqual([]);
    expect(parseColumns(JSON.stringify([null, 3, { name: '   ' }, { name: 'Ok' }]))).toEqual([
      expect.objectContaining({ name: 'Ok' }),
    ]);
  });
});
