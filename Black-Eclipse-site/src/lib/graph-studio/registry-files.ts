// Local file node contracts: an uploaded file becomes a graph input, parses into
// text/rows, and exports rows back to a downloadable local asset.
//
// The bytes live in the bounded graph asset store. These contracts carry only a
// stable `assetId` + metadata, never the file itself.

import { z } from 'zod';
import type { ExecutionMode, NodeDefinition, PortDef } from './types';

const ALL_MODES: ExecutionMode[] = ['research', 'backtest', 'paper', 'live'];

export const FILE_PARSE_KINDS = ['auto', 'text', 'json', 'csv', 'tsv', 'xlsx', 'binary'] as const;
export const FILE_EXPORT_FORMATS = ['csv', 'json', 'xlsx'] as const;

function port(p: PortDef): PortDef {
  return { kind: 'data', ...p };
}

export const FILE_DEFINITIONS: NodeDefinition[] = [
  {
    type: 'data.file.attach',
    version: '1.0.0',
    category: 'data',
    label: 'File',
    description: 'Turns an uploaded local file into text or rows.',
    icon: 'text',
    inputs: [],
    outputs: [
      port({ id: 'file', name: 'File', type: 'file' }),
      port({ id: 'text', name: 'Text', type: 'string', nullable: true }),
      port({ id: 'rows', name: 'Rows', type: 'array', nullable: true }),
      port({ id: 'meta', name: 'Meta', type: 'object' }),
    ],
    configSchema: z.object({
      assetId: z.string().max(80).default(''),
      parseAs: z.enum(FILE_PARSE_KINDS).default('auto'),
      delimiter: z.string().max(4).default(','),
      header: z.boolean().default(true),
      maxRows: z.number().int().min(1).max(20_000).default(5_000),
      encoding: z.string().max(40).default('utf-8-sig'),
    }),
    defaultConfig: () => ({
      assetId: '', parseAs: 'auto', delimiter: ',', header: true,
      maxRows: 5_000, encoding: 'utf-8-sig',
    }),
    capabilities: ['asset.read'],
    sideEffects: 'read',
    allowedModes: ALL_MODES,
    docs: 'Upload a CSV/TSV/JSON/XLSX/text file in the inspector. Bytes live in the bounded graph asset store; config carries only the ref and metadata. Rows and the cell count are capped; truncation is reported. A missing or expired file fails by name.',
  },
  {
    type: 'data.file.parse',
    version: '1.0.0',
    category: 'data',
    label: 'Parse file',
    description: 'Parses a file reference into rows, columns and text.',
    icon: 'text',
    inputs: [port({ id: 'file', name: 'File', type: 'file', optional: true })],
    outputs: [
      port({ id: 'rows', name: 'Rows', type: 'array', nullable: true }),
      port({ id: 'columns', name: 'Columns', type: 'array' }),
      port({ id: 'text', name: 'Text', type: 'string', nullable: true }),
      port({ id: 'meta', name: 'Meta', type: 'object' }),
    ],
    configSchema: z.object({
      assetId: z.string().max(80).default(''),
      parseAs: z.enum(FILE_PARSE_KINDS).default('auto'),
      delimiter: z.string().max(4).default(','),
      header: z.boolean().default(true),
      maxRows: z.number().int().min(1).max(20_000).default(5_000),
      encoding: z.string().max(40).default('utf-8-sig'),
      sheet: z.string().max(120).default(''),
    }),
    defaultConfig: () => ({
      assetId: '', parseAs: 'auto', delimiter: ',', header: true,
      maxRows: 5_000, encoding: 'utf-8-sig', sheet: '',
    }),
    capabilities: ['asset.read'],
    sideEffects: 'read',
    allowedModes: ALL_MODES,
    docs: 'Same parser as File, for a File reference produced upstream. Choose a sheet for an Excel workbook; blank uses the first sheet.',
  },
  {
    type: 'data.file.export',
    version: '1.0.0',
    category: 'data',
    label: 'Export file',
    description: 'Exports rows to a downloadable local CSV, JSON or Excel file.',
    icon: 'text',
    inputs: [
      port({ id: 'in', name: 'Run', type: 'any', kind: 'control', optional: true }),
      port({ id: 'rows', name: 'Rows', type: 'any', optional: true }),
    ],
    outputs: [
      port({ id: 'artifact', name: 'Artifact', type: 'object' }),
      port({ id: 'name', name: 'Name', type: 'string' }),
      port({ id: 'bytes', name: 'Bytes', type: 'number' }),
    ],
    configSchema: z.object({
      format: z.enum(FILE_EXPORT_FORMATS).default('csv'),
      name: z.string().max(200).default('export'),
      includeHeader: z.boolean().default(true),
      rowsJson: z.string().max(1_000_000).default(''),
      maxRows: z.number().int().min(1).max(20_000).default(5_000),
    }),
    defaultConfig: () => ({
      format: 'csv', name: 'export', includeHeader: true, rowsJson: '', maxRows: 5_000,
    }),
    capabilities: ['asset.write'],
    sideEffects: 'local_write',
    allowedModes: ALL_MODES,
    docs: 'Local write, not an external effect: a test run may export. Distinct from file.write, which writes into an operator-granted scope. The Artifact output is a local asset reference with a download route.',
  },
];
