import * as d3 from 'd3';
import { METRICS, M_LABEL, M_COLOR } from './config.js';
import { showTip, moveTip, hideTip } from './tooltip.js';

export function renderAccuracyChart(runs, summary, getSelectedRun, onSelect) {
  const M = { top: 18, right: 170, bottom: 52, left: 52 };
  const W = 900, H = 320;
  const w = W - M.left - M.right, h = H - M.top - M.bottom;

  const svg = d3.select('#acc-chart').append('svg')
    .attr('viewBox', `0 0 ${W} ${H}`).attr('style', 'width:100%;height:auto')
    .append('g').attr('transform', `translate(${M.left},${M.top})`);

  const x = d3.scalePoint().domain(runs).range([0, w]).padding(.35);
  const y = d3.scaleLinear().domain([58, 103]).range([h, 0]);

  svg.append('g').attr('class', 'grid').call(d3.axisLeft(y).tickSize(-w).tickFormat('').ticks(5));

  runs.forEach(run => {
    svg.append('rect')
      .attr('x', x(run) - x.step() * 0.35).attr('y', 0)
      .attr('width', x.step() * 0.7).attr('height', h)
      .attr('fill', 'transparent').style('cursor', 'pointer')
      .on('click', () => onSelect(run));
  });

  function drawHighlight() {
    svg.selectAll('.run-highlight').remove();
    svg.insert('rect', ':first-child')
      .attr('class', 'run-highlight')
      .attr('x', x(getSelectedRun()) - x.step() * 0.35).attr('y', 0)
      .attr('width', x.step() * 0.7).attr('height', h)
      .attr('fill', '#58a6ff').attr('opacity', .07).attr('rx', 4)
      .style('pointer-events', 'none');
  }
  drawHighlight();

  svg.append('line').attr('x1', 0).attr('x2', w).attr('y1', y(100)).attr('y2', y(100))
    .attr('stroke', '#30363d').attr('stroke-dasharray', '5,4').attr('stroke-width', 1);
  svg.append('text').attr('x', w + 6).attr('y', y(100) + 4)
    .attr('fill', '#6e7681').attr('font-size', 10).text('100%');

  svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${h})`)
    .call(d3.axisBottom(x).tickFormat((_, i) => `Cycle ${i + 1}`));
  svg.append('g').attr('class', 'axis').call(d3.axisLeft(y).tickFormat(d => d + '%').ticks(5));

  svg.selectAll('.t-lbl').data(runs).enter().append('text').attr('class', 't-lbl')
    .attr('x', d => x(d)).attr('y', h + 40).attr('text-anchor', 'middle')
    .attr('fill', '#6e7681').attr('font-size', 10).text(d => d.slice(11, 16));

  const lineGen = d3.line().x(d => x(d.run_id)).y(d => y(d.accuracy_pct)).curve(d3.curveMonotoneX);
  const areaGen = d3.area().x(d => x(d.run_id)).y0(h).y1(d => y(d.accuracy_pct)).curve(d3.curveMonotoneX);

  METRICS.forEach(m => {
    const data = summary.filter(d => d.metric === m).sort((a, b) => a.run_id.localeCompare(b.run_id));
    const col  = M_COLOR[m];
    svg.append('path').datum(data).attr('fill', col).attr('opacity', .07).attr('d', areaGen);
    svg.append('path').datum(data).attr('fill', 'none').attr('stroke', col).attr('stroke-width', 2.5).attr('d', lineGen);
    svg.selectAll(null).data(data).enter().append('circle')
      .attr('r', 5).attr('cx', d => x(d.run_id)).attr('cy', d => y(d.accuracy_pct))
      .attr('fill', col).attr('stroke', '#1c2128').attr('stroke-width', 2)
      .style('cursor', 'pointer')
      .on('mouseover', (ev, d) => showTip(
        `<b>${M_LABEL[d.metric]}</b><br>Cycle ${runs.indexOf(d.run_id) + 1} · ${d.run_id.slice(11, 16)}<br>` +
        `Accuracy: <b>${d.accuracy_pct}%</b><br>Correct: ${d.n_correct}/${d.n_total}<br>` +
        `Mean error: ${d.mean_error_pct !== null ? d.mean_error_pct + '%' : '—'}`, ev))
      .on('mousemove', moveTip).on('mouseout', hideTip)
      .on('click', (_, d) => onSelect(d.run_id));
    const last = data[data.length - 1];
    svg.append('text').attr('x', x(last.run_id) + 12).attr('y', y(last.accuracy_pct) + 4)
      .attr('fill', col).attr('font-size', 11).attr('font-weight', 600).text(last.accuracy_pct + '%');
  });

  const leg = d3.select('#acc-leg');
  METRICS.forEach(m => leg.append('span').attr('class', 'leg-item')
    .html(`<span class="leg-line" style="background:${M_COLOR[m]}"></span>${M_LABEL[m]}`));

  return drawHighlight;
}
