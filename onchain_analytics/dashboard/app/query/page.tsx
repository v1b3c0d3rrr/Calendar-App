'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';

const SUGGESTED_QUERIES = [
  'How many swaps in the last 7 days?',
  'Top 10 holders by balance',
  'Daily swap volume in USDT for the last 30 days',
  'Buy vs sell count in the last 24 hours',
  'Largest 5 swaps by USDT amount',
  'Average price per day for the last 14 days',
];

const CHART_COLORS = [
  '#6366f1', '#06b6d4', '#f59e0b', '#10b981',
  '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6',
];

type QueryResult = {
  question: string;
  sql: string;
  columns: string[];
  rows: (string | number | boolean | null)[][];
  row_count: number;
  visualization_hint: string;
};

export default function QueryPage() {
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'auto' | 'table' | 'chart'>('auto');

  async function handleSubmit(q?: string) {
    const text = q ?? question;
    if (!text.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await api.submitQuery(text.trim());
      setResult(data);
      setViewMode('auto');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Something went wrong';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  // Convert rows to objects for Recharts
  function chartData() {
    if (!result) return [];
    return result.rows.map((row) => {
      const obj: Record<string, unknown> = {};
      result.columns.forEach((col, i) => {
        obj[col] = row[i];
      });
      return obj;
    });
  }

  function shouldShowChart(): boolean {
    if (!result || result.row_count === 0) return false;
    if (viewMode === 'table') return false;
    if (viewMode === 'chart') return true;
    // auto: follow the hint
    return result.visualization_hint !== 'table';
  }

  const hint = result?.visualization_hint ?? 'table';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Ask Your Data</h1>
        <p className="text-slate-500 text-sm mt-1">
          Type a question in plain English and get results from the database.
        </p>
      </div>

      {/* Input */}
      <form
        onSubmit={(e) => { e.preventDefault(); handleSubmit(); }}
        className="flex gap-3"
      >
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. How many swaps happened today?"
          className="flex-1 px-4 py-3 rounded-xl border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-acu-primary text-sm"
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="px-6 py-3 bg-acu-primary text-white rounded-xl text-sm font-medium disabled:opacity-50 hover:opacity-90 transition-opacity"
        >
          {loading ? 'Thinking...' : 'Ask'}
        </button>
      </form>

      {/* Suggested queries */}
      <div className="flex flex-wrap gap-2">
        {SUGGESTED_QUERIES.map((q) => (
          <button
            key={q}
            onClick={() => { setQuestion(q); handleSubmit(q); }}
            className="px-3 py-1.5 text-xs rounded-full border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Loading skeleton */}
      {loading && (
        <div className="bg-white dark:bg-slate-800 rounded-xl p-6 shadow-sm space-y-3">
          <div className="h-4 w-1/3 bg-slate-200 dark:bg-slate-700 rounded animate-pulse" />
          <div className="h-4 w-full bg-slate-200 dark:bg-slate-700 rounded animate-pulse" />
          <div className="h-4 w-2/3 bg-slate-200 dark:bg-slate-700 rounded animate-pulse" />
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4 text-red-700 dark:text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-4">
          {/* SQL preview */}
          <details className="bg-white dark:bg-slate-800 rounded-xl shadow-sm">
            <summary className="px-4 py-3 cursor-pointer text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300">
              View generated SQL ({result.row_count} row{result.row_count !== 1 ? 's' : ''})
            </summary>
            <pre className="px-4 pb-4 text-xs font-mono text-slate-600 dark:text-slate-400 overflow-x-auto whitespace-pre-wrap">
              {result.sql}
            </pre>
          </details>

          {/* View toggle */}
          {result.row_count > 0 && hint !== 'table' && (
            <div className="flex space-x-1 bg-slate-100 dark:bg-slate-800 rounded-lg p-1 w-fit">
              {(['auto', 'table', 'chart'] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setViewMode(mode)}
                  className={cn(
                    'px-3 py-1 text-sm rounded-md capitalize transition-colors',
                    viewMode === mode
                      ? 'bg-white dark:bg-slate-700 shadow'
                      : 'text-slate-600 dark:text-slate-400'
                  )}
                >
                  {mode}
                </button>
              ))}
            </div>
          )}

          {/* Chart view */}
          {shouldShowChart() && (
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm p-4">
              <ResponsiveContainer width="100%" height={350}>
                {hint === 'line_chart' ? (
                  <LineChart data={chartData()}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey={result.columns[0]} tick={{ fontSize: 12 }} />
                    <YAxis tick={{ fontSize: 12 }} />
                    <Tooltip />
                    <Legend />
                    {result.columns.slice(1).map((col, i) => (
                      <Line
                        key={col}
                        type="monotone"
                        dataKey={col}
                        stroke={CHART_COLORS[i % CHART_COLORS.length]}
                        strokeWidth={2}
                        dot={false}
                      />
                    ))}
                  </LineChart>
                ) : hint === 'pie_chart' ? (
                  <PieChart>
                    <Pie
                      data={chartData()}
                      dataKey={result.columns[1]}
                      nameKey={result.columns[0]}
                      cx="50%"
                      cy="50%"
                      outerRadius={120}
                      label
                    >
                      {chartData().map((_, i) => (
                        <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                ) : (
                  <BarChart data={chartData()}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey={result.columns[0]} tick={{ fontSize: 12 }} />
                    <YAxis tick={{ fontSize: 12 }} />
                    <Tooltip />
                    <Legend />
                    {result.columns.slice(1).map((col, i) => (
                      <Bar
                        key={col}
                        dataKey={col}
                        fill={CHART_COLORS[i % CHART_COLORS.length]}
                        radius={[4, 4, 0, 0]}
                      />
                    ))}
                  </BarChart>
                )}
              </ResponsiveContainer>
            </div>
          )}

          {/* Table view */}
          {!shouldShowChart() && result.row_count > 0 && (
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-slate-50 dark:bg-slate-700/50">
                    <tr className="text-left text-xs text-slate-500 uppercase">
                      {result.columns.map((col) => (
                        <th key={col} className="px-4 py-3 font-medium">{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                    {result.rows.map((row, i) => (
                      <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors">
                        {row.map((cell, j) => (
                          <td key={j} className="px-4 py-3 text-sm tabular-nums">
                            {cell === null ? <span className="text-slate-400">null</span> : String(cell)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* No results */}
          {result.row_count === 0 && (
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm p-8 text-center text-slate-500">
              No results found for this query.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
