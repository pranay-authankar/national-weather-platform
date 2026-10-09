import { useState, useEffect, type FC } from 'react';
import { AlertCircle, Activity, ShieldCheck, AlertTriangle, Layers } from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
  CartesianGrid,
} from 'recharts';
import { getAnalyticsSummary } from '../services/analyticsApi';
import type { AnalyticsSummary } from '../types/analytics';

function formatDateLabel(dateStr: string): string {
  if (!dateStr) return '';
  try {
    const d = new Date(`${dateStr}T00:00:00`);
    if (isNaN(d.getTime())) return dateStr;
    return new Intl.DateTimeFormat('en-IN', {
      day: 'numeric',
      month: 'short',
    }).format(d);
  } catch {
    return dateStr;
  }
}

function formatFullDate(dateStr: string): string {
  if (!dateStr) return '';
  try {
    const d = new Date(`${dateStr}T00:00:00`);
    if (isNaN(d.getTime())) return dateStr;
    return new Intl.DateTimeFormat('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    }).format(d);
  } catch {
    return dateStr;
  }
}

const SOURCE_COLORS = [
  '#0284c7',
  '#0d9488',
  '#f59e0b',
  '#6366f1',
  '#ec4899',
  '#8b5cf6',
];

const VERIFICATION_COLORS: Record<string, string> = {
  Verified: '#16a34a',
  Unverified: '#ea580c',
  Duplicate: '#64748b',
};

export const AnalyticsPage: FC = () => {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    getAnalyticsSummary()
      .then((data) => {
        if (!isMounted) return;
        setSummary(data);
        setLoading(false);
      })
      .catch(() => {
        if (!isMounted) return;
        setError('Unable to load analytics.');
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const eventTypeData = summary?.events_by_type
    ? summary.events_by_type
        .filter((item) => typeof item.count === 'number' && item.count > 0)
        .map((item) => ({ name: item.event_type, count: item.count }))
    : [];

  const stateData = summary?.events_by_state
    ? summary.events_by_state
        .filter((item) => typeof item.count === 'number' && item.count > 0)
        .map((item) => ({ state: item.state, count: item.count }))
        .slice(0, 10)
    : [];

  const sourceData = summary?.events_by_source
    ? summary.events_by_source
        .filter((item) => typeof item.count === 'number' && item.count > 0)
        .map((item) => ({ source: item.source, count: item.count }))
    : [];

  const verificationList = summary?.verification_breakdown || summary?.events_by_verification;
  const verificationData = verificationList
    ? verificationList
        .filter((item) => typeof item.count === 'number' && item.count > 0)
        .map((item) => ({ name: item.status, count: item.count }))
    : summary
    ? [
        { name: 'Verified', count: summary.verified_events || 0 },
        { name: 'Unverified', count: summary.unverified_events || 0 },
        { name: 'Duplicate', count: summary.duplicate_events || 0 },
      ].filter((item) => item.count > 0)
    : [];

  const eventsOverTimeData = summary?.events_over_time
    ? summary.events_over_time
        .filter((item) => item.date && typeof item.count === 'number')
        .map((item) => ({ date: item.date, count: item.count }))
    : [];

  const isEmpty =
    !summary ||
    (summary.total_events === 0 &&
      eventTypeData.length === 0 &&
      stateData.length === 0 &&
      sourceData.length === 0 &&
      verificationData.length === 0 &&
      eventsOverTimeData.length === 0);

  return (
    <div className="analytics-page">
      <div className="page-header">
        <h2 className="page-title">Weather Big Data Analytics</h2>
        <p className="page-subtitle">
          Aggregated event volume, hazard types, regional coverage, and data source distribution.
        </p>
      </div>

      {loading && (
        <div className="dashboard-state-box loading">
          <span className="dashboard-state-text">Loading analytics...</span>
        </div>
      )}

      {!loading && error && (
        <div className="dashboard-error-banner" role="alert">
          <AlertCircle size={15} className="error-banner-icon" aria-hidden="true" />
          <span className="error-banner-text">{error}</span>
        </div>
      )}

      {!loading && !error && isEmpty && (
        <div className="dashboard-state-box empty">
          <span className="dashboard-state-text">No analytics data available.</span>
        </div>
      )}

      {!loading && !error && summary && !isEmpty && (
        <div className="analytics-content">
          {/* Summary Metric Cards (Max 4 cards) */}
          <div className="analytics-summary-cards">
            <div className="summary-card">
              <div className="summary-card-header">
                <span className="summary-card-label">Total Events</span>
                <Activity size={16} className="summary-card-icon total" aria-hidden="true" />
              </div>
              <div className="summary-card-value">{summary.total_events}</div>
              <div className="summary-card-sub">Recorded weather events</div>
            </div>

            <div className="summary-card">
              <div className="summary-card-header">
                <span className="summary-card-label">Verified</span>
                <ShieldCheck size={16} className="summary-card-icon verified" aria-hidden="true" />
              </div>
              <div className="summary-card-value">{summary.verified_events}</div>
              <div className="summary-card-sub">Confirmed accuracy</div>
            </div>

            <div className="summary-card">
              <div className="summary-card-header">
                <span className="summary-card-label">Unverified</span>
                <AlertTriangle size={16} className="summary-card-icon unverified" aria-hidden="true" />
              </div>
              <div className="summary-card-value">{summary.unverified_events}</div>
              <div className="summary-card-sub">Pending verification</div>
            </div>

            <div className="summary-card">
              <div className="summary-card-header">
                <span className="summary-card-label">Duplicate</span>
                <Layers size={16} className="summary-card-icon duplicate" aria-hidden="true" />
              </div>
              <div className="summary-card-value">{summary.duplicate_events}</div>
              <div className="summary-card-sub">Redundant reports</div>
            </div>
          </div>

          {/* Charts Grid */}
          <div className="analytics-charts-grid">
            {/* Events Over Time Timeline Chart */}
            <div className="analytics-chart-card full-width">
              <div className="chart-card-header">
                <div className="chart-card-titles">
                  <h3 className="chart-card-title">Events Over Time</h3>
                  <span className="chart-card-sub">Number of weather events recorded over time</span>
                </div>
                {eventsOverTimeData.length > 0 && (
                  <span className="section-count">
                    {eventsOverTimeData.length} {eventsOverTimeData.length === 1 ? 'day' : 'days'}
                  </span>
                )}
              </div>
              <div className="chart-container">
                {eventsOverTimeData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={240}>
                    <LineChart
                      data={eventsOverTimeData}
                      margin={{ top: 12, right: 24, left: -20, bottom: 20 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                      <XAxis
                        dataKey="date"
                        tickFormatter={formatDateLabel}
                        tick={{ fill: '#64748b', fontSize: 11 }}
                        tickLine={false}
                        axisLine={{ stroke: '#e2e8f0' }}
                      />
                      <YAxis
                        allowDecimals={false}
                        tick={{ fill: '#64748b', fontSize: 11 }}
                        tickLine={false}
                        axisLine={{ stroke: '#e2e8f0' }}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#0f172a',
                          borderColor: '#1e293b',
                          borderRadius: '6px',
                          color: '#f8fafc',
                          fontSize: '12px',
                        }}
                        labelFormatter={(label) => formatFullDate(String(label))}
                        itemStyle={{ color: '#38bdf8' }}
                        formatter={(val) => [`${val} ${Number(val) === 1 ? 'event' : 'events'}`, 'Recorded']}
                      />
                      <Line
                        type="monotone"
                        dataKey="count"
                        name="Events"
                        stroke="#0284c7"
                        strokeWidth={2}
                        dot={{ r: 4, fill: '#0284c7', stroke: '#ffffff', strokeWidth: 2 }}
                        activeDot={{ r: 6, fill: '#0284c7', stroke: '#ffffff', strokeWidth: 2 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="analytics-chart-empty">
                    <span>No event timeline data available.</span>
                  </div>
                )}
              </div>
            </div>

            {/* Event Types Chart */}
            {eventTypeData.length > 0 && (
              <div className="analytics-chart-card">
                <div className="chart-card-header">
                  <h3 className="chart-card-title">Event Types</h3>
                  <span className="section-count">{eventTypeData.length} types</span>
                </div>
                <div className="chart-container">
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart
                      data={eventTypeData}
                      margin={{ top: 12, right: 12, left: -20, bottom: 35 }}
                    >
                      <XAxis
                        dataKey="name"
                        tick={{ fill: '#64748b', fontSize: 11 }}
                        interval={0}
                        angle={-30}
                        textAnchor="end"
                        tickLine={false}
                      />
                      <YAxis
                        allowDecimals={false}
                        tick={{ fill: '#64748b', fontSize: 11 }}
                        tickLine={false}
                        axisLine={{ stroke: '#e2e8f0' }}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#0f172a',
                          borderColor: '#1e293b',
                          borderRadius: '6px',
                          color: '#f8fafc',
                          fontSize: '12px',
                        }}
                        itemStyle={{ color: '#38bdf8' }}
                      />
                      <Bar dataKey="count" fill="#0284c7" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* Geographic Distribution (By State) */}
            {stateData.length > 0 && (
              <div className="analytics-chart-card">
                <div className="chart-card-header">
                  <h3 className="chart-card-title">By State</h3>
                  <span className="section-count">{stateData.length} states</span>
                </div>
                <div className="chart-container">
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart
                      data={stateData}
                      margin={{ top: 12, right: 12, left: -20, bottom: 35 }}
                    >
                      <XAxis
                        dataKey="state"
                        tick={{ fill: '#64748b', fontSize: 11 }}
                        interval={0}
                        angle={-30}
                        textAnchor="end"
                        tickLine={false}
                      />
                      <YAxis
                        allowDecimals={false}
                        tick={{ fill: '#64748b', fontSize: 11 }}
                        tickLine={false}
                        axisLine={{ stroke: '#e2e8f0' }}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#0f172a',
                          borderColor: '#1e293b',
                          borderRadius: '6px',
                          color: '#f8fafc',
                          fontSize: '12px',
                        }}
                        itemStyle={{ color: '#0ea5e9' }}
                      />
                      <Bar dataKey="count" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* Source Distribution */}
            {sourceData.length > 0 && (
              <div className="analytics-chart-card">
                <div className="chart-card-header">
                  <h3 className="chart-card-title">By Source</h3>
                  <span className="section-count">{sourceData.length} sources</span>
                </div>
                <div className="chart-container donut-chart-layout">
                  <div className="donut-wrapper">
                    <ResponsiveContainer width="100%" height={180}>
                      <PieChart>
                        <Pie
                          data={sourceData}
                          dataKey="count"
                          nameKey="source"
                          cx="50%"
                          cy="50%"
                          innerRadius={45}
                          outerRadius={70}
                          paddingAngle={3}
                        >
                          {sourceData.map((_, index) => (
                            <Cell
                              key={`source-cell-${index}`}
                              fill={SOURCE_COLORS[index % SOURCE_COLORS.length]}
                            />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            backgroundColor: '#0f172a',
                            borderColor: '#1e293b',
                            borderRadius: '6px',
                            color: '#f8fafc',
                            fontSize: '12px',
                          }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="chart-breakdown-list">
                    {sourceData.map((item, idx) => (
                      <div key={item.source} className="breakdown-item">
                        <div className="breakdown-item-left">
                          <span
                            className="breakdown-dot"
                            style={{ backgroundColor: SOURCE_COLORS[idx % SOURCE_COLORS.length] }}
                          />
                          <span className="breakdown-label">{item.source}</span>
                        </div>
                        <span className="breakdown-value">{item.count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Verification Breakdown */}
            {verificationData.length > 0 && (
              <div className="analytics-chart-card">
                <div className="chart-card-header">
                  <h3 className="chart-card-title">By Verification Status</h3>
                  <span className="section-count">{verificationData.length} statuses</span>
                </div>
                <div className="chart-container donut-chart-layout">
                  <div className="donut-wrapper">
                    <ResponsiveContainer width="100%" height={180}>
                      <PieChart>
                        <Pie
                          data={verificationData}
                          dataKey="count"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          innerRadius={45}
                          outerRadius={70}
                          paddingAngle={3}
                        >
                          {verificationData.map((entry) => (
                            <Cell
                              key={`verif-cell-${entry.name}`}
                              fill={VERIFICATION_COLORS[entry.name] || '#64748b'}
                            />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            backgroundColor: '#0f172a',
                            borderColor: '#1e293b',
                            borderRadius: '6px',
                            color: '#f8fafc',
                            fontSize: '12px',
                          }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="chart-breakdown-list">
                    {verificationData.map((item) => (
                      <div key={item.name} className="breakdown-item">
                        <div className="breakdown-item-left">
                          <span
                            className="breakdown-dot"
                            style={{
                              backgroundColor: VERIFICATION_COLORS[item.name] || '#64748b',
                            }}
                          />
                          <span className="breakdown-label">{item.name}</span>
                        </div>
                        <span className="breakdown-value">{item.count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default AnalyticsPage;
