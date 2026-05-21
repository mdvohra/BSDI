import axios from 'axios';

export function getAnalysisBaseUrl() {
  return (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
}

const client = () =>
  axios.create({
    baseURL: `${getAnalysisBaseUrl()}/api/analysis`,
    timeout: 120000,
  });

export async function fetchCatalog(limit = 200) {
  const { data } = await client().get('/catalog', { params: { limit } });
  return data;
}

export async function fetchPredictionBundle(task, id) {
  const { data } = await client().get(`/prediction/${encodeURIComponent(task)}/${encodeURIComponent(id)}`);
  return data;
}

export async function deletePrediction(task, id) {
  const { data } = await client().delete(
    `/prediction/${encodeURIComponent(task)}/${encodeURIComponent(id)}`
  );
  return data;
}

export async function deleteAllPredictions() {
  const { data } = await client().post('/predictions/delete-all', { confirm: true });
  return data;
}

export async function postCompare(primary, secondary) {
  const { data } = await client().post('/compare', {
    primary,
    secondary,
  });
  return data;
}

export async function postLlmChat(messages, context) {
  const { data } = await client().post('/llm/chat', {
    messages,
    context,
  });
  return data;
}

export async function postLulcChangeComparison(baselineId, newId, tilePx = 128, regionSetId = null) {
  const { data } = await client().post('/lulc-change/comparison', {
    baseline_id: baselineId,
    new_id: newId,
    tile_px: tilePx,
    region_set_id: regionSetId,
  });
  return data;
}

export async function getLulcChangeSummary(comparisonId) {
  const { data } = await client().get(
    `/lulc-change/comparison/${encodeURIComponent(comparisonId)}/summary`
  );
  return data;
}

export async function getLulcChangeTransitionMatrix(comparisonId) {
  const { data } = await client().get(
    `/lulc-change/comparison/${encodeURIComponent(comparisonId)}/transition-matrix`
  );
  return data;
}

export async function getLulcChangeClasses(comparisonId, classIdx, topNRegions = 5, topNTiles = 10) {
  const { data } = await client().get(
    `/lulc-change/comparison/${encodeURIComponent(comparisonId)}/classes`,
    { params: { class_idx: classIdx, top_n_regions: topNRegions, top_n_tiles: topNTiles } }
  );
  return data;
}

export async function getLulcChangeRegions(comparisonId) {
  const { data } = await client().get(
    `/lulc-change/comparison/${encodeURIComponent(comparisonId)}/regions`
  );
  return data;
}

export async function getLulcChangeTiles(comparisonId, limit = 50, offset = 0) {
  const { data } = await client().get(
    `/lulc-change/comparison/${encodeURIComponent(comparisonId)}/tiles`,
    { params: { limit, offset } }
  );
  return data;
}

export async function postLulcLocalInsight(comparisonId, lon, lat, windowPx = 31) {
  const { data } = await client().post('/lulc-change/local-insight', {
    comparison_id: comparisonId,
    lon,
    lat,
    window_px: windowPx,
  });
  return data;
}

export async function postLlmQuery(messages, comparisonId = null) {
  const { data } = await client().post('/llm/query', {
    messages,
    comparison_id: comparisonId,
  });
  return data;
}

/** POST GeoJSON boundaries (FeatureCollection or Feature); use same set_id when running comparison. */
export async function postLulcRegionSet(setId, geojson) {
  const { data } = await client().post('/lulc-change/region-set', {
    set_id: setId,
    geojson,
  });
  return data;
}
