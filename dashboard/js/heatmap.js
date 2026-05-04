import * as d3 from 'd3';
import { METRICS, M_LABEL, M_COLOR } from './config.js';
import { showTip, moveTip, hideTip } from './tooltip.js';

export function renderHeatmap(results, selectedRun) {
  d3.select('#heatmap').html('');
  const companies = [...new Set(results.map(d => d.company))].sort();
  const ld  = results.filter(d => d.run_id === selectedRun);
  const lkp = {};
  ld.forEach(d => { lkp[d.company + '-' + d.metric] = d; });

  const cW = 178, cH = 25, lblW = 58, hdrH = 42;
  const W  = lblW + 12 + METRICS.length * cW + 20;
  const H  = hdrH + companies.length * cH + 26;
  const ox = lblW + 12;

  const svg = d3.select('#heatmap').append('svg')
    .attr('viewBox', `0 0 ${W} ${H}`).attr('style', 'width:100%;height:auto');

  METRICS.forEach((m, i) => {
    svg.append('text').attr('x', ox + i * cW + cW / 2).attr('y', 16)
      .attr('text-anchor', 'middle').attr('fill', M_COLOR[m])
      .attr('font-size', 12).attr('font-weight', 600).text(M_LABEL[m]);
  });

  companies.forEach((co, j) => {
    const ry = hdrH + j * cH;
    if (j % 2 === 0) svg.append('rect').attr('x', ox).attr('y', ry)
      .attr('width', METRICS.length * cW).attr('height', cH).attr('fill', '#fff').attr('opacity', .025);
    svg.append('text').attr('x', ox - 6).attr('y', ry + cH / 2 + 4)
      .attr('text-anchor', 'end').attr('fill', '#e6edf3').attr('font-size', 12).text(co);

    METRICS.forEach((m, i) => {
      const d  = lkp[co + '-' + m];
      const cx = ox + i * cW, cy = ry;
      let fill, label, lf = '#fff';
      if (!d || d.extracted === null || d.extracted === undefined) {
        fill = '#30363d'; label = 'null'; lf = '#8b949e';
      } else if (d.correct) {
        fill = '#1a4731'; label = '✓'; lf = '#3fb950';
      } else {
        const e = d.error_pct;
        if (e === null)   { fill = '#7f1d1d'; label = '✗'; }
        else if (e < 1)   { fill = '#713f12'; label = e + '%'; lf = '#fde68a'; }
        else if (e < 5)   { fill = '#92400e'; label = e + '%'; lf = '#fcd34d'; }
        else if (e < 20)  { fill = '#991b1b'; label = e + '%'; lf = '#fca5a5'; }
        else              { fill = '#7f1d1d'; label = e + '%'; lf = '#fca5a5'; }
      }
      svg.append('rect').attr('x', cx + 2).attr('y', cy + 2)
        .attr('width', cW - 4).attr('height', cH - 4).attr('rx', 4)
        .attr('fill', fill).attr('opacity', .92).style('cursor', 'pointer')
        .on('mouseover', ev => {
          if (!d) { showTip(`<b>${co} · ${M_LABEL[m]}</b><br>No data`, ev); return; }
          const gt = d.ground_truth !== null ? '$' + (d.ground_truth / 1e9).toFixed(3) + 'B' : '—';
          const ex = d.extracted   !== null ? '$' + (d.extracted   / 1e9).toFixed(3) + 'B' : 'null';
          showTip(`<b>${co} · ${M_LABEL[m]}</b><br>Ground truth: ${gt}<br>Extracted:&nbsp; ${ex}<br>Status: ${d.correct ? '✓ Correct' : '✗ ' + d.error_pct + '% error'}`, ev);
        }).on('mousemove', moveTip).on('mouseout', hideTip);
      svg.append('text').attr('x', cx + cW / 2).attr('y', cy + cH / 2 + 4)
        .attr('text-anchor', 'middle').attr('fill', lf).attr('font-size', 11).text(label);
    });
  });

  const ly = H - 10;
  [
    ['#1a4731', '#3fb950', 'Correct'],
    ['#713f12', '#fde68a', '<1% error'],
    ['#92400e', '#fcd34d', '1–5% error'],
    ['#991b1b', '#fca5a5', '5–20% error'],
    ['#7f1d1d', '#fca5a5', '>20% error'],
    ['#30363d', '#8b949e', 'Null / missing'],
  ].reduce((lx, [bg, fc, lbl]) => {
    svg.append('rect').attr('x', lx).attr('y', ly - 11).attr('width', 13).attr('height', 13).attr('rx', 3).attr('fill', bg);
    svg.append('text').attr('x', lx + 17).attr('y', ly).attr('fill', fc).attr('font-size', 11).text(lbl);
    return lx + 107;
  }, ox);
}
