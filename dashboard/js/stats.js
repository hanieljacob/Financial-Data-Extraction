import { METRICS, M_LABEL } from './config.js';

export function renderStats(runId, summary, runs) {
  const ls = summary.filter(d => d.run_id === runId);
  const overall = +(ls.reduce((s, d) => s + d.accuracy_pct, 0) / ls.length).toFixed(1);
  const cards = [
    {
      label: 'Overall Accuracy',
      val: overall + '%',
      sub: `Avg 3 metrics · Cycle ${runs.indexOf(runId) + 1}`,
      cls: 'green',
    },
    ...METRICS.map(m => {
      const s = ls.find(d => d.metric === m);
      return {
        label: M_LABEL[m],
        val: s ? s.accuracy_pct + '%' : '—',
        sub: s ? `${s.n_correct}/${s.n_total} correct` : '',
        cls: m === 'operating_income' ? 'blue' : m === 'stockholders_equity' ? 'gold' : 'purple',
      };
    }),
  ];
  document.getElementById('stats').innerHTML = cards.map(c =>
    `<div class="sc">
       <div class="sc-label">${c.label}</div>
       <div class="sc-val ${c.cls}">${c.val}</div>
       <div class="sc-sub">${c.sub}</div>
     </div>`
  ).join('');
}
