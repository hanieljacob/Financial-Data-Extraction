import * as d3 from 'd3';
import { METRICS, M_LABEL, M_COLOR } from './config.js';
import { showTip, moveTip, hideTip } from './tooltip.js';

export function renderForest(results, selectedRun) {
  d3.select('#forest').html('');
  const ld = results.filter(d => d.run_id === selectedRun);

  METRICS.forEach(metric => {
    const raw  = ld.filter(d => d.metric === metric && d.extracted !== null && d.ground_truth !== null && d.ground_truth !== 0);
    const data = raw.map(d => ({ ...d, ratio: d.extracted / d.ground_truth }))
      .sort((a, b) => Math.abs(a.ground_truth) - Math.abs(b.ground_truth));

    const col = M_COLOR[metric];
    const Mg  = { top: 30, right: 14, bottom: 46, left: 54 };
    const W   = 360, H = 60 + data.length * 18;
    const w   = W - Mg.left - Mg.right, h = H - Mg.top - Mg.bottom;

    const ratios = data.map(d => d.ratio);
    const rMin   = Math.min(d3.min(ratios), .92);
    const rMax   = Math.max(d3.max(ratios), 1.08);
    const pad    = (rMax - rMin) * .08;

    const container = d3.select('#forest').append('div');
    const svg = container.append('svg')
      .attr('viewBox', `0 0 ${W} ${H}`).attr('style', 'width:100%;height:auto')
      .append('g').attr('transform', `translate(${Mg.left},${Mg.top})`);

    svg.append('text').attr('x', w / 2).attr('y', -14).attr('text-anchor', 'middle')
      .attr('fill', col).attr('font-size', 12).attr('font-weight', 600).text(M_LABEL[metric]);

    const x = d3.scaleLinear().domain([rMin - pad, rMax + pad]).range([0, w]).nice();
    const y = d3.scaleBand().domain(data.map(d => d.company)).range([0, h]).padding(.15);

    svg.append('g').attr('class', 'grid').call(d3.axisBottom(x).tickSize(h).tickFormat('').ticks(5));
    svg.append('line').attr('x1', x(1)).attr('x2', x(1)).attr('y1', 0).attr('y2', h)
      .attr('stroke', '#3fb950').attr('stroke-width', 1.5).attr('stroke-dasharray', '4,3').attr('opacity', .7);

    svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${h})`)
      .call(d3.axisBottom(x).ticks(5).tickFormat(d => `${d.toFixed(2)}×`));
    svg.append('g').attr('class', 'axis').call(d3.axisLeft(y));

    data.forEach(d => {
      const cx = x(d.ratio), cy = y(d.company) + y.bandwidth() / 2;
      svg.append('line').attr('x1', x(1)).attr('x2', cx).attr('y1', cy).attr('y2', cy)
        .attr('stroke', d.correct ? '#3fb950' : '#f85149').attr('stroke-width', 1.5).attr('opacity', .6);
      svg.append('circle').attr('cx', cx).attr('cy', cy).attr('r', 5)
        .attr('fill', d.correct ? col : '#f85149').attr('stroke', '#1c2128').attr('stroke-width', 1.5)
        .attr('opacity', .9).style('cursor', 'pointer')
        .on('mouseover', ev => showTip(
          `<b>${d.company} · ${M_LABEL[metric]}</b><br>` +
          `GT: $${(d.ground_truth / 1e9).toFixed(3)}B<br>` +
          `Extracted: $${(d.extracted / 1e9).toFixed(3)}B<br>` +
          `Ratio: ${d.ratio.toFixed(4)}×<br>` +
          `Status: ${d.correct ? '✓ Correct' : '✗ ' + d.error_pct + '% error'}`, ev))
        .on('mousemove', moveTip).on('mouseout', hideTip);
    });

    svg.append('text').attr('x', w / 2).attr('y', h + 40).attr('text-anchor', 'middle')
      .attr('fill', '#8b949e').attr('font-size', 10).text('Extracted ÷ Ground Truth');
  });

  const legDiv = d3.select('#forest').append('div')
    .attr('style', 'grid-column:1/-1;display:flex;gap:22px;font-size:12px;color:#8b949e;padding-top:6px;align-items:center');
  legDiv.append('span').html('<svg width="14" height="14"><circle cx="7" cy="7" r="5" fill="#58a6ff" stroke="#1c2128" stroke-width="1.5"/></svg>&nbsp;Correct extraction');
  legDiv.append('span').html('<svg width="14" height="14"><circle cx="7" cy="7" r="5" fill="#f85149" stroke="#1c2128" stroke-width="1.5"/></svg>&nbsp;Incorrect extraction');
  legDiv.append('span').html('<svg width="28" height="14"><line x1="0" y1="7" x2="28" y2="7" stroke="#3fb950" stroke-width="1.5" stroke-dasharray="4,3"/></svg>&nbsp;Perfect (1.0×)');
}
