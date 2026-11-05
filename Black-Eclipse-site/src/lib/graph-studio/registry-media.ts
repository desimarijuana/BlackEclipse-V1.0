// Vision-read image node contracts.
//
// These nodes READ images through the existing vision engine. They do not render
// charts and they do not generate images. Every output is an observation
// (`verified: false`) unless `image.read_chart` gets a real market-data check.

import { z } from 'zod';
import type { ExecutionMode, NodeDefinition, PortDef } from './types';

const ALL_MODES: ExecutionMode[] = ['research', 'backtest', 'paper', 'live'];

export const IMAGE_ANALYZE_MODES = ['describe', 'answer', 'ground', 'extract'] as const;
export const IMAGE_BATCH_MODES = ['analyze', 'read_chart', 'ocr'] as const;
export const IMAGE_COMPARE_MODES = ['pixel', 'visual', 'both'] as const;
export const MAX_BATCH_IMAGES = 8;

function port(p: PortDef): PortDef {
  return { kind: 'data', ...p };
}

export const MEDIA_DEFINITIONS: NodeDefinition[] = [
  {
    type: 'image.attach',
    version: '1.0.0',
    category: 'media',
    label: 'Image',
    description: 'Uploads or references one local image.',
    icon: 'chart',
    inputs: [],
    outputs: [
      port({ id: 'image', name: 'Image', type: 'image' }),
      port({ id: 'meta', name: 'Meta', type: 'object' }),
    ],
    configSchema: z.object({
      assetId: z.string().max(80).default(''),
      notes: z.string().max(500).default(''),
    }),
    defaultConfig: () => ({ assetId: '', notes: '' }),
    capabilities: ['image.read'],
    sideEffects: 'read',
    allowedModes: ALL_MODES,
    docs: 'Upload a PNG/JPEG/WebP/GIF/BMP/TIFF image in the inspector. The image is content-addressed in the vision asset store; only the asset id is saved in the workflow.',
  },
  {
    type: 'image.analyze',
    version: '1.0.0',
    category: 'media',
    label: 'Analyze image',
    description: 'One bounded vision read: describe, answer, ground or extract JSON.',
    icon: 'chart',
    inputs: [
      port({ id: 'image', name: 'Image', type: 'image', optional: true }),
      port({ id: 'question', name: 'Question', type: 'string', optional: true }),
    ],
    outputs: [
      port({ id: 'description', name: 'Description', type: 'string' }),
      port({ id: 'observations', name: 'Observations', type: 'array' }),
      port({ id: 'data', name: 'Data', type: 'object', nullable: true }),
      port({ id: 'meta', name: 'Meta', type: 'object' }),
    ],
    configSchema: z.object({
      assetId: z.string().max(80).default(''),
      mode: z.enum(IMAGE_ANALYZE_MODES).default('describe'),
      question: z.string().max(4_000).default(''),
      schemaJson: z.string().max(20_000).default(''),
      region: z.string().max(80).default(''),
      maxObservations: z.number().int().min(1).max(200).default(60),
    }),
    defaultConfig: () => ({
      assetId: '', mode: 'describe', question: '', schemaJson: '', region: '', maxObservations: 60,
    }),
    capabilities: ['image.read', 'model.vision'],
    sideEffects: 'model',
    allowedModes: ALL_MODES,
    docs: 'describe returns the engine’s guarded description; answer asks the question; ground returns elements with pixel boxes; extract validates the model’s JSON against schemaJson and returns data: null with issues on a mismatch. The result is an observation, never verified evidence.',
  },
  {
    type: 'image.ocr',
    version: '1.0.0',
    category: 'media',
    label: 'Read text (OCR)',
    description: 'Extracts text and pixel spans from an image.',
    icon: 'text',
    inputs: [port({ id: 'image', name: 'Image', type: 'image', optional: true })],
    outputs: [
      port({ id: 'text', name: 'Text', type: 'string' }),
      port({ id: 'spans', name: 'Spans', type: 'array' }),
      port({ id: 'meta', name: 'Meta', type: 'object' }),
    ],
    configSchema: z.object({
      assetId: z.string().max(80).default(''),
      language: z.string().max(40).default(''),
      region: z.string().max(80).default(''),
    }),
    defaultConfig: () => ({ assetId: '', language: '', region: '' }),
    capabilities: ['image.read', 'model.vision'],
    sideEffects: 'model',
    allowedModes: ALL_MODES,
    docs: 'OCR through the vision engine. Spans carry text and pixel bounds when the engine returns them; an empty result is honest.',
  },
  {
    type: 'image.read_chart',
    version: '1.0.0',
    category: 'media',
    label: 'Read chart',
    description: 'Reads a chart image into trend, patterns, candles and levels.',
    icon: 'chart',
    inputs: [
      port({ id: 'image', name: 'Image', type: 'image', optional: true }),
      port({ id: 'question', name: 'Question', type: 'string', optional: true }),
    ],
    outputs: [
      port({ id: 'reading', name: 'Reading', type: 'object' }),
      port({ id: 'description', name: 'Description', type: 'string' }),
      port({ id: 'verified', name: 'Verified', type: 'boolean' }),
      port({ id: 'meta', name: 'Meta', type: 'object' }),
    ],
    configSchema: z.object({
      assetId: z.string().max(80).default(''),
      question: z.string().max(4_000).default(''),
      symbol: z.string().max(40).default(''),
      market: z.string().max(20).default(''),
      timeframe: z.string().max(40).default(''),
    }),
    defaultConfig: () => ({ assetId: '', question: '', symbol: '', market: '', timeframe: '' }),
    capabilities: ['image.read', 'model.vision', 'market.read'],
    sideEffects: 'model',
    allowedModes: ALL_MODES,
    docs: 'The chart reader. `verified` is true only when the engine’s own market-data check confirmed the reading; otherwise the result is an observation with the reason in meta.verification.',
  },
  {
    type: 'image.compare',
    version: '1.0.0',
    category: 'media',
    label: 'Compare images',
    description: 'Compares two images (pixel diff and/or visual description).',
    icon: 'branch',
    inputs: [
      port({ id: 'a', name: 'Candidate', type: 'image', optional: true }),
      port({ id: 'b', name: 'Reference', type: 'image', optional: true }),
    ],
    outputs: [
      port({ id: 'same', name: 'Same', type: 'boolean' }),
      port({ id: 'score', name: 'Similarity', type: 'number' }),
      port({ id: 'differences', name: 'Differences', type: 'array' }),
      port({ id: 'meta', name: 'Meta', type: 'object' }),
    ],
    configSchema: z.object({
      assetId: z.string().max(80).default(''),
      compareAssetId: z.string().max(80).default(''),
      mode: z.enum(IMAGE_COMPARE_MODES).default('both'),
      threshold: z.number().min(0).max(1).default(0.02),
      question: z.string().max(2_000).default(''),
    }),
    defaultConfig: () => ({
      assetId: '', compareAssetId: '', mode: 'both', threshold: 0.02, question: '',
    }),
    capabilities: ['image.read', 'model.vision'],
    sideEffects: 'model',
    allowedModes: ALL_MODES,
    docs: 'pixel is deterministic and needs no model; visual asks the model what changed; both reports both and says which basis produced `same` in meta.basis.',
  },
  {
    type: 'image.batch',
    version: '1.0.0',
    category: 'media',
    label: 'Read image options',
    description: 'Applies the same questions to 1–8 images, one result per image.',
    icon: 'chart',
    inputs: [port({ id: 'images', name: 'Images', type: 'array', optional: true })],
    outputs: [
      port({ id: 'results', name: 'Results', type: 'array' }),
      port({ id: 'summary', name: 'Summary', type: 'object' }),
      port({ id: 'failed', name: 'Failed', type: 'array' }),
    ],
    configSchema: z.object({
      assetIds: z.string().max(8_000).default(''),
      questionsJson: z.string().max(10_000).default(''),
      mode: z.enum(IMAGE_BATCH_MODES).default('analyze'),
      concurrency: z.number().int().min(1).max(3).default(1),
      maxImages: z.number().int().min(1).max(MAX_BATCH_IMAGES).default(MAX_BATCH_IMAGES),
      outputSchemaJson: z.string().max(20_000).default(''),
      symbol: z.string().max(40).default(''),
    }),
    defaultConfig: () => ({
      assetIds: '', questionsJson: '', mode: 'analyze', concurrency: 1,
      maxImages: MAX_BATCH_IMAGES, outputSchemaJson: '', symbol: '',
    }),
    capabilities: ['image.read', 'model.vision'],
    sideEffects: 'model',
    allowedModes: ALL_MODES,
    docs: 'The multiple-options node: one image per candle option, the same 1–5 questions applied to each, and one row per image. A failed image is a row with ok: false; the batch never aborts silently. 1–8 images, concurrency 1–3.',
  },
];
