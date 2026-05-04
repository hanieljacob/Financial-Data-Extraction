import * as d3 from 'd3';

const tip = d3.select('#tip');

export const showTip = (html, ev) =>
  tip.html(html).style('opacity', 1)
     .style('left', (ev.clientX + 15) + 'px')
     .style('top',  (ev.clientY - 10) + 'px');

export const moveTip = ev =>
  tip.style('left', (ev.clientX + 15) + 'px')
     .style('top',  (ev.clientY - 10) + 'px');

export const hideTip = () => tip.style('opacity', 0);
