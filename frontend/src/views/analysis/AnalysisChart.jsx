import React, { useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
} from 'recharts';

const COLORS = ['#60a5fa', '#34d399', '#fbbf24', '#f87171', '#a78bfa', '#fb923c'];

/**
 * chartSpec: { type: 'bar'|'pie'|'line', title, labels: [], series: [{ name?, values: [] }] }
 */
export default function AnalysisChart({ chartSpec }) {
  const spec = chartSpec?.chart || chartSpec;
  if (!spec || !spec.type) return null;

  const type = String(spec.type).toLowerCase();
  const title = spec.title || 'Chart';
  const labels = Array.isArray(spec.labels) ? spec.labels : [];
  const series = Array.isArray(spec.series) ? spec.series : [];

  const barData = useMemo(() => {
    const rows = [];
    const vals = series[0]?.values || [];
    for (let i = 0; i < Math.max(labels.length, vals.length); i++) {
      rows.push({
        name: String(labels[i] ?? i),
        value: Number(vals[i]) || 0,
      });
    }
    return rows;
  }, [labels, series]);

  const pieData = useMemo(() => {
    const vals = series[0]?.values || [];
    return labels.map((l, i) => ({
      name: String(l),
      value: Number(vals[i]) || 0,
    }));
  }, [labels, series]);

  const lineData = useMemo(() => {
    const rows = [];
    const maxLen = Math.max(
      labels.length,
      ...series.map((s) => (Array.isArray(s.values) ? s.values.length : 0)),
      0
    );
    for (let i = 0; i < maxLen; i++) {
      const row = { name: String(labels[i] ?? i) };
      series.forEach((s, si) => {
        const name = s.name || `series_${si}`;
        row[name] = Number(Array.isArray(s.values) ? s.values[i] : 0) || 0;
      });
      rows.push(row);
    }
    return rows;
  }, [labels, series]);

  const wrapStyle = { width: '100%', height: 280, marginTop: 12 };

  if (type === 'pie') {
    return (
      <div className="analysis-chart-wrap">
        <div className="analysis-chart-title">{title}</div>
        <ResponsiveContainer width="100%" height={260}>
          <PieChart>
            <Pie
              data={pieData}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              outerRadius={90}
              label
            >
              {pieData.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </div>
    );
  }

  if (type === 'line') {
    return (
      <div className="analysis-chart-wrap">
        <div className="analysis-chart-title">{title}</div>
        <div style={wrapStyle}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={lineData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155' }} />
              <Legend />
              {series.map((s, si) => (
                <Line
                  key={si}
                  type="monotone"
                  dataKey={s.name || `series_${si}`}
                  stroke={COLORS[si % COLORS.length]}
                  dot={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  return (
    <div className="analysis-chart-wrap">
      <div className="analysis-chart-title">{title}</div>
      <div style={wrapStyle}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={barData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} />
            <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
            <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155' }} />
            <Bar dataKey="value" fill="#60a5fa" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function parseChartFromReply(text) {
  if (!text || typeof text !== 'string') return { displayText: text, chartSpec: null };
  const m = text.match(/```chart\s*([\s\S]*?)```/);
  if (!m) return { displayText: text, chartSpec: null };
  try {
    const json = JSON.parse(m[1].trim());
    const displayText = text.replace(/```chart\s*[\s\S]*?```/, '').trim();
    return { displayText, chartSpec: json };
  } catch {
    return { displayText: text, chartSpec: null };
  }
}
