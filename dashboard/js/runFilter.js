import * as d3 from 'd3';

export function renderRunFilter(runs, summary, selectedRun, onSelect) {
  const container = d3.select('#run-filter');
  container.html('');
  container.append('span').attr('class', 'run-filter-label').text('Viewing cycle:');

  runs.forEach((run, i) => {
    const ls  = summary.filter(d => d.run_id === run);
    const avg = ls.length ? +(ls.reduce((s, d) => s + d.accuracy_pct, 0) / ls.length).toFixed(1) : null;
    const btn = container.append('button')
      .attr('class', 'run-btn' + (run === selectedRun ? ' active' : ''))
      .attr('data-run', run);
    btn.append('span').text(`Cycle ${i + 1} · ${run.slice(11, 16)}`);
    if (avg !== null) btn.append('span').attr('class', 'run-accuracy-badge').text(avg + '%');
    btn.on('click', () => {
      document.querySelectorAll('.run-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.run === run);
      });
      onSelect(run);
    });
  });
}
