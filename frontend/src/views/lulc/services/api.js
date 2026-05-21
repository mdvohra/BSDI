import axios from 'axios';

export const LULC_BASE_URL = 'http://localhost:8000/lulc';

const createApiClient = () => {
  return axios.create({
    baseURL: LULC_BASE_URL,
    timeout: 600000,
    maxContentLength: Infinity,
    maxBodyLength: Infinity,
  });
};

export const uploadImageForClassification = async (formData, segMode = 'fast', onUploadProgress) => {
  const api = createApiClient();
  formData.append('seg_mode', segMode);

  const response = await api.post('/predict', formData, {
    onUploadProgress: (progressEvent) => {
      if (onUploadProgress) {
        const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        onUploadProgress(percentCompleted);
      }
    },
  });

  return response.data;
};

/**
 * Parse Flask SSE: each event is `data: <json>\\n\\n`. Payloads can be megabytes (base64 images),
 * so they arrive across many XHR chunks — we must buffer until `\\n\\n`, not split per chunk on `\\n`.
 */
function parseSseBlocks(carry, chunk) {
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
      events.push(JSON.parse(jsonStr));
    } catch {
      /* incomplete or corrupt block */
    }
  }
  return { carry, events };
}

export const uploadImageStreaming = (formData, segMode = 'fast', onProgress, onDone, onError) => {
  formData.append('seg_mode', segMode);

  const xhr = new XMLHttpRequest();
  xhr.open('POST', `${LULC_BASE_URL}/predict-stream`, true);

  let carry = '';
  let lastResponseLen = 0;

  const dispatch = (event) => {
    if (event.type === 'progress') {
      onProgress?.(event);
    } else if (event.type === 'done') {
      onDone?.(event);
    } else if (event.type === 'error') {
      onError?.(event.error || 'Unknown error');
    } else if (event.type === 'start') {
      onProgress?.({ ...event, progress: 0 });
    }
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
        if (j.error) msg = j.error;
      } catch {
        /* ignore */
      }
      onError?.(msg);
      return;
    }
    pump();
    if (carry.trim()) {
      const dataLine = carry.trim().split('\n').find((l) => l.startsWith('data: '));
      if (dataLine) {
        try {
          dispatch(JSON.parse(dataLine.slice(6).trim()));
        } catch {
          onError?.('Incomplete response from server');
        }
      }
      carry = '';
    }
  };

  xhr.onerror = () => {
    onError?.('Network error');
  };

  xhr.send(formData);
  return xhr;
};

export const previewImage = async (formData) => {
  const api = createApiClient();
  const response = await api.post('/preview', formData);
  return response.data;
};

export const fetchPredictions = async () => {
  const api = createApiClient();
  const response = await api.get('/predictions');
  return response.data;
};

export const fetchPrediction = async (predId) => {
  const api = createApiClient();
  const response = await api.get(`/predictions/${predId}`);
  return response.data;
};

export const deletePrediction = async (predId) => {
  const api = createApiClient();
  const response = await api.delete(`/predictions/${encodeURIComponent(predId)}`);
  return response.data;
};

export const deleteAllPredictions = async () => {
  const api = createApiClient();
  const response = await api.post('/predictions/delete-all', { confirm: true });
  return response.data;
};

export const downloadGeoTIFF = async (predId) => {
  const api = createApiClient();
  const response = await api.get(`/predictions/${predId}/geotiff`, {
    responseType: 'blob',
  });
  return response.data;
};

export default { LULC_BASE_URL };
