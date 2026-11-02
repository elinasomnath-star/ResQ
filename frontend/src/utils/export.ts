/**
 * Export utilities for ResQ Dashboard
 * CSV export for allocation and inventory tables
 * PNG export for map and charts
 */

export function exportToCSV(filename: string, rows: Record<string, any>[], headers?: string[]): void {
  if (!rows || rows.length === 0) return;
  const cols = headers || Object.keys(rows[0]);
  const csvContent = [
    cols.join(','),
    ...rows.map((row) =>
      cols
        .map((col) => {
          const val = row[col] === null || row[col] === undefined ? '' : String(row[col]);
          return `"${val.replace(/"/g, '""')}"`;
        })
        .join(',')
    ),
  ].join('\r\n');

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', filename.endsWith('.csv') ? filename : `${filename}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function triggerDirectDownload(url: string, filename: string): void {
  const link = document.createElement('a');
  link.download = filename.endsWith('.png') ? filename : `${filename}.png`;
  link.href = url;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

export async function exportElementAsPNG(elementId: string, filename: string): Promise<void> {
  const el = document.getElementById(elementId);
  if (!el) {
    console.error(`Export failed: element #${elementId} not found`);
    return;
  }

  // Handle the main MapLibre map canvas
  if (elementId === 'resq-map-container') {
    const mapCanvas = el.querySelector('canvas');
    if (!mapCanvas) {
      console.error('Map export failed: MapLibre canvas is not ready.');
      return;
    }
    try {
      const outCanvas = document.createElement('canvas');
      outCanvas.width = mapCanvas.width;
      outCanvas.height = mapCanvas.height;
      const ctx = outCanvas.getContext('2d');

      if (ctx) {
        // 1. Draw WebGL Map Canvas directly
        ctx.drawImage(mapCanvas, 0, 0);

        // 2. Add high-res ResQ stamp overlay
        ctx.save();
        const stampW = Math.min(390, outCanvas.width * 0.45);
        const stampH = 52;
        const padX = 24;
        const padY = 24;

        // Dark frosted backdrop
        ctx.fillStyle = 'rgba(5, 8, 19, 0.90)';
        ctx.strokeStyle = 'rgba(34, 211, 238, 0.45)';
        ctx.lineWidth = 1.5;

        ctx.beginPath();
        const r = 10;
        ctx.moveTo(padX + r, padY);
        ctx.lineTo(padX + stampW - r, padY);
        ctx.quadraticCurveTo(padX + stampW, padY, padX + stampW, padY + r);
        ctx.lineTo(padX + stampW, padY + stampH - r);
        ctx.quadraticCurveTo(padX + stampW, padY + stampH, padX + stampW - r, padY + stampH);
        ctx.lineTo(padX + r, padY + stampH);
        ctx.quadraticCurveTo(padX, padY + stampH, padX, padY + stampH - r);
        ctx.lineTo(padX, padY + r);
        ctx.quadraticCurveTo(padX, padY, padX + r, padY);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();

        // Brand Title
        ctx.fillStyle = '#22d3ee';
        ctx.font = 'bold 15px "Space Grotesk", sans-serif';
        ctx.fillText('ResQ · Bantwal Taluk Flood Workspace', padX + 14, padY + 23);

        // Meta subtitle
        ctx.fillStyle = '#94a3b8';
        ctx.font = '11px "JetBrains Mono", monospace';
        const cleanName = filename.replace('resq_map_', '').replace(/_/g, ' ');
        ctx.fillText(`Event: ${cleanName} · Sourced Replay · ${new Date().toLocaleDateString('en-IN')}`, padX + 14, padY + 41);
        ctx.restore();

        outCanvas.toBlob((blob) => {
          if (!blob) {
            triggerDirectDownload(outCanvas.toDataURL('image/png'), filename);
            return;
          }
          const blobUrl = URL.createObjectURL(blob);
          triggerDirectDownload(blobUrl, filename);
          setTimeout(() => URL.revokeObjectURL(blobUrl), 2000);
        }, 'image/png');
      } else {
        triggerDirectDownload(mapCanvas.toDataURL('image/png'), filename);
      }
    } catch (error) {
      console.error('Map export failed:', error);
      try {
        triggerDirectDownload(mapCanvas.toDataURL('image/png'), filename);
      } catch (err) {
        console.error('Fallback export error:', err);
      }
    }
    return;
  }

  // If the element is or contains an SVG, serialize it to an image canvas
  const svgEl = el.tagName.toLowerCase() === 'svg' ? (el as unknown as SVGSVGElement) : el.querySelector('svg');

  if (svgEl) {
    const svgData = new XMLSerializer().serializeToString(svgEl);
    const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
    const URL = window.URL || window.webkitURL || window;
    const blobURL = URL.createObjectURL(svgBlob);

    const image = new Image();
    image.onload = () => {
      const rect = svgEl.getBoundingClientRect();
      const canvas = document.createElement('canvas');
      canvas.width = (rect.width || 800) * 2; // high res
      canvas.height = (rect.height || 600) * 2;
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.fillStyle = '#0b0f19'; // dark theme background
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.scale(2, 2);
        ctx.drawImage(image, 0, 0, rect.width || 800, rect.height || 600);

        const pngUrl = canvas.toDataURL('image/png');
        triggerDirectDownload(pngUrl, filename);
      }
      URL.revokeObjectURL(blobURL);
    };
    image.src = blobURL;
    return;
  }

  console.warn(`Element #${elementId} is neither an SVG nor contains a map canvas.`);
}
