import { renderStats }        from './stats.js';
import { renderRunFilter }    from './runFilter.js';
import { renderAccuracyChart } from './accuracyChart.js';
import { renderHeatmap }      from './heatmap.js';
import { renderForest }       from './forestPlot.js';

async function loadData() {
  const [resultsRes, summaryRes] = await Promise.all([
    fetch('/api/results'),
    fetch('/api/summary'),
  ]);
  if (!resultsRes.ok || !summaryRes.ok) throw new Error('Failed to fetch data from server');
  return {
    results: await resultsRes.json(),
    summary: await summaryRes.json(),
  };
}

function showError(msg) {
  document.getElementById('stats').innerHTML =
    `<div class="error-banner" style="grid-column:1/-1">
       <strong>Could not load data:</strong> ${msg}<br>
       Make sure <code>server.py</code> is running.
     </div>`;
}

async function init() {
  let results, summary;
  try {
    ({ results, summary } = await loadData());
  } catch (err) {
    showError(err.message);
    return;
  }

  const runs      = [...new Set(summary.map(d => d.run_id))].sort();
  let selectedRun = runs[runs.length - 1];

  function getSelectedRun() { return selectedRun; }

  function onSelect(run) {
    selectedRun = run;
    document.querySelectorAll('.run-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.run === run);
    });
    if (window._drawAccHighlight) window._drawAccHighlight();
    renderStats(selectedRun, summary, runs);
    renderHeatmap(results, selectedRun);
    renderForest(results, selectedRun);
  }

  renderStats(selectedRun, summary, runs);
  renderRunFilter(runs, summary, selectedRun, onSelect);

  const drawHighlight = renderAccuracyChart(runs, summary, getSelectedRun, run => {
    onSelect(run);
    renderRunFilter(runs, summary, selectedRun, onSelect);
  });
  window._drawAccHighlight = drawHighlight;

  renderHeatmap(results, selectedRun);
  renderForest(results, selectedRun);
}

init();
