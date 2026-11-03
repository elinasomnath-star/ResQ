import React, { useEffect, useState } from 'react';
import { AlertTriangle, ExternalLink, Waves } from 'lucide-react';
import type { GaugeReading } from '../types';
import { api } from '../services/api';
import '../styles/GaugeRewind.css';

interface GaugeRewindProps {
  eventDate: string;
}

const isPeak = (reading: GaugeReading) => reading.is_peak_reading;

export const GaugeRewind: React.FC<GaugeRewindProps> = ({ eventDate }) => {
  const [readings, setReadings] = useState<GaugeReading[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setLoadError(false);
    api.getGaugeReadings(eventDate)
      .then((data) => {
        if (!mounted) return;
        const sorted = data
          .filter((row) => Number.isFinite(row.water_level_m))
          .sort((a, b) => a.reading_timestamp_utc.localeCompare(b.reading_timestamp_utc));
        setReadings(sorted);
        const peakIndex = sorted.findIndex(isPeak);
        setSelectedIndex(peakIndex >= 0 ? peakIndex : Math.max(0, sorted.length - 1));
      })
      .catch(() => {
        if (mounted) {
          setReadings([]);
          setLoadError(true);
        }
      })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [eventDate]);

  if (loading) {
    return (
      <div className="gauge-card gauge-loading">
        <span className="gauge-spin-dot" />
        <span>Loading sourced gauge stage…</span>
      </div>
    );
  }

  if (!readings.length) {
    return (
      <div className="gauge-card gauge-empty" role="status">
        <div className="gauge-heading"><Waves size={15} /><strong>River gauge</strong></div>
        <p>{loadError ? 'Gauge readings could not be loaded.' : `No gauge reading is available for ${eventDate}.`}</p>
      </div>
    );
  }

  const current = readings[selectedIndex] ?? readings[0];
  const danger = current.danger_mark_m ?? 9.0;
  const warning = current.warning_level_m ?? 8.0;
  const level = current.water_level_m;
  const aboveDanger = level >= danger;
  const atWarning = level >= warning;
  const stageLabel = aboveDanger ? 'DANGER LEVEL' : atWarning ? 'WARNING LEVEL' : 'NORMAL';
  const diffFromDanger = level - danger;
  const dateText = current.reading_timestamp_utc
    ? new Date(current.reading_timestamp_utc).toLocaleString('en-IN', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
      })
    : eventDate;

  const maxScale = Math.max(12, level + 0.5, danger + 0.5);
  const fillPct = Math.min(100, Math.max(0, (level / maxScale) * 100));
  const warnPct = (warning / maxScale) * 100;
  const dangerPct = (danger / maxScale) * 100;

  return (
    <section className="gauge-card" aria-label="Sourced Bantwal river gauge stage">
      {/* Header with Title and Glowing Status Badge */}
      <div className="gauge-heading-row">
        <div className="gauge-heading">
          <span className="gauge-icon-wrapper">
            <Waves size={14} />
          </span>
          <strong>Netravati · Bantwal gauge</strong>
        </div>
        <span className={`gauge-status-badge ${aboveDanger ? 'badge-danger' : atWarning ? 'badge-warning' : 'badge-normal'}`}>
          {aboveDanger || atWarning ? <AlertTriangle size={11} className="badge-icon" /> : <span className="badge-dot" />}
          {stageLabel}
        </span>
      </div>

      {/* Main Metric & Comparison */}
      <div className="gauge-metrics-container">
        <div className="gauge-main-stat">
          <div className="gauge-stage-value">
            {level.toFixed(1)}
            <small>m</small>
          </div>
          <div className="gauge-date">
            <span>{dateText}</span>
            {isPeak(current) && <span className="peak-chip">PEAK</span>}
          </div>
        </div>

        <div className="gauge-threshold-box">
          <div className="threshold-row">
            <span className="threshold-label">Warning</span>
            <span className="threshold-val warning-val">{warning.toFixed(1)} m</span>
          </div>
          <div className="threshold-row">
            <span className="threshold-label">Danger</span>
            <span className="threshold-val danger-val">{danger.toFixed(1)} m</span>
          </div>
          <div className={`threshold-diff ${aboveDanger ? 'diff-danger' : atWarning ? 'diff-warning' : 'diff-normal'}`}>
            {aboveDanger
              ? `+${diffFromDanger.toFixed(1)} m above danger`
              : `${Math.abs(diffFromDanger).toFixed(1)} m below danger`}
          </div>
        </div>
      </div>

      {/* Visual Water Level Meter Bar */}
      <div className="gauge-bar-wrapper">
        <div className="gauge-bar-track">
          <div
            className={`gauge-bar-fill ${aboveDanger ? 'fill-danger' : atWarning ? 'fill-warning' : 'fill-normal'}`}
            style={{ width: `${fillPct}%` }}
          />
          <span className="gauge-bar-tick tick-warning" style={{ left: `${warnPct}%` }} title={`Warning: ${warning}m`} />
          <span className="gauge-bar-tick tick-danger" style={{ left: `${dangerPct}%` }} title={`Danger: ${danger}m`} />
        </div>
        <div className="gauge-bar-labels">
          <span>0.0 m</span>
          <span className="label-danger-mark">{danger.toFixed(1)} m Danger</span>
          <span>{maxScale.toFixed(1)} m</span>
        </div>
      </div>

      {/* Timeline Slider if multiple readings */}
      {readings.length > 2 && (
        <div className="gauge-timeline">
          <div className="gauge-timeline-labels">
            <span>{readings[0].reading_timestamp_utc.slice(5, 16)}</span>
            <span>Historical readings</span>
            <span>{readings[readings.length - 1].reading_timestamp_utc.slice(5, 16)}</span>
          </div>
          <input
            aria-label="Select documented gauge reading"
            type="range"
            min={0}
            max={readings.length - 1}
            value={selectedIndex}
            onChange={(event) => setSelectedIndex(Number(event.target.value))}
            className="gauge-slider"
          />
        </div>
      )}

      {/* Source documentation note and link */}
      <div className="gauge-source-row">
        <span className="gauge-source-note" title={current.notes}>
          {current.source_document_title || current.notes || 'Sourced event gauge record'}
        </span>
        {current.source_url && (
          <a href={current.source_url} target="_blank" rel="noreferrer" className="gauge-source-link">
            <span>Source</span>
            <ExternalLink size={10} />
          </a>
        )}
      </div>
    </section>
  );
};

export default GaugeRewind;
