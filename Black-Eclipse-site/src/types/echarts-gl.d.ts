// Type shim for `echarts-gl`.
//
// The package ships no type declarations. Only its SIDE EFFECT is used —
// importing it registers the `globe`, `scatterGL`/`linesGL` components and the
// WebGL renderer against the ECharts instance that shares its peer dependency.
// Nothing from the module is called directly, so `any` is the honest type here.
declare module 'echarts-gl';
