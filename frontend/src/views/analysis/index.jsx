import React, { useCallback, useEffect, useMemo, useState } from 'react';
import UiScopedView from '../../components/UiScopedView';
import { Container, Row, Col, Card, Form, Button, Spinner, Alert, Nav, Table } from 'react-bootstrap';
import {
  fetchCatalog,
  fetchPredictionBundle,
  deletePrediction,
  deleteAllPredictions,
  postCompare,
  postLlmChat,
  getAnalysisBaseUrl,
  postLulcChangeComparison,
  getLulcChangeSummary,
  getLulcChangeTransitionMatrix,
  getLulcChangeClasses,
  getLulcChangeRegions,
  getLulcChangeTiles,
  postLulcLocalInsight,
  postLlmQuery,
  postLulcRegionSet,
} from './api';
import AnalysisChart, { parseChartFromReply } from './AnalysisChart';
import LulcComparisonTab from './LulcComparisonTab';
import './analysis.css';

function selectionKey(task, id) {
  return `${task}:${id}`;
}

function parseSelectionKey(key) {
  const i = key.indexOf(':');
  if (i <= 0) return null;
  return { task: key.slice(0, i), id: key.slice(i + 1) };
}

function AnalysisPageInner() {
  const [catalog, setCatalog] = useState({ object_detection: [], lulc: [] });
  const [loading, setLoading] = useState(true);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [err, setErr] = useState('');

  const [primaryKey, setPrimaryKey] = useState('');
  const [secondaryKey, setSecondaryKey] = useState('');

  const [bundleA, setBundleA] = useState(null);
  const [bundleB, setBundleB] = useState(null);
  const [loadingBundle, setLoadingBundle] = useState(false);

  const [compareResult, setCompareResult] = useState(null);
  const [compareLoading, setCompareLoading] = useState(false);

  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState('');

  const [changeTab, setChangeTab] = useState('overview');
  const [tilePx, setTilePx] = useState(128);
  const [comparisonId, setComparisonId] = useState('');
  const [changeLoading, setChangeLoading] = useState(false);
  const [changeErr, setChangeErr] = useState('');
  const [summary, setSummary] = useState(null);
  const [matrix, setMatrix] = useState(null);
  const [classIdx, setClassIdx] = useState(0);
  const [classDetail, setClassDetail] = useState(null);
  const [regionsData, setRegionsData] = useState(null);
  const [regionsLoading, setRegionsLoading] = useState(false);
  const [tilesData, setTilesData] = useState(null);
  const [localLon, setLocalLon] = useState('');
  const [localLat, setLocalLat] = useState('');
  const [localWin, setLocalWin] = useState(31);
  const [localResult, setLocalResult] = useState(null);
  const [localLoading, setLocalLoading] = useState(false);

  const [llmGroundedMessages, setLlmGroundedMessages] = useState([]);
  const [llmGroundedInput, setLlmGroundedInput] = useState('');
  const [llmGroundedLoading, setLlmGroundedLoading] = useState(false);
  const [llmGroundedError, setLlmGroundedError] = useState('');

  const [regionSetId, setRegionSetId] = useState('');
  const [regionGeoJsonText, setRegionGeoJsonText] = useState('');
  const [regionSaveLoading, setRegionSaveLoading] = useState(false);
  const [regionSaveErr, setRegionSaveErr] = useState('');
  const [regionSaveOk, setRegionSaveOk] = useState('');

  const flatOd = catalog.object_detection || [];
  const flatLulc = catalog.lulc || [];

  const allOptions = useMemo(() => {
    const od = flatOd.map((r) => ({
      key: selectionKey(r.task, r.id),
      label: `[${r.task}] ${String(r.id).slice(0, 10)}… ${r.model_name || ''} ${r.created_at || ''}`,
    }));
    const lu = flatLulc.map((r) => ({
      key: selectionKey('lulc', r.id),
      label: `[lulc] ${r.id.slice(0, 22)}… ${r.top_class || ''}${r.has_buildings ? ' · buildings' : ''}`,
    }));
    return [...od, ...lu];
  }, [flatOd, flatLulc]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setErr('');
    try {
      const data = await fetchCatalog(300);
      setCatalog(data);
    } catch (e) {
      setErr(e?.message || 'Failed to load catalog');
      setCatalog({ object_detection: [], lulc: [] });
    } finally {
      setLoading(false);
    }
  }, []);

  const clearChangeSession = () => {
    setComparisonId('');
    setSummary(null);
    setMatrix(null);
    setRegionsData(null);
    setTilesData(null);
    setClassDetail(null);
    setChangeErr('');
  };

  const handleDeleteOne = async (selectionKeyStr) => {
    const ref = parseSelectionKey(selectionKeyStr);
    if (!ref) return;
    const label = ref.task === 'lulc' ? 'this LULC run' : `this ${ref.task} run`;
    if (!window.confirm(`Delete ${label} from disk? This cannot be undone.`)) return;
    setDeleteBusy(true);
    setErr('');
    try {
      await deletePrediction(ref.task, ref.id);
      if (primaryKey === selectionKeyStr) {
        setPrimaryKey('');
        setBundleA(null);
      }
      if (secondaryKey === selectionKeyStr) {
        setSecondaryKey('');
        setBundleB(null);
      }
      clearChangeSession();
      await refresh();
    } catch (e) {
      const msg = e?.response?.data?.detail || e.message || 'Delete failed';
      setErr(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setDeleteBusy(false);
    }
  };

  const handleDeleteAll = async () => {
    if (
      !window.confirm(
        'Delete ALL saved predictions (object detection + LULC) from this server? This cannot be undone.'
      )
    ) {
      return;
    }
    setDeleteBusy(true);
    setErr('');
    try {
      await deleteAllPredictions();
      setPrimaryKey('');
      setSecondaryKey('');
      setBundleA(null);
      setBundleB(null);
      clearChangeSession();
      await refresh();
    } catch (e) {
      const msg = e?.response?.data?.detail || e.message || 'Delete all failed';
      setErr(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setDeleteBusy(false);
    }
  };

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!primaryKey) {
      setBundleA(null);
      return;
    }
    const ref = parseSelectionKey(primaryKey);
    if (!ref) return;
    let cancelled = false;
    setLoadingBundle(true);
    fetchPredictionBundle(ref.task, ref.id)
      .then((b) => {
        if (!cancelled) setBundleA(b);
      })
      .catch(() => {
        if (!cancelled) setBundleA(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingBundle(false);
      });
    return () => {
      cancelled = true;
    };
  }, [primaryKey]);

  useEffect(() => {
    if (!secondaryKey) {
      setBundleB(null);
      return;
    }
    const ref = parseSelectionKey(secondaryKey);
    if (!ref) return;
    let cancelled = false;
    fetchPredictionBundle(ref.task, ref.id)
      .then((b) => {
        if (!cancelled) setBundleB(b);
      })
      .catch(() => {
        if (!cancelled) setBundleB(null);
      });
    return () => {
      cancelled = true;
    };
  }, [secondaryKey]);

  const runCompare = async () => {
    if (!primaryKey || !secondaryKey) return;
    const a = parseSelectionKey(primaryKey);
    const b = parseSelectionKey(secondaryKey);
    if (!a || !b) return;
    setCompareLoading(true);
    setCompareResult(null);
    try {
      const data = await postCompare(a, b);
      setCompareResult(data);
    } catch (e) {
      setCompareResult({ error: e?.response?.data?.detail || e.message });
    } finally {
      setCompareLoading(false);
    }
  };

  const runLulcChange = async () => {
    const a = parseSelectionKey(primaryKey);
    const b = parseSelectionKey(secondaryKey);
    if (!a || !b || a.task !== 'lulc' || b.task !== 'lulc') {
      setChangeErr('Select two LULC runs: Primary (A) = baseline, Secondary (B) = new.');
      return;
    }
    setChangeLoading(true);
    setChangeErr('');
    setSummary(null);
    setMatrix(null);
    setRegionsData(null);
    setClassDetail(null);
    setComparisonId('');
    try {
      const rsid = regionSetId.trim() || null;
      const data = await postLulcChangeComparison(a.id, b.id, tilePx, rsid);
      const cid = data.comparison_id;
      setComparisonId(cid);
      const [sum, mx] = await Promise.all([
        getLulcChangeSummary(cid),
        getLulcChangeTransitionMatrix(cid),
      ]);
      setSummary(sum);
      setMatrix(mx);
      setRegionsLoading(true);
      try {
        const reg = await getLulcChangeRegions(cid);
        setRegionsData(reg);
      } catch {
        setRegionsData(null);
      } finally {
        setRegionsLoading(false);
      }
      setChangeTab('overview');
      const bounds = bundleB?.derived?.bounds;
      if (Array.isArray(bounds) && bounds.length === 4) {
        const [south, west, north, east] = bounds.map(Number);
        if ([south, west, north, east].every(Number.isFinite)) {
          setLocalLat((((south + north) / 2).toFixed(5)));
          setLocalLon((((west + east) / 2).toFixed(5)));
        }
      }
    } catch (e) {
      const msg = e?.response?.data?.detail || e.message || 'Change analysis failed';
      setChangeErr(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setChangeLoading(false);
    }
  };

  const loadClassDetail = async () => {
    if (!comparisonId) return;
    try {
      const d = await getLulcChangeClasses(comparisonId, classIdx);
      setClassDetail(d);
    } catch {
      setClassDetail(null);
    }
  };

  const loadRegions = async (cidArg) => {
    const cid = cidArg ?? comparisonId;
    if (!cid) return;
    setRegionsLoading(true);
    try {
      const d = await getLulcChangeRegions(cid);
      setRegionsData(d);
    } catch {
      setRegionsData(null);
    } finally {
      setRegionsLoading(false);
    }
  };

  const loadTiles = async () => {
    if (!comparisonId) return;
    try {
      const d = await getLulcChangeTiles(comparisonId, 80, 0);
      setTilesData(d);
    } catch {
      setTilesData(null);
    }
  };

  const normalizeGeoJsonForRegions = (obj) => {
    if (!obj || typeof obj !== 'object') return null;
    if (obj.type === 'FeatureCollection') return obj;
    if (obj.type === 'Feature') {
      return { type: 'FeatureCollection', features: [obj] };
    }
    return null;
  };

  const saveRegionSet = async () => {
    const sid = regionSetId.trim();
    setRegionSaveErr('');
    setRegionSaveOk('');
    if (!sid) {
      setRegionSaveErr('Enter a region set ID (e.g. my_districts) before saving.');
      return;
    }
    let parsed;
    try {
      parsed = JSON.parse(regionGeoJsonText || '{}');
    } catch {
      setRegionSaveErr('GeoJSON is not valid JSON.');
      return;
    }
    const gj = normalizeGeoJsonForRegions(parsed);
    if (!gj || !Array.isArray(gj.features) || gj.features.length === 0) {
      setRegionSaveErr('Provide a GeoJSON FeatureCollection or Feature with polygons (WGS84).');
      return;
    }
    setRegionSaveLoading(true);
    try {
      await postLulcRegionSet(sid, gj);
      setRegionSaveOk(
        `Saved as "${sid}". Click Analyze changes again with this ID under Technical options (optional).`
      );
    } catch (e) {
      setRegionSaveErr(e?.response?.data?.detail || e.message || 'Save failed');
    } finally {
      setRegionSaveLoading(false);
    }
  };

  useEffect(() => {
    if (changeTab === 'regions' && comparisonId) loadRegions();
    if (changeTab === 'tiles' && comparisonId) loadTiles();
    if (changeTab === 'categories' && comparisonId) loadClassDetail();
  }, [changeTab, comparisonId, classIdx]);

  const runLocalInsight = async () => {
    if (!comparisonId) return;
    const lon = parseFloat(localLon);
    const lat = parseFloat(localLat);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
      setChangeErr('Enter valid longitude and latitude.');
      return;
    }
    setLocalLoading(true);
    setChangeErr('');
    try {
      const r = await postLulcLocalInsight(comparisonId, lon, lat, localWin);
      setLocalResult(r);
    } catch (e) {
      setChangeErr(e?.response?.data?.detail || e.message || 'Local insight failed');
      setLocalResult(null);
    } finally {
      setLocalLoading(false);
    }
  };

  const sendChat = async () => {
    const text = (chatInput || '').trim();
    if (!text) return;
    setChatError('');
    const userMsg = { role: 'user', content: text };
    const nextMessages = [...chatMessages, userMsg];
    setChatMessages(nextMessages);
    setChatInput('');
    setChatLoading(true);

    const ctx = { prediction_ids: [] };
    if (primaryKey) {
      const pa = parseSelectionKey(primaryKey);
      if (pa) ctx.prediction_ids.push(pa);
    }
    if (secondaryKey) {
      const pb = parseSelectionKey(secondaryKey);
      if (pb) ctx.prediction_ids.push(pb);
    }

    try {
      const { reply } = await postLlmChat(nextMessages, ctx.prediction_ids.length ? ctx : null);
      setChatMessages((prev) => [...prev, { role: 'assistant', content: reply || '' }]);
    } catch (e) {
      const msg = e?.response?.data?.detail || e.message || 'Chat failed';
      setChatError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setChatLoading(false);
    }
  };

  const sendGroundedLlm = async () => {
    const text = (llmGroundedInput || '').trim();
    if (!text) return;
    setLlmGroundedError('');
    const userMsg = { role: 'user', content: text };
    const nextMessages = [...llmGroundedMessages, userMsg];
    setLlmGroundedMessages(nextMessages);
    setLlmGroundedInput('');
    setLlmGroundedLoading(true);
    try {
      const { reply } = await postLlmQuery(nextMessages, comparisonId || null);
      setLlmGroundedMessages((prev) => [...prev, { role: 'assistant', content: reply || '' }]);
    } catch (e) {
      const msg = e?.response?.data?.detail || e.message || 'Query failed';
      setLlmGroundedError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setLlmGroundedLoading(false);
    }
  };

  const apiBase = getAnalysisBaseUrl();

  const labels = summary?.labels || [];

  return (
    <Container fluid className="analysis-page py-3 px-3">
      <header className="mb-3">
        <h1 className="h4 text-white mb-1">Analysis</h1>
        <p className="text-secondary small mb-0">
          Inspect runs, shallow compare, <strong>LULC change analysis</strong> (GeoTIFF class rasters), and assistants.
          API: <code>{apiBase}/api/analysis</code>
        </p>
      </header>

      {err && <Alert variant="warning">{err}</Alert>}

      <Row className="g-3">
        <Col lg={5} xl={4}>
          <Card className="analysis-card h-100">
            <Card.Header className="d-flex justify-content-between align-items-center flex-wrap gap-2">
              <span>Predictions</span>
              <div className="d-flex gap-2 align-items-center">
                <Button size="sm" variant="outline-light" onClick={refresh} disabled={loading || deleteBusy}>
                  {loading ? <Spinner size="sm" animation="border" /> : 'Refresh'}
                </Button>
                <Button size="sm" variant="danger" onClick={handleDeleteAll} disabled={loading || deleteBusy}>
                  {deleteBusy ? <Spinner size="sm" animation="border" /> : 'Delete all'}
                </Button>
              </div>
            </Card.Header>
            <Card.Body>
              <div className="small text-secondary mb-2">
                Object detection: {flatOd.length} · LULC: {flatLulc.length}
              </div>
              <p className="small text-secondary mb-3">
                Pick the <strong>older</strong> map first, then the <strong>newer</strong> one. One button runs the full
                change analysis (regions, tiles, charts).
              </p>
              <Form.Label className="small text-secondary mb-1">Older run (baseline)</Form.Label>
              <Form.Select
                className="mb-2 bg-dark text-light border-secondary"
                size="sm"
                value={primaryKey}
                onChange={(e) => setPrimaryKey(e.target.value)}
              >
                <option value="">Choose…</option>
                {allOptions.map((o) => (
                  <option key={`p-${o.key}`} value={o.key}>
                    {o.label}
                  </option>
                ))}
              </Form.Select>
              <div className="d-flex gap-2 mb-3 flex-wrap">
                <Button
                  size="sm"
                  variant="outline-danger"
                  disabled={!primaryKey || deleteBusy}
                  onClick={() => handleDeleteOne(primaryKey)}
                >
                  Delete baseline
                </Button>
              </div>
              <Form.Label className="small text-secondary mb-1">Newer run</Form.Label>
              <Form.Select
                className="mb-2 bg-dark text-light border-secondary"
                size="sm"
                value={secondaryKey}
                onChange={(e) => setSecondaryKey(e.target.value)}
              >
                <option value="">Choose…</option>
                {allOptions.map((o) => (
                  <option key={`s-${o.key}`} value={o.key}>
                    {o.label}
                  </option>
                ))}
              </Form.Select>
              <div className="d-flex gap-2 mb-3 flex-wrap">
                <Button
                  size="sm"
                  variant="outline-danger"
                  disabled={!secondaryKey || deleteBusy}
                  onClick={() => handleDeleteOne(secondaryKey)}
                >
                  Delete newer
                </Button>
              </div>

              <div className="d-grid gap-2 mt-2">
                <Button
                  variant="warning"
                  size="sm"
                  disabled={changeLoading || !primaryKey || !secondaryKey}
                  onClick={runLulcChange}
                >
                  {changeLoading ? 'Analyzing…' : 'Analyze changes'}
                </Button>
              </div>

              <details className="mt-3 mb-2">
                <summary className="small text-secondary" style={{ cursor: 'pointer' }}>
                  Technical options (optional)
                </summary>
                <div className="pt-2">
                  <Form.Label className="small text-secondary mb-1">Tile grid size (pixels)</Form.Label>
                  <Form.Control
                    type="number"
                    size="sm"
                    className="mb-2 bg-dark text-light border-secondary"
                    min={32}
                    max={512}
                    value={tilePx}
                    onChange={(e) => setTilePx(Number(e.target.value) || 128)}
                  />
                  <Form.Label className="small text-secondary mb-1">Extra region set ID (experts)</Form.Label>
                  <Form.Control
                    type="text"
                    size="sm"
                    className="mb-2 bg-dark text-light border-secondary"
                    placeholder="Leave empty for automatic full-area stats only"
                    value={regionSetId}
                    onChange={(e) => setRegionSetId(e.target.value)}
                  />
                  <Button
                    variant="outline-secondary"
                    size="sm"
                    className="mb-2 w-100"
                    disabled={!primaryKey || !secondaryKey || compareLoading}
                    onClick={runCompare}
                  >
                    {compareLoading ? 'Working…' : 'Quick metadata-only compare'}
                  </Button>
                </div>
              </details>

              {comparisonId && (
                <div className="small text-muted mt-2 mb-0" style={{ fontSize: '0.7rem' }}>
                  Session ref: <code className="user-select-all">{comparisonId.slice(0, 12)}…</code>
                </div>
              )}
            </Card.Body>
          </Card>
        </Col>

        <Col lg={7} xl={8}>
          {changeErr && (
            <Alert variant="danger" className="py-2 small">
              {changeErr}
            </Alert>
          )}

          <Card className="analysis-card mb-3">
            <Card.Header>LULC change analysis</Card.Header>
            <Card.Body className="pt-2">
              <Nav
                variant="tabs"
                className="analysis-tabs mb-3"
                activeKey={changeTab}
                onSelect={(k) => setChangeTab(k || 'overview')}
              >
                <Nav.Item>
                  <Nav.Link eventKey="overview">Overview</Nav.Link>
                </Nav.Item>
                <Nav.Item>
                  <Nav.Link eventKey="categories">Categories</Nav.Link>
                </Nav.Item>
                <Nav.Item>
                  <Nav.Link eventKey="regions">Regions</Nav.Link>
                </Nav.Item>
                <Nav.Item>
                  <Nav.Link eventKey="tiles">Tiles</Nav.Link>
                </Nav.Item>
                <Nav.Item>
                  <Nav.Link eventKey="local">Local</Nav.Link>
                </Nav.Item>
                <Nav.Item>
                  <Nav.Link eventKey="comparison">Comparison</Nav.Link>
                </Nav.Item>
                <Nav.Item>
                  <Nav.Link eventKey="llm">LLM (grounded)</Nav.Link>
                </Nav.Item>
              </Nav>

              {!comparisonId && (
                <p className="text-secondary small mb-0">
                  Choose two saved LULC results (older → newer), then click <strong>Analyze changes</strong>. Use runs
                  produced from a GeoTIFF so change maps can align.
                </p>
              )}

              {changeTab === 'overview' && comparisonId && summary && (
                <div>
                  <p className="small text-secondary">
                    Valid pixels: {summary.valid_pixels?.toLocaleString?.() ?? summary.valid_pixels} · Changed:{' '}
                    {summary.changed_pixels?.toLocaleString?.() ?? summary.changed_pixels} · Unchanged:{' '}
                    {summary.unchanged_pixels?.toLocaleString?.() ?? summary.unchanged_pixels}
                  </p>
                  <div className="table-responsive">
                    <Table striped bordered hover size="sm" variant="dark" className="mb-2">
                      <thead>
                        <tr>
                          <th>Class</th>
                          <th>% baseline</th>
                          <th>% new</th>
                          <th>Δ %</th>
                        </tr>
                      </thead>
                      <tbody>
                        {labels.map((lb, i) => (
                          <tr key={lb}>
                            <td>{lb}</td>
                            <td>{summary.percent_baseline?.[i]}</td>
                            <td>{summary.percent_new?.[i]}</td>
                            <td>{summary.delta_percent?.[i]}</td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </div>
                  <details>
                    <summary className="small text-secondary">Raw summary.json</summary>
                    <pre className="analysis-json mt-2">{JSON.stringify(summary, null, 2)}</pre>
                  </details>
                  {matrix && (
                    <details className="mt-2">
                      <summary className="small text-secondary">Transition matrix</summary>
                      <pre className="analysis-json mt-2">{JSON.stringify(matrix.matrix, null, 2)}</pre>
                    </details>
                  )}
                </div>
              )}

              {changeTab === 'categories' && comparisonId && (
                <div>
                  <Form.Group className="mb-2">
                    <Form.Label className="small text-secondary mb-1">Land-cover class</Form.Label>
                    <Form.Select
                      size="sm"
                      className="bg-dark text-light border-secondary"
                      style={{ maxWidth: 420 }}
                      value={classIdx}
                      onChange={(e) => setClassIdx(Number(e.target.value))}
                    >
                      {labels.map((lb, i) => (
                        <option key={lb} value={i}>
                          {lb}
                        </option>
                      ))}
                    </Form.Select>
                  </Form.Group>
                  {classDetail ? (
                    <pre className="analysis-json">{JSON.stringify(classDetail, null, 2)}</pre>
                  ) : (
                    <Spinner size="sm" animation="border" />
                  )}
                </div>
              )}

              {changeTab === 'regions' && (
                <div>
                  <p className="text-secondary small mb-3">
                    The <strong>whole compared scene</strong> is summarized automatically—no setup needed. Refresh if
                    you just finished analysis.
                  </p>

                  {comparisonId && (
                    <>
                      <Button size="sm" className="mb-3" variant="outline-secondary" onClick={loadRegions}>
                        Refresh
                      </Button>
                      {regionsLoading ? (
                        <Spinner size="sm" animation="border" className="mb-2" />
                      ) : regionsData?.items?.length ? (
                        <>
                          <div className="table-responsive mb-3">
                            <Table striped bordered hover size="sm" variant="dark">
                              <thead>
                                <tr>
                                  <th>Area</th>
                                  <th>Valid pixels</th>
                                  <th>Note</th>
                                </tr>
                              </thead>
                              <tbody>
                                {regionsData.items.map((r) => (
                                  <tr key={r.region_id || r.name}>
                                    <td>{r.name || r.region_id}</td>
                                    <td>{r.valid_pixels?.toLocaleString?.() ?? r.valid_pixels}</td>
                                    <td className="small text-secondary">
                                      {r.region_id === 'full_extent' ? 'Automatic' : 'Custom boundary'}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </Table>
                          </div>
                          <details>
                            <summary className="small text-secondary">All numbers (JSON)</summary>
                            <pre className="analysis-json mt-2">{JSON.stringify(regionsData.items, null, 2)}</pre>
                          </details>
                        </>
                      ) : (
                        <p className="text-secondary small mb-0">
                          Could not load area summary. Try Refresh, or run <strong>Analyze changes</strong> again.
                        </p>
                      )}
                    </>
                  )}
                  {!comparisonId && (
                    <p className="text-secondary small mb-0">Run <strong>Analyze changes</strong> to see regions.</p>
                  )}

                  <details className="mt-4">
                    <summary className="small text-secondary" style={{ cursor: 'pointer' }}>
                      Advanced: add custom districts (GeoJSON)
                    </summary>
                    <div className="pt-3">
                      <p className="small text-secondary">
                        Only for GIS teams. Save a boundary file, enter its ID under &quot;Technical options&quot;, then
                        run <strong>Analyze changes</strong> again.
                      </p>
                      <Form.Label className="small text-secondary mb-1">Region set name</Form.Label>
                      <Form.Control
                        type="text"
                        size="sm"
                        className="mb-2 bg-dark text-light border-secondary"
                        value={regionSetId}
                        onChange={(e) => setRegionSetId(e.target.value)}
                      />
                      <Form.Label className="small text-secondary mb-1">GeoJSON</Form.Label>
                      <Form.Control
                        as="textarea"
                        rows={4}
                        className="mb-2 bg-dark text-light border-secondary font-monospace"
                        style={{ fontSize: '12px' }}
                        value={regionGeoJsonText}
                        onChange={(e) => setRegionGeoJsonText(e.target.value)}
                      />
                      <div className="d-flex flex-wrap gap-2 align-items-center mb-2">
                        <Button
                          size="sm"
                          variant="outline-info"
                          disabled={regionSaveLoading}
                          onClick={saveRegionSet}
                        >
                          {regionSaveLoading ? <Spinner size="sm" animation="border" /> : 'Save boundaries'}
                        </Button>
                        <Form.Control
                          type="file"
                          accept=".json,.geojson,application/json"
                          size="sm"
                          className="text-light"
                          style={{ maxWidth: 200 }}
                          onChange={(e) => {
                            const f = e.target.files?.[0];
                            if (!f) return;
                            const r = new FileReader();
                            r.onload = () => {
                              if (typeof r.result === 'string') setRegionGeoJsonText(r.result);
                            };
                            r.readAsText(f);
                            e.target.value = '';
                          }}
                        />
                      </div>
                      {regionSaveErr && (
                        <Alert variant="warning" className="py-2 small">
                          {regionSaveErr}
                        </Alert>
                      )}
                      {regionSaveOk && (
                        <Alert variant="success" className="py-2 small">
                          {regionSaveOk}
                        </Alert>
                      )}
                    </div>
                  </details>
                </div>
              )}

              {changeTab === 'tiles' && comparisonId && (
                <div>
                  <Button size="sm" className="mb-2" variant="outline-secondary" onClick={loadTiles}>
                    Refresh tiles
                  </Button>
                  {tilesData?.items?.length ? (
                    <div className="table-responsive">
                      <Table striped bordered hover size="sm" variant="dark">
                        <thead>
                          <tr>
                            <th>tile</th>
                            <th>changed px</th>
                            <th>valid px</th>
                          </tr>
                        </thead>
                        <tbody>
                          {tilesData.items.slice(0, 60).map((t) => (
                            <tr key={t.tile_id}>
                              <td>{t.tile_id}</td>
                              <td>{t.changed_pixels}</td>
                              <td>{t.valid_pixels}</td>
                            </tr>
                          ))}
                        </tbody>
                      </Table>
                    </div>
                  ) : (
                    <p className="text-secondary small">No tiles loaded.</p>
                  )}
                </div>
              )}

              {changeTab === 'comparison' && (
                <div>
                  {bundleA && bundleB && bundleA.task === 'lulc' && bundleB.task === 'lulc' ? (
                    <LulcComparisonTab
                      apiBase={getAnalysisBaseUrl()}
                      bundleA={bundleA}
                      bundleB={bundleB}
                    />
                  ) : (
                    <p className="text-secondary small mb-0">
                      Select two saved <strong>LULC</strong> runs as baseline (A) and newer (B). Comparison uses cached PNG
                      overlays from disk when both selections load successfully.
                    </p>
                  )}
                </div>
              )}

              {changeTab === 'local' && comparisonId && (
                <div>
                  <Row className="g-2 mb-2">
                    <Col xs={4}>
                      <Form.Label className="small text-secondary">Lon</Form.Label>
                      <Form.Control
                        size="sm"
                        className="bg-dark text-light border-secondary"
                        value={localLon}
                        onChange={(e) => setLocalLon(e.target.value)}
                        placeholder="e.g. 72.8"
                      />
                    </Col>
                    <Col xs={4}>
                      <Form.Label className="small text-secondary">Lat</Form.Label>
                      <Form.Control
                        size="sm"
                        className="bg-dark text-light border-secondary"
                        value={localLat}
                        onChange={(e) => setLocalLat(e.target.value)}
                        placeholder="e.g. 19.1"
                      />
                    </Col>
                    <Col xs={4}>
                      <Form.Label className="small text-secondary">Window px</Form.Label>
                      <Form.Control
                        type="number"
                        size="sm"
                        className="bg-dark text-light border-secondary"
                        value={localWin}
                        onChange={(e) => setLocalWin(Number(e.target.value) || 31)}
                      />
                    </Col>
                  </Row>
                  <Button size="sm" variant="info" disabled={localLoading} onClick={runLocalInsight}>
                    {localLoading ? <Spinner size="sm" animation="border" /> : 'Inspect location'}
                  </Button>
                  {localResult && (
                    <pre className="analysis-json mt-3">{JSON.stringify(localResult, null, 2)}</pre>
                  )}
                </div>
              )}

              {changeTab === 'llm' && (
                <div>
                  <p className="small text-secondary">
                    Uses tool calls over saved JSON summaries only. Set a comparison above first.
                  </p>
                  {llmGroundedError && (
                    <Alert variant="danger" className="py-2 small">
                      {llmGroundedError}
                    </Alert>
                  )}
                  <div className="analysis-chat-log mb-3">
                    {llmGroundedMessages.map((m, i) => (
                      <div key={i} className={`analysis-msg analysis-msg-${m.role}`}>
                        <div className="analysis-msg-role">{m.role}</div>
                        <div className="analysis-msg-text">{m.content}</div>
                      </div>
                    ))}
                  </div>
                  <div className="d-flex gap-2">
                    <Form.Control
                      as="textarea"
                      rows={2}
                      className="bg-dark text-light border-secondary"
                      placeholder="Ask about transition matrix, class deltas, top tiles…"
                      value={llmGroundedInput}
                      onChange={(e) => setLlmGroundedInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          sendGroundedLlm();
                        }
                      }}
                    />
                    <Button variant="success" disabled={llmGroundedLoading} onClick={sendGroundedLlm}>
                      {llmGroundedLoading ? <Spinner size="sm" animation="border" /> : 'Send'}
                    </Button>
                  </div>
                </div>
              )}
            </Card.Body>
          </Card>

          <Card className="analysis-card mb-3">
            <Card.Header>Inspector (primary A)</Card.Header>
            <Card.Body className="analysis-inspector">
              {loadingBundle && <Spinner animation="border" size="sm" />}
              {!primaryKey && <span className="text-secondary">Select a primary prediction.</span>}
              {bundleA && (
                <pre className="analysis-json">{JSON.stringify(bundleA, null, 2)}</pre>
              )}
            </Card.Body>
          </Card>

          {secondaryKey && bundleB && (
            <Card className="analysis-card mb-3">
              <Card.Header>Secondary (B) snapshot</Card.Header>
              <Card.Body className="analysis-inspector">
                <pre className="analysis-json">{JSON.stringify(bundleB, null, 2)}</pre>
              </Card.Body>
            </Card>
          )}

          <Card className="analysis-card mb-3">
            <Card.Header>Metadata comparison</Card.Header>
            <Card.Body>
              {!compareResult && !compareLoading && (
                <span className="text-secondary small">Run “Compare A vs B (metadata)” for shallow stats.</span>
              )}
              {compareLoading && <Spinner animation="border" size="sm" />}
              {compareResult && (
                <pre className="analysis-json">{JSON.stringify(compareResult, null, 2)}</pre>
              )}
            </Card.Body>
          </Card>

          <Card className="analysis-card">
            <Card.Header>Assistant (prediction metadata)</Card.Header>
            <Card.Body>
              <p className="small text-secondary">
                OpenAI chat with raw prediction JSON (not grounded on computed change tiles).
              </p>
              {chatError && (
                <Alert variant="danger" className="py-2 small">
                  {chatError}
                </Alert>
              )}
              <div className="analysis-chat-log mb-3">
                {chatMessages.map((m, i) => {
                  const { displayText, chartSpec } =
                    m.role === 'assistant'
                      ? parseChartFromReply(m.content)
                      : { displayText: m.content, chartSpec: null };
                  return (
                    <div key={i} className={`analysis-msg analysis-msg-${m.role}`}>
                      <div className="analysis-msg-role">{m.role}</div>
                      <div className="analysis-msg-text">{displayText}</div>
                      {chartSpec && <AnalysisChart chartSpec={chartSpec} />}
                    </div>
                  );
                })}
              </div>
              <div className="d-flex gap-2">
                <Form.Control
                  as="textarea"
                  rows={2}
                  className="bg-dark text-light border-secondary"
                  placeholder="Ask a question…"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      sendChat();
                    }
                  }}
                />
                <Button variant="success" disabled={chatLoading} onClick={sendChat}>
                  {chatLoading ? <Spinner size="sm" animation="border" /> : 'Send'}
                </Button>
              </div>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </Container>
  );
}

export default function AnalysisPage() {
  return (
    <UiScopedView flag="show_analysis">
      <AnalysisPageInner />
    </UiScopedView>
  );
}
