"""Generate a single-file HTML dashboard from benchmark results."""

from __future__ import annotations

import json
from pathlib import Path

from .reporter import RunSummary
from .runner import TaskResult


def generate_dashboard(summary: RunSummary, results: list[TaskResult], output_path: str | Path) -> Path:
    """Generate an interactive HTML dashboard."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results_json = json.dumps([r.to_dict() for r in results])
    config_json = json.dumps(summary.by_config)
    category_json = json.dumps(summary.by_category)
    task_json = json.dumps(summary.by_task)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Proof Dashboard — {summary.name}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 2rem; }}
h1 {{ font-size: 1.5rem; font-weight: 600; margin-bottom: 0.25rem; }}
.subtitle {{ color: #888; font-size: 0.85rem; margin-bottom: 2rem; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
.card {{ background: #141414; border: 1px solid #222; border-radius: 8px; padding: 1.25rem; }}
.card .label {{ color: #888; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }}
.card .value {{ font-size: 1.75rem; font-weight: 700; margin-top: 0.25rem; }}
.card .value.green {{ color: #22c55e; }}
.card .value.red {{ color: #ef4444; }}
.card .value.blue {{ color: #3b82f6; }}
.card .value.yellow {{ color: #eab308; }}
.charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 2rem; }}
.chart-container {{ background: #141414; border: 1px solid #222; border-radius: 8px; padding: 1.25rem; }}
.chart-container h2 {{ font-size: 0.9rem; font-weight: 600; margin-bottom: 1rem; }}
canvas {{ max-height: 300px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
th {{ text-align: left; color: #888; font-weight: 500; padding: 0.5rem 0.75rem; border-bottom: 1px solid #222; }}
td {{ padding: 0.5rem 0.75rem; border-bottom: 1px solid #1a1a1a; }}
tr:hover {{ background: #1a1a1a; }}
.pass {{ color: #22c55e; }}
.fail {{ color: #ef4444; }}
.section {{ background: #141414; border: 1px solid #222; border-radius: 8px; padding: 1.25rem; margin-bottom: 1.5rem; }}
.section h2 {{ font-size: 0.9rem; font-weight: 600; margin-bottom: 1rem; }}
@media (max-width: 768px) {{ .charts {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>

<h1>Proof Dashboard</h1>
<p class="subtitle">{summary.name} &mdash; {summary.timestamp}</p>

<div class="grid">
  <div class="card">
    <div class="label">Success Rate</div>
    <div class="value green">{summary.success_rate:.0%}</div>
  </div>
  <div class="card">
    <div class="label">Total Tasks</div>
    <div class="value blue">{summary.total_tasks}</div>
  </div>
  <div class="card">
    <div class="label">Avg Latency</div>
    <div class="value yellow">{summary.avg_latency_ms:.0f}ms</div>
  </div>
  <div class="card">
    <div class="label">P95 Latency</div>
    <div class="value yellow">{summary.p95_latency_ms:.0f}ms</div>
  </div>
  <div class="card">
    <div class="label">Total Cost</div>
    <div class="value">${summary.total_cost_usd:.4f}</div>
  </div>
  <div class="card">
    <div class="label">Total Tokens</div>
    <div class="value">{summary.total_input_tokens + summary.total_output_tokens:,}</div>
  </div>
</div>

<div class="charts">
  <div class="chart-container">
    <h2>Success Rate by Config</h2>
    <canvas id="configChart"></canvas>
  </div>
  <div class="chart-container">
    <h2>Failure Taxonomy</h2>
    <canvas id="taxonomyChart"></canvas>
  </div>
  <div class="chart-container">
    <h2>Latency by Config</h2>
    <canvas id="latencyChart"></canvas>
  </div>
  <div class="chart-container">
    <h2>Cost by Config</h2>
    <canvas id="costChart"></canvas>
  </div>
</div>

<div class="section">
  <h2>Detailed Results</h2>
  <table>
    <thead>
      <tr>
        <th>Task</th>
        <th>Config</th>
        <th>Iter</th>
        <th>Status</th>
        <th>Category</th>
        <th>Latency</th>
        <th>Tokens</th>
        <th>Cost</th>
        <th>Retries</th>
      </tr>
    </thead>
    <tbody id="resultsBody"></tbody>
  </table>
</div>

<script>
const results = {results_json};
const configData = {config_json};
const categoryData = {category_json};
const taskData = {task_json};

Chart.defaults.color = '#888';
Chart.defaults.borderColor = '#222';

// Config success rate chart
const configNames = Object.keys(configData);
new Chart(document.getElementById('configChart'), {{
  type: 'bar',
  data: {{
    labels: configNames,
    datasets: [{{
      label: 'Passed',
      data: configNames.map(n => configData[n].passed),
      backgroundColor: '#22c55e',
    }}, {{
      label: 'Failed',
      data: configNames.map(n => configData[n].failed),
      backgroundColor: '#ef4444',
    }}]
  }},
  options: {{ responsive: true, scales: {{ x: {{ stacked: true }}, y: {{ stacked: true, beginAtZero: true }} }} }}
}});

// Taxonomy chart
const catLabels = Object.keys(categoryData);
const catColors = catLabels.map(c => {{
  if (c === 'success') return '#22c55e';
  if (c.includes('recovery')) return '#3b82f6';
  if (c.includes('partial') || c.includes('format') || c.includes('schema')) return '#eab308';
  return '#ef4444';
}});
new Chart(document.getElementById('taxonomyChart'), {{
  type: 'doughnut',
  data: {{
    labels: catLabels,
    datasets: [{{ data: catLabels.map(c => categoryData[c]), backgroundColor: catColors }}]
  }},
  options: {{ responsive: true, plugins: {{ legend: {{ position: 'right' }} }} }}
}});

// Latency chart
new Chart(document.getElementById('latencyChart'), {{
  type: 'bar',
  data: {{
    labels: configNames,
    datasets: [{{
      label: 'Avg Latency (ms)',
      data: configNames.map(n => Math.round(configData[n].avg_latency_ms)),
      backgroundColor: '#eab308',
    }}]
  }},
  options: {{ responsive: true, scales: {{ y: {{ beginAtZero: true }} }} }}
}});

// Cost chart
new Chart(document.getElementById('costChart'), {{
  type: 'bar',
  data: {{
    labels: configNames,
    datasets: [{{
      label: 'Cost (USD)',
      data: configNames.map(n => configData[n].total_cost_usd),
      backgroundColor: '#8b5cf6',
    }}]
  }},
  options: {{ responsive: true, scales: {{ y: {{ beginAtZero: true }} }} }}
}});

// Results table
const tbody = document.getElementById('resultsBody');
results.forEach(r => {{
  const tr = document.createElement('tr');
  const status = r.passed ? '<span class="pass">PASS</span>' : '<span class="fail">FAIL</span>';
  tr.innerHTML = `
    <td>${{r.task_id}}</td>
    <td>${{r.config_name}}</td>
    <td>${{r.iteration}}</td>
    <td>${{status}}</td>
    <td>${{r.failure_category}}</td>
    <td>${{Math.round(r.latency_ms)}}ms</td>
    <td>${{r.total_tokens.toLocaleString()}}</td>
    <td>$${{r.cost_usd.toFixed(6)}}</td>
    <td>${{r.retries}}</td>
  `;
  tbody.appendChild(tr);
}});
</script>
</body>
</html>"""

    output_path.write_text(html)
    return output_path
