import axios from 'axios';

// Backend configuration mapping
const BACKEND_CONFIGS = {
  'unet': {
    baseURL: 'http://localhost:8000/unet',
    name: 'UNet Building Detection'
  },
  'maskrcnn': {
    baseURL: 'http://localhost:8000/maskrcnn',
    name: 'MaskRCNN Object Detection'
  },
  'oil_spill': {
    baseURL: 'http://localhost:8000/oil_spill',
    name: 'Oil Spill Segmentation'
  },
  'srgan': {
    baseURL: 'http://localhost:8000/srgan',
    name: 'SRGAN Super-Resolution'
  }
};

// Enhanced function to determine backend based on model name
const getBackendConfig = (modelName) => {
  console.log(`🔍 Determining backend for model: ${modelName}`);
  const modelLower = modelName.toLowerCase();

  // SRGAN models
  if (modelLower.includes('srgan') ||
    modelLower.includes('super') ||
    modelLower.includes('resolution') ||
    modelLower.includes('upscale') ||
    modelLower.includes('generator')) {
    console.log(`✅ Routing to SRGAN backend (port 8002)`);
    return BACKEND_CONFIGS.srgan;
  }

  // SAR flood UNet before generic "mask" heuristic (avoids mis-routing names containing "mask")
  if (modelLower.includes('sar') && (modelLower.includes('flood') || modelLower.includes('finetune'))) {
    console.log(`✅ Routing to UNet backend for SAR flood model`);
    return BACKEND_CONFIGS.unet;
  }

  // Solar panel ResUNet — same FastAPI service as Mask R-CNN (finalmain /maskrcnn)
  if (modelLower.includes('solar') || modelLower.includes('solarpanel')) {
    console.log('✅ Routing to MaskRCNN backend for solar panel model');
    return BACKEND_CONFIGS.maskrcnn;
  }

  // Oil spill semantic segmentation
  if (modelLower.includes('oil_spill') || modelLower.includes('oil spill') || modelLower.includes('oilspill')) {
    console.log('✅ Routing to Oil Spill backend');
    return BACKEND_CONFIGS.oil_spill;
  }

  // MaskRCNN models
  if (modelLower.includes('tree') ||
    modelLower.includes('maskrcnn') ||
    modelLower.includes('mask') ||
    modelLower.includes('rcnn')) {
    console.log(`✅ Routing to MaskRCNN backend (port 8001)`);
    return BACKEND_CONFIGS.maskrcnn;
  }

  // UNet models (building detection)
  console.log(`✅ Routing to UNet backend (port 8000)`);
  return BACKEND_CONFIGS.unet;
};

const createApiClient = (backendConfig) => {
  return axios.create({
    baseURL: backendConfig.baseURL,
    timeout: 600000,
    maxContentLength: Infinity,
    maxBodyLength: Infinity,
  });
};

/** URL for demo ortho GeoTIFF (UNet serves from models/samples/demo_ortho, then Eg_files). */
export const getDemoOrthoSampleUrl = () =>
  `${BACKEND_CONFIGS.unet.baseURL}/demo-sample-ortho`;

///////////////////////NEW////////////////////////
export const fetchModels1 = async () => {
  console.log('🌐 Fetching models from all backends...');
  try {
    const unetApi = createApiClient(BACKEND_CONFIGS.unet);
    const maskrcnnApi = createApiClient(BACKEND_CONFIGS.maskrcnn);
    const srganApi = createApiClient(BACKEND_CONFIGS.srgan);

    const results = await Promise.allSettled([
      // unetApi.get('/models'),
      // maskrcnnApi.get('/models'),
      srganApi.get('/super_resolution_model')
    ]);

    let allModels = [];

    // Process UNet backend results
    if (results[0].status === 'fulfilled') {
      const unetModels = results[0].value.data.models || [];
      console.log('📁 UNet backend models:', unetModels);
      unetModels.forEach(modelName => {
        allModels.push({
          name: modelName,
          backend: BACKEND_CONFIGS.unet.name,
          baseURL: BACKEND_CONFIGS.unet.baseURL,
          type: 'detection'  // NEW: Add type field
        });
      });
    }
    const uniqueModels = [];
    const seenNames = new Set();
    allModels.forEach(model => {
      if (!seenNames.has(model.name)) {
        seenNames.add(model.name);
        const correctBackend = getBackendConfig(model.name);
        uniqueModels.push({
          ...model,
          backend: correctBackend.name,
          baseURL: correctBackend.baseURL
        });
      }
    });

    console.log('🎯 Final processed models:', uniqueModels);
    console.log(`📊 Total: ${uniqueModels.length} models`);
    return { models: uniqueModels };

  } catch (error) {
    console.error('❌ Error fetching models:', error);
    return { models: [] };
  }
};
// Fetch models from all backends
export const fetchModels = async () => {
  console.log('🌐 Fetching models from all backends...');
  try {
    const unetApi = createApiClient(BACKEND_CONFIGS.unet);
    const maskrcnnApi = createApiClient(BACKEND_CONFIGS.maskrcnn);
    const oilSpillApi = createApiClient(BACKEND_CONFIGS.oil_spill);

    const results = await Promise.allSettled([
      unetApi.get('/models'),
      maskrcnnApi.get('/models'),
      oilSpillApi.get('/models'),
      // srganApi.get('/super_resolution_model')
    ]);

    let allModels = [];

    // Process UNet backend results
    if (results[0].status === 'fulfilled') {
      const unetModels = results[0].value.data.models || [];
      console.log('📁 UNet backend models:', unetModels);
      unetModels.forEach(modelName => {
        allModels.push({
          name: modelName,
          backend: BACKEND_CONFIGS.unet.name,
          baseURL: BACKEND_CONFIGS.unet.baseURL,
          type: 'detection'  // NEW: Add type field
        });
      });
    }

    // Process MaskRCNN backend results
    if (results[1].status === 'fulfilled') {
      const respData = results[1].value.data || {};
      const maskrcnnModels = respData.models || [];
      const detailed = respData.models_detailed || [];
      const metaByName = {};
      detailed.forEach((d) => {
        if (d && d.name) metaByName[d.name] = d;
      });
      console.log('📁 MaskRCNN backend models:', maskrcnnModels);
      maskrcnnModels.forEach((modelName) => {
        const d = metaByName[modelName] || {};
        allModels.push({
          name: modelName,
          backend: BACKEND_CONFIGS.maskrcnn.name,
          baseURL: BACKEND_CONFIGS.maskrcnn.baseURL,
          type: 'detection',
          modelKind: d.kind || 'maskrcnn',
          modelFamily: d.model_family || 'maskrcnn',
        });
      });
    }
    // Oil spill segmentation models
    if (results[2].status === 'fulfilled') {
      const oilModels = results[2].value.data.models || [];
      console.log('📁 Oil spill backend models:', oilModels);
      oilModels.forEach(modelName => {
        allModels.push({
          name: modelName,
          backend: BACKEND_CONFIGS.oil_spill.name,
          baseURL: BACKEND_CONFIGS.oil_spill.baseURL,
          type: 'detection'
        });
      });
    }
    // SRGAN models: add srganApi.get(...) to Promise.all above when enabling this branch.

    // Remove duplicates (keep the first occurrence with its original backend)
    const uniqueModels = [];
    const seenNames = new Set();
    allModels.forEach(model => {
      if (!seenNames.has(model.name)) {
        seenNames.add(model.name);
        uniqueModels.push(model);
      }
    });

    console.log('🎯 Final processed models:', uniqueModels);
    console.log(`📊 Total: ${uniqueModels.length} models`);
    return { models: uniqueModels };

  } catch (error) {
    console.error('❌ Error fetching models:', error);
    return { models: [] };
  }
};

// Upload with dynamic routing (UPDATED to handle scale_factor for SRGAN)
export const uploadImage = async (
  formData,
  modelName,
  thresholdOrScale = 0.5,
  onUploadProgress,
  overrideBaseURL,
  extras = {},
) => {
  console.log(`🚀 uploadImage called with model: ${modelName}, param: ${thresholdOrScale}`);
  try {
    const backendConfig = overrideBaseURL
      ? { ...getBackendConfig(modelName), baseURL: overrideBaseURL }
      : getBackendConfig(modelName);
    const api = createApiClient(backendConfig);

    console.log(`🎯 Final routing: ${modelName} → ${backendConfig.name} (${backendConfig.baseURL})`);

    // Determine parameter name based on backend type
    const params = {};
    params.model_name = modelName;

    if (backendConfig.name.includes('SRGAN')) {
      // SRGAN uses scale_factor instead of threshold
      params.scale_factor = Math.round(thresholdOrScale);  // Convert to integer
      console.log(`🔧 SRGAN parameters: scale_factor=${params.scale_factor}`);
    } else {
      // Detection models use threshold
      params.threshold = thresholdOrScale;
      console.log(`🔧 Detection parameters: threshold=${params.threshold}`);
      const u = String(backendConfig.baseURL || '').toLowerCase();
      if (u.includes('unet')) {
        params.straighten_mask = extras.unetStraightenMask ? 1 : 0;
      }
    }

    const response = await api.post('/predict', formData, {
      params: params,
      onUploadProgress: (progressEvent) => {
        if (onUploadProgress) {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onUploadProgress(percentCompleted);
        }
      },
    });

    // Add backend info to response
    const responseData = {
      ...response.data,
      _backendURL: backendConfig.baseURL,
      _backendType: backendConfig.name.includes('SRGAN') ? 'super-resolution' : 'detection'
    };

    console.log('✅ Upload successful, response:', responseData);
    return responseData;

  } catch (error) {
    console.error('❌ Upload error:', error);
    if (error.response) {
      console.error('Error response:', error.response.data);
      console.error('Error status:', error.response.status);
    }
    throw error;
  }
};

// Download functions (unchanged)
export const downloadGeoJSON = async (runId, backendURL) => {
  try {
    const baseURL = backendURL || BACKEND_CONFIGS.unet.baseURL;
    const api = axios.create({ baseURL });
    console.log(`📥 Downloading GeoJSON from: ${baseURL}/download_geojson?run_id=${runId}`);

    const response = await api.get('/download_geojson', {
      params: { run_id: runId },
      responseType: 'arraybuffer',
    });

    console.log('✅ GeoJSON downloaded successfully');
    return response.data;
  } catch (error) {
    console.error('❌ GeoJSON download error:', error);
    throw error;
  }
};

/** Filter Mask R-CNN full GeoJSON features by properties.confidence (post-inference display threshold). */
export function filterGeoJsonByConfidence(geojson, minConfidence) {
  if (!geojson || !Array.isArray(geojson.features)) return geojson;
  const t = Number(minConfidence);
  const features = geojson.features.filter((f) => {
    const c = f?.properties?.confidence;
    if (c === undefined || c === null) return true;
    return Number(c) >= t;
  });
  return { type: 'FeatureCollection', features };
}

export async function fetchUnetGeojsonAtThreshold(
  runId,
  threshold,
  backendURL,
  straightenMask = 0,
) {
  const root = (backendURL || BACKEND_CONFIGS.unet.baseURL).replace(/\/$/, '');
  const api = axios.create({ baseURL: root });
  const { data } = await api.get(`/runs/${runId}/geojson`, {
    params: {
      threshold,
      straighten_mask: straightenMask ? 1 : 0,
    },
  });
  return data;
}

/**
 * Post-process lab (preview): requires ENABLE_POSTPROCESS_LAB on server + VITE_ENABLE_POSTPROCESS_LAB on client.
 * Mask R-CNN / solar: POST {backend}/postprocess/preview. UNet: same path on UNet service.
 */
export async function postprocessLabPreview(backendURL, body) {
  const root = (backendURL || '').replace(/\/$/, '');
  const api = axios.create({ baseURL: root, timeout: 600000 });
  const { data } = await api.post('/postprocess/preview', body);
  return data;
}

export async function postprocessLabApply(backendURL, body) {
  const root = (backendURL || '').replace(/\/$/, '');
  const api = axios.create({ baseURL: root, timeout: 600000 });
  const { data } = await api.post('/postprocess/apply', body);
  return data;
}

export async function fetchSavedDetectionRuns(limit = 50) {
  const query = { params: { limit } };
  const unetApi = axios.create({ baseURL: BACKEND_CONFIGS.unet.baseURL });
  const maskApi = axios.create({ baseURL: BACKEND_CONFIGS.maskrcnn.baseURL });
  const [u, m] = await Promise.allSettled([
    unetApi.get('/runs', query),
    maskApi.get('/runs', query),
  ]);
  const runs = [];
  if (u.status === 'fulfilled') {
    (u.value.data?.runs || []).forEach((r) =>
      runs.push({ ...r, _backendURL: BACKEND_CONFIGS.unet.baseURL, _backendType: 'detection' })
    );
  }
  if (m.status === 'fulfilled') {
    (m.value.data?.runs || []).forEach((r) =>
      runs.push({ ...r, _backendURL: BACKEND_CONFIGS.maskrcnn.baseURL, _backendType: 'detection' })
    );
  }
  runs.sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));
  return runs;
}

/** Download class GeoTIFF from oil spill API (`prediction_geotiff_url` path under backend). */
export const downloadPredictionGeoTiff = async (relativeUrl, backendURL) => {
  const root = (backendURL || BACKEND_CONFIGS.oil_spill.baseURL).replace(/\/$/, '');
  const path = relativeUrl.startsWith('http') ? relativeUrl : `${root}${relativeUrl}`;
  const response = await axios.get(path, { responseType: 'arraybuffer' });
  return response.data;
};

export const downloadShapefile = async (runId, backendURL) => {
  try {
    const baseURL = backendURL || BACKEND_CONFIGS.unet.baseURL;
    const api = axios.create({ baseURL });
    console.log(`📥 Downloading Shapefile from: ${baseURL}/download_shapefile?run_id=${runId}`);

    const response = await api.get('/download_shapefile', {
      params: { run_id: runId },
      responseType: 'arraybuffer',
    });

    console.log('✅ Shapefile downloaded successfully');
    return response.data;
  } catch (error) {
    console.error('❌ Shapefile download error:', error);
    throw error;
  }
};

// NEW: Download super-resolved image
export const downloadSRImage = async (runId, backendURL) => {
  try {
    const baseURL = backendURL || BACKEND_CONFIGS.srgan.baseURL;
    const api = axios.create({ baseURL });
    console.log(`📥 Downloading SR image from: ${baseURL}/download_output?run_id=${runId}`);

    const response = await api.get('/download_output', {
      params: { run_id: runId },
      responseType: 'blob',
    });

    console.log('✅ SR image downloaded successfully');
    return response.data;
  } catch (error) {
    console.error('❌ SR image download error:', error);
    throw error;
  }
};

/**
 * Parse one SSE JSON payload. Python may emit NaN/Infinity (invalid in RFC 8259 / JSON.parse).
 */
export function parseSseJsonPayload(jsonStr) {
  if (!jsonStr || !jsonStr.length) return null;
  try {
    return JSON.parse(jsonStr);
  } catch {
    const fixed = jsonStr
      .replace(/:\s*NaN\b/g, ':null')
      .replace(/:\s*-Infinity\b/g, ':null')
      .replace(/:\s*Infinity\b/g, ':null');
    return JSON.parse(fixed);
  }
}

/**
 * Buffer Flask/FastAPI SSE until `\n\n` (base64/geojson payloads can span chunks).
 */
export function parseSseBlocks(carry, chunk) {
  carry += chunk;
  const events = [];
  let sep;
  while ((sep = carry.indexOf('\n\n')) !== -1) {
    const block = carry.slice(0, sep).trim();
    carry = carry.slice(sep + 2);
    const dataLine = block.split('\n').find((l) => l.startsWith('data: '));
    if (!dataLine) continue;
    const jsonStr = dataLine.slice(6).trim();
    if (!jsonStr) continue;
    try {
      const ev = parseSseJsonPayload(jsonStr);
      if (ev != null) events.push(ev);
    } catch {
      /* incomplete block */
    }
  }
  return { carry, events };
}

/**
 * Incremental detection: POST `/predict-stream` (Mask R-CNN or UNet).
 * @param streamIntervalParam - `stream_tile_interval` (Mask R-CNN) or `stream_chip_interval` (UNet)
 */
export function postPredictStream(
  formData,
  {
    baseURL,
    modelName,
    threshold,
    streamIntervalParam = 'stream_tile_interval',
    streamInterval = 5,
    onEvent,
    onDone,
    onError,
  }
) {
  const root = (baseURL || '').replace(/\/$/, '');
  const q = new URLSearchParams({
    model_name: modelName,
    threshold: String(threshold),
    [streamIntervalParam]: String(streamInterval),
  });
  const url = `${root}/predict-stream?${q.toString()}`;

  const xhr = new XMLHttpRequest();
  xhr.open('POST', url, true);

  let carry = '';
  let lastResponseLen = 0;

  const dispatch = (ev) => {
    if (ev.type === 'error') {
      onError?.(ev.error || 'Unknown error');
      return;
    }
    if (ev.type === 'done') {
      onDone?.(ev);
      return;
    }
    onEvent?.(ev);
  };

  const pump = () => {
    const text = xhr.responseText;
    if (text.length <= lastResponseLen) return;
    const delta = text.slice(lastResponseLen);
    lastResponseLen = text.length;
    const parsed = parseSseBlocks(carry, delta);
    carry = parsed.carry;
    for (const ev of parsed.events) {
      dispatch(ev);
    }
  };

  xhr.onreadystatechange = () => {
    if (xhr.readyState < 3) return;
    if (xhr.status !== 0 && xhr.status >= 400) return;
    pump();
  };

  xhr.onload = () => {
    if (xhr.status >= 400) {
      let msg = `Request failed (${xhr.status})`;
      try {
        const j = JSON.parse(xhr.responseText);
        if (j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
      } catch {
        /* ignore */
      }
      onError?.(msg);
      return;
    }
    pump();
    const tail = carry.trim();
    if (tail) {
      const dataLine = tail.split('\n').find((l) => l.startsWith('data: '));
      if (dataLine) {
        const jsonStr = dataLine.slice(6).trim();
        try {
          const ev = parseSseJsonPayload(jsonStr);
          if (ev != null) dispatch(ev);
        } catch {
          onError?.('Incomplete response from server');
        }
      }
      carry = '';
    }
  };

  xhr.onerror = () => onError?.('Network error');

  xhr.send(formData);
  return xhr;
}

export default BACKEND_CONFIGS;
