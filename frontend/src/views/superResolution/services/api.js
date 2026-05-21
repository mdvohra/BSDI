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
  'srgan': {
    baseURL: 'http://localhost:8000/srgan',
    name: 'SRGAN Super-Resolution'
  }
};

// Enhanced function to determine backend based on model name
const getBackendConfig = (modelName) => {
  if (!modelName || typeof modelName !== 'string') {
    console.warn(`⚠️ Invalid modelName passed to getBackendConfig:`, modelName);
    return BACKEND_CONFIGS.unet; // Default
  }
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

  if (modelLower.includes('sar') && (modelLower.includes('flood') || modelLower.includes('finetune'))) {
    console.log(`✅ Routing to UNet backend for SAR flood model`);
    return BACKEND_CONFIGS.unet;
  }

  if (modelLower.includes('solar') || modelLower.includes('solarpanel')) {
    console.log('✅ Routing to MaskRCNN backend for solar panel model');
    return BACKEND_CONFIGS.maskrcnn;
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

///////////////////////NEW////////////////////////
export const fetchModels1 = async () => {
  console.log('🌐 Fetching models from all backends (SR only)...');
  try {
    const srganApi = createApiClient(BACKEND_CONFIGS.srgan);

    const result = await srganApi.get('/super_resolution_model');

    let allModels = [];

    if (result.status === 200) {
      const srganModels = result.data.models || [];
      console.log('📁 Raw models from SRGAN backend:', srganModels);
      if (srganModels.length === 0) {
        console.warn('⚠️ SRGAN backend returned zero models. Check backend/models directory.');
      }
      srganModels.forEach(modelName => {
        if (modelName && typeof modelName === 'string') {
          allModels.push({
            name: modelName,
            backend: BACKEND_CONFIGS.srgan.name,
            baseURL: BACKEND_CONFIGS.srgan.baseURL,
            type: 'super-resolution'
          });
        }
      });
    }

    console.log('🎯 Final processed SR models:', allModels);
    return { models: allModels };

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
    const srganApi = createApiClient(BACKEND_CONFIGS.srgan);

    const results = await Promise.allSettled([
      unetApi.get('/models'),
      maskrcnnApi.get('/models'),
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

    // Process MaskRCNN backend results
    if (results[1].status === 'fulfilled') {
      const maskrcnnModels = results[1].value.data.models || [];
      console.log('📁 MaskRCNN backend models:', maskrcnnModels);
      maskrcnnModels.forEach(modelName => {
        allModels.push({
          name: modelName,
          backend: BACKEND_CONFIGS.maskrcnn.name,
          baseURL: BACKEND_CONFIGS.maskrcnn.baseURL,
          type: 'detection'  // NEW: Add type field
        });
      });
    }

    // Process SRGAN backend results - NEW
    if (results[2].status === 'fulfilled') {
      const srganModels = results[2].value.data.models || [];
      console.log('📁 SRGAN backend models:', srganModels);
      srganModels.forEach(modelName => {
        allModels.push({
          name: modelName,
          backend: BACKEND_CONFIGS.srgan.name,
          baseURL: BACKEND_CONFIGS.srgan.baseURL,
          type: 'super-resolution'  // NEW: Add type field
        });
      });
    } else {
      console.warn('⚠️ SRGAN backend fetch failed:', results[2].reason);
    }

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
export const uploadImage = async (formData, modelName, thresholdOrScale = 0.5, onUploadProgress, overrideBaseURL) => {
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

export default BACKEND_CONFIGS;
