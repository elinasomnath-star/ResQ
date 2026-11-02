import React, { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
import 'maplibre-gl/dist/maplibre-gl.css';
import {
  Layers,
  Eye,
  Sliders,
  Box,
  Radio,
  Flame,
  Shield,
  Truck,
  Rotate3d,
  Maximize2,
  Minimize2,
  AlertTriangle,
  Plus,
  Minus,
} from 'lucide-react';
import { ZoneData, RouteFeature, EngineType, AllocationRow } from '../types';
import Dock, { DockItem } from './reactbits/Dock';

function closureMarkerCollection(collection: any, closureId: string | null) {
  const feature = collection?.features?.find((item: any) => item.properties?.closure_id === closureId);
  if (!feature?.geometry) return { type: 'FeatureCollection', features: [] } as const;
  const parts: number[][][] = feature.geometry.type === 'LineString'
    ? [feature.geometry.coordinates]
    : feature.geometry.type === 'MultiLineString' ? feature.geometry.coordinates : [];
  const configuredPoint = feature.properties?.closure_point;
  if (Array.isArray(configuredPoint) && configuredPoint.length >= 2) {
    return {
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        properties: { closure_id: closureId },
        geometry: { type: 'Point', coordinates: configuredPoint },
      }],
    } as const;
  }
  const longest = parts.reduce((best, part) => part.length > best.length ? part : best, [] as number[][]);
  if (!longest.length) return { type: 'FeatureCollection', features: [] } as const;
  const midpoint = longest[Math.floor((longest.length - 1) / 2)];
  return {
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      properties: { closure_id: closureId },
      geometry: { type: 'Point', coordinates: midpoint },
    }],
  } as const;
}

// Resolve the worker through Vite so the built/Docker frontend serves it as a
// same-origin asset instead of relying on a runtime blob import.
maplibregl.setWorkerUrl(maplibreWorkerUrl);

const MINI_TOWN_HALL_SCENARIO_ID = 'bantwal_netravati_bridge';
const MINI_TOWN_HALL_NAME = 'Mini Town Hall';
const MINI_TOWN_HALL_COORDINATES: [number, number] = [74.83935, 12.86431];

function fitReliefSiteBounds(
  map: maplibregl.Map,
  bounds: [number, number, number, number],
  includeMiniTownHall: boolean,
  duration: number,
) {
  const [west, south, east, north] = bounds;
  const viewportHeight = map.getContainer().clientHeight;
  const overlayReserve = Math.min(320, Math.max(250, viewportHeight * 0.35));
  const fittedBounds: [[number, number], [number, number]] = [
    [includeMiniTownHall ? Math.min(west, MINI_TOWN_HALL_COORDINATES[0]) : west, south],
    [east, north],
  ];
  map.fitBounds(fittedBounds, {
    padding: { top: 72, right: 350, bottom: overlayReserve, left: 340 },
    duration,
    maxZoom: 11,
  });
}

interface MapConsoleProps {
  selectedEvent: string;
  zones: ZoneData[];
  onSelectZone: (zone: ZoneData | null) => void;
  selectedZoneId: string | null;
  selectedEngine: EngineType;
  isClosureActive: boolean;
  appliedClosureId?: string | null;
  closureRouteChangeCount?: number | null;
  closureDetourInfo?: { beforeDistanceKm: number; afterDistanceKm: number } | null;
  allocations?: AllocationRow[];
  routes?: RouteFeature[];
  coveragePreview?: number[] | null;
  coveragePreviewStockPct?: number;
}

export const MapConsole: React.FC<MapConsoleProps> = ({
  selectedEvent,
  zones,
  onSelectZone,
  selectedZoneId,
  selectedEngine,
  isClosureActive,
  appliedClosureId = null,
  closureRouteChangeCount = null,
  closureDetourInfo,
  allocations = [],
  routes = [],
  coveragePreview = null,
  coveragePreviewStockPct,
}) => {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const facilityLabelMarkersRef = useRef<maplibregl.Marker[]>([]);
  const miniTownHallMarkerRef = useRef<maplibregl.Marker | null>(null);
  const mapBoundsRef = useRef<[number, number, number, number] | null>(null);
  const zonesRef = useRef(zones);
  const routesRef = useRef(routes);
  const appliedClosureIdRef = useRef(appliedClosureId);
  zonesRef.current = zones;
  routesRef.current = routes;
  appliedClosureIdRef.current = appliedClosureId;

  // Layer Visibility States
  const [showZones, setShowZones] = useState(true);
  const [showSar, setShowSar] = useState(true);
  const [sarOpacity, setSarOpacity] = useState(0.65);
  const [showRiver, setShowRiver] = useState(true);
  const [showRoads, setShowRoads] = useState(true);
  const [showFacilities, setShowFacilities] = useState(true);
  const [showClosures, setShowClosures] = useState(true);
  const [showRoutes, setShowRoutes] = useState(true);
  const [is3DMode, setIs3DMode] = useState(false);
  const [showOpacitySlider, setShowOpacitySlider] = useState(false);

  // Initialize Map
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    // Local study canvas: only the Bantwal-specific cached layers are shown.
    const darkStyle: maplibregl.StyleSpecification = {
      version: 8,
      sources: {},
      layers: [
        {
          id: 'base_dark_background',
          type: 'background',
          paint: {
            'background-color': '#080D1A',
          },
        },
      ],
    };

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: darkStyle,
      center: [75.06, 12.85],
      zoom: 10,
      pitch: 0,
      bearing: 0,
      attributionControl: { compact: true },
      canvasContextAttributes: { preserveDrawingBuffer: true },
    });

    map.on('load', async () => {
      // 1. Load River GeoJSON
      try {
        const riverRes = await fetch('/data/bantwal_river.geojson');
        const riverData = await riverRes.json();
        map.addSource('river_source', { type: 'geojson', data: riverData, attribution: '&copy; OpenStreetMap contributors' });
        map.addLayer({
          id: 'river_layer',
          type: 'line',
          source: 'river_source',
          paint: {
            'line-color': '#59D3C4',
            'line-width': 3.3,
            'line-opacity': 0.96,
          },
        });
      } catch (err) {
        console.warn('River layer load error:', err);
      }

      // 2. Load Simplified Roads GeoJSON
      try {
        const roadsRes = await fetch('/data/bantwal_roads.geojson');
        const roadsData = await roadsRes.json();
        map.addSource('roads_source', { type: 'geojson', data: roadsData, attribution: '&copy; OpenStreetMap contributors' });
        map.addLayer({
          id: 'roads_layer',
          type: 'line',
          source: 'roads_source',
          paint: {
            'line-color': ['match', ['get', 'highway'], ['motorway', 'trunk', 'primary', 'motorway_link', 'trunk_link', 'primary_link'], '#F4C36A', '#B8C9DF'],
            'line-width': ['interpolate', ['linear'], ['zoom'], 8, 0.75, 12, 1.45, 14, 2.1],
            'line-opacity': 0.88,
          },
        });
      } catch (err) {
        console.warn('Roads layer load error:', err);
      }

      // 3. Load Analysis Zones GeoJSON
      try {
        const zonesRes = await fetch('/data/analysis_zones.geojson');
        const zonesGeo = await zonesRes.json();

        // Merge event severity into properties
        const severityMap = new Map(zonesRef.current.map((z) => [z.zone_id, z.severity_score]));
        zonesGeo.features.forEach((f: any) => {
          const score = severityMap.get(f.properties.zone_id) ?? 0.5;
          f.properties.severity_score = score;
          // Ramp on map: teal #2DD4BF (<0.35), yellow #FDE047 (0.35-0.65), coral #FB7185 (>0.65)
          f.properties.severity_color =
            score > 0.65 ? '#FB7185' : score > 0.35 ? '#FDE047' : '#2DD4BF';
          f.properties.zone_number = f.properties.zone_id.replace('bantwal_grid_', '');
        });

        map.addSource('zones_source', { type: 'geojson', data: zonesGeo });
        const bounds = await fetch('/data/bantwal_map_bounds.json').then((r) => r.json());
        if (Array.isArray(bounds) && bounds.length === 4) {
          mapBoundsRef.current = bounds as [number, number, number, number];
          fitReliefSiteBounds(map, mapBoundsRef.current, false, 0);
        }

        // Flat fill layer
        map.addLayer({
          id: 'zones_fill',
          type: 'fill',
          source: 'zones_source',
          paint: {
            'fill-color': ['get', 'severity_color'],
            'fill-opacity': 0.35,
          },
        });

        // 3D Extrusion layer (initially hidden or pitch 0)
        map.addLayer({
          id: 'zones_extrusion',
          type: 'fill-extrusion',
          source: 'zones_source',
          layout: { visibility: 'none' },
          paint: {
            'fill-extrusion-color': ['get', 'severity_color'],
            'fill-extrusion-height': ['*', ['get', 'severity_score'], 2800],
            'fill-extrusion-base': 0,
            'fill-extrusion-opacity': 0.75,
          },
        });

        // Zone line outline
        map.addLayer({
          id: 'zones_line',
          type: 'line',
          source: 'zones_source',
          paint: {
            'line-color': '#64748B',
            'line-width': 1.8,
            'line-opacity': 0.65,
          },
        });

        // Selected zone glowing highlight ring
        map.addLayer({
          id: 'zones_selected',
          type: 'line',
          source: 'zones_source',
          filter: ['==', 'zone_id', selectedZoneId || ''],
          paint: {
            'line-color': '#22D3EE',
            'line-width': 3.5,
            'line-opacity': 1.0,
          },
        });

        // Hover & click listeners for zones
        map.on('click', 'zones_fill', (e: any) => {
          if (!e.features || !e.features[0]) return;
          const zid = e.features[0].properties.zone_id;
          const match = zones.find((z) => z.zone_id === zid) || null;
          onSelectZone(match);
        });

        map.on('mouseenter', 'zones_fill', () => {
          map.getCanvas().style.cursor = 'pointer';
        });
        map.on('mouseleave', 'zones_fill', () => {
          map.getCanvas().style.cursor = '';
        });
      } catch (err) {
        console.warn('Zones layer load error:', err);
      }

      // 4. Bantwal-clipped candidate SAR change signal
      try {
        const sarBounds = await fetch('/data/bantwal_sar_bounds.json').then((r) => r.json());
        map.addSource('sar_overlay_source', {
          type: 'image',
          url: `/data/sar_bantwal_${selectedEvent}.png`,
          coordinates: sarBounds[selectedEvent],
        });

        map.addLayer(
          {
            id: 'sar_overlay_layer',
            type: 'raster',
            source: 'sar_overlay_source',
            paint: {
              'raster-opacity': sarOpacity,
            },
          },
          'zones_line'
        );
      } catch (err) {
        console.warn('SAR overlay error:', err);
      }

      // 5. Relief Facilities (warehouses.geojson)
      try {
        const facRes = await fetch('/data/bantwal_facilities.geojson');
        const facData = await facRes.json();
        // Filter out null geometries
        facData.features = facData.features.filter((f: any) => f.geometry && f.geometry.type === 'Point');
        map.addSource('facilities_source', { type: 'geojson', data: facData });

        map.addLayer({
          id: 'facilities_layer',
          type: 'circle',
          source: 'facilities_source',
          paint: {
            'circle-color': '#F59E0B',
            'circle-radius': 6,
            'circle-stroke-width': 2,
            'circle-stroke-color': '#FFFFFF',
            'circle-opacity': 0.9,
          },
        });

        // Facility coordinates are close together in Bantwal. Give each name a
        // stable outward offset so both remain readable at the same zoom level.
        // DOM markers keep these labels separate from the zone-number markers.
        for (const feature of facData.features) {
          const [longitude, latitude] = feature.geometry.coordinates as [number, number];
          const name = String(feature.properties?.name ?? 'Relief facility');
          const facilityId = String(feature.properties?.warehouse_id ?? '');
          const isSvs = facilityId.includes('svs_');
          const root = document.createElement('div');
          Object.assign(root.style, {
            position: 'relative',
            width: '0',
            height: '0',
            pointerEvents: 'none',
            zIndex: '4',
          });
          const label = document.createElement('div');
          label.setAttribute('aria-label', name);
          label.dataset.testid = 'facility-map-label';
          Object.assign(label.style, {
            position: 'absolute',
            top: isSvs ? '-29px' : '10px',
            left: isSvs ? '14px' : 'auto',
            right: isSvs ? 'auto' : '14px',
            width: 'max-content',
            maxWidth: '220px',
            boxSizing: 'border-box',
            display: 'flex',
            flexDirection: isSvs ? 'row' : 'row-reverse',
            alignItems: 'center',
            gap: '7px',
            padding: '6px 9px',
            border: '1px solid rgba(157, 169, 224, .48)',
            borderRadius: '8px',
            background: 'rgba(26, 32, 52, .88)',
            backdropFilter: 'blur(9px)',
            boxShadow: '0 4px 14px rgba(6, 10, 25, .32)',
            color: '#EEF1FF',
            font: '550 12px/1.35 Inter, Arial, sans-serif',
            letterSpacing: '.01em',
            textAlign: isSvs ? 'left' : 'right',
            overflowWrap: 'anywhere',
          });
          const accent = document.createElement('span');
          Object.assign(accent.style, {
            flex: '0 0 7px',
            width: '7px',
            height: '7px',
            borderRadius: '50%',
            background: '#A5B4FC',
            boxShadow: '0 0 7px rgba(165, 180, 252, .65)',
          });
          const title = document.createElement('span');
          title.textContent = name;
          label.append(accent, title);
          root.appendChild(label);
          facilityLabelMarkersRef.current.push(
            new maplibregl.Marker({ element: root, anchor: 'center' })
              .setLngLat([longitude, latitude])
              .addTo(map),
          );
        }

        const miniTownHallRoot = document.createElement('div');
        Object.assign(miniTownHallRoot.style, {
          position: 'relative',
          width: '0',
          height: '0',
          pointerEvents: 'none',
          zIndex: '5',
          display: appliedClosureIdRef.current === MINI_TOWN_HALL_SCENARIO_ID ? '' : 'none',
        });
        const miniTownHallLabel = document.createElement('div');
        miniTownHallLabel.dataset.testid = 'mini-town-hall-map-label';
        miniTownHallLabel.setAttribute('aria-label', MINI_TOWN_HALL_NAME);
        Object.assign(miniTownHallLabel.style, {
          position: 'absolute',
          bottom: '18px',
          left: '14px',
          width: 'max-content',
          maxWidth: '170px',
          boxSizing: 'border-box',
          display: 'flex',
          alignItems: 'center',
          gap: '7px',
          padding: '6px 9px',
          border: '1px solid rgba(157, 169, 224, .48)',
          borderRadius: '8px',
          background: 'rgba(26, 32, 52, .88)',
          backdropFilter: 'blur(9px)',
          boxShadow: '0 4px 14px rgba(6, 10, 25, .32)',
          color: '#EEF1FF',
          font: '550 12px/1.35 Inter, Arial, sans-serif',
          letterSpacing: '.01em',
          textAlign: 'left',
          overflowWrap: 'anywhere',
        });
        const miniTownHallDot = document.createElement('span');
        Object.assign(miniTownHallDot.style, {
          flex: '0 0 7px',
          width: '7px',
          height: '7px',
          borderRadius: '50%',
          background: '#A5B4FC',
          boxShadow: '0 0 7px rgba(165, 180, 252, .65)',
        });
        const miniTownHallCircle = document.createElement('span');
        Object.assign(miniTownHallCircle.style, {
          position: 'absolute',
          top: '-6px',
          left: '-6px',
          width: '12px',
          height: '12px',
          boxSizing: 'border-box',
          borderRadius: '50%',
          border: '2px solid #FFFFFF',
          background: '#F59E0B',
          boxShadow: '0 0 8px rgba(245, 158, 11, .7)',
        });
        const miniTownHallTitle = document.createElement('span');
        miniTownHallTitle.textContent = MINI_TOWN_HALL_NAME;
        miniTownHallLabel.append(miniTownHallDot, miniTownHallTitle);
        miniTownHallRoot.appendChild(miniTownHallLabel);
        miniTownHallRoot.appendChild(miniTownHallCircle);
        miniTownHallMarkerRef.current = new maplibregl.Marker({ element: miniTownHallRoot, anchor: 'center' })
          .setLngLat(MINI_TOWN_HALL_COORDINATES)
          .addTo(map);
        if (appliedClosureIdRef.current === MINI_TOWN_HALL_SCENARIO_ID && mapBoundsRef.current) {
          fitReliefSiteBounds(map, mapBoundsRef.current, true, 0);
        }
      } catch (err) {
        console.warn('Facilities load error:', err);
      }

      // 6. Closures GeoJSON
      try {
        const closRes = await fetch('/data/bantwal_scenario_closures.geojson');
        const closData = await closRes.json();
        map.addSource('closures_source', { type: 'geojson', data: closData });
        map.addSource('closure_marker_source', {
          type: 'geojson', data: closureMarkerCollection(closData, null),
        });

        map.addLayer({
          id: 'closures_casing_layer',
          type: 'line',
          source: 'closures_source',
          layout: { visibility: 'none', 'line-cap': 'round', 'line-join': 'round' },
          paint: {
            'line-color': '#280A17',
            'line-width': ['interpolate', ['linear'], ['zoom'], 8, 7, 12, 11, 15, 15],
            'line-opacity': 0.96,
          },
        });
        map.addLayer({
          id: 'closures_layer',
          type: 'line',
          source: 'closures_source',
          layout: { visibility: 'none', 'line-cap': 'round', 'line-join': 'round' },
          paint: {
            'line-color': '#FF263F',
            'line-width': ['interpolate', ['linear'], ['zoom'], 8, 4.5, 12, 7, 15, 10],
            'line-opacity': 1,
          },
        });
        map.addLayer({
          id: 'closure_marker_layer',
          type: 'circle',
          source: 'closure_marker_source',
          layout: { visibility: 'none' },
          paint: {
            'circle-radius': 7,
            'circle-color': '#FF263F',
            'circle-stroke-color': '#FFF1F4',
            'circle-stroke-width': 2,
            'circle-opacity': 1,
          },
        });
        map.addLayer({
          id: 'closure_marker_label_layer',
          type: 'symbol',
          source: 'closure_marker_source',
          layout: {
            visibility: 'none',
            'text-field': 'ROAD CLOSED',
            'text-font': ['Open Sans Bold', 'Arial Unicode MS Bold'],
            'text-size': 10,
            'text-offset': [0, 1.8],
            'text-anchor': 'top',
            'text-allow-overlap': true,
          },
          paint: {
            'text-color': '#FFD8E0',
            'text-halo-color': '#280A17',
            'text-halo-width': 2,
          },
        });
      } catch (err) {
        console.warn('Closures load error:', err);
      }

      // 7. Routes GeoJSON
      try {
        const routeRes = await fetch(`/data/bantwal_routes_${selectedEvent}.geojson`);
        const routeData = await routeRes.json();
        map.addSource('routes_source', {
          type: 'geojson',
          data: routesRef.current.length || isClosureActive
            ? { type: 'FeatureCollection', features: routesRef.current }
            : routeData,
        });

        // A dark casing keeps the selected path distinct from the OSM road layer.
        map.addLayer({
          id: 'routes_halo_layer',
          type: 'line',
          source: 'routes_source',
          filter: ['==', ['get', 'zone_id'], ''],
          paint: { 'line-color': '#07110F', 'line-width': 8, 'line-opacity': 0.95 },
        });
        map.addLayer({
          id: 'routes_road_layer',
          type: 'line',
          source: 'routes_source',
          filter: ['all', ['==', ['get', 'delivery_mode'], 'road'], ['==', ['get', 'zone_id'], '']],
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: {
            'line-color': '#FFD071',
            'line-width': 4.2,
            'line-opacity': 1,
          },
        });

        // Secondary unverified routes (violet #A78BFA, dotted)
        map.addLayer({
          id: 'routes_secondary_layer',
          type: 'line',
          source: 'routes_source',
          filter: ['all', ['==', ['get', 'delivery_mode'], 'secondary'], ['==', ['get', 'zone_id'], '']],
          paint: {
            'line-color': '#C1A7FF',
            'line-width': 4.2,
            'line-dasharray': [2, 2],
            'line-opacity': 0.9,
          },
        });
      } catch (err) {
        console.warn('Routes load error:', err);
      }

      // Draw cached roads above the translucent zone/SAR layers, while keeping
      // relief facilities, closure lines and selected routes visually on top.
      if (map.getLayer('roads_layer') && map.getLayer('facilities_layer')) {
        map.moveLayer('roads_layer', 'facilities_layer');
      }
      // Closures are the most important route-state overlay. Keep the blocked
      // segment above the route redraw so it remains visibly distinct.
      if (map.getLayer('closures_casing_layer')) map.moveLayer('closures_casing_layer');
      if (map.getLayer('closures_layer')) map.moveLayer('closures_layer');
      if (map.getLayer('closure_marker_layer')) map.moveLayer('closure_marker_layer');
      if (map.getLayer('closure_marker_label_layer')) map.moveLayer('closure_marker_label_layer');
    });

    mapRef.current = map;
    (window as any).__resq_map = map;
    

    return () => {
      facilityLabelMarkersRef.current.forEach((marker) => marker.remove());
      facilityLabelMarkersRef.current = [];
      miniTownHallMarkerRef.current?.remove();
      miniTownHallMarkerRef.current = null;
      map.remove();
      mapRef.current = null;
      (window as any).__resq_map = null;
    };
  }, []);


  // Update SAR image source when event changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const updateEventLayers = async () => {
      const sarBounds = await fetch('/data/bantwal_sar_bounds.json').then((r) => r.json());
      const source = map.getSource('sar_overlay_source') as maplibregl.ImageSource;
      if (source && (source as any).updateImage && sarBounds[selectedEvent]) {
        (source as any).updateImage({
          url: `/data/sar_bantwal_${selectedEvent}.png`,
          coordinates: sarBounds[selectedEvent],
        });
      }
      const staticRoutes = await fetch(`/data/bantwal_routes_${selectedEvent}.geojson`).then((r) => r.json());
      const routeSource = map.getSource('routes_source') as maplibregl.GeoJSONSource;
      if (routeSource) {
        routeSource.setData(routesRef.current.length || isClosureActive
          ? { type: 'FeatureCollection', features: routesRef.current }
          : staticRoutes);
      }
    };
    if (map.isStyleLoaded()) void updateEventLayers().catch(() => {});
    else map.once('load', () => { void updateEventLayers().catch(() => {}); });
  }, [selectedEvent, isClosureActive]);

  // Keep the map focused on the specific closure that the API actually applied.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const updateActiveClosure = async () => {
      const collection = await fetch('/data/bantwal_scenario_closures.geojson').then((r) => {
        if (!r.ok) throw new Error(`Closure map data unavailable (${r.status})`);
        return r.json();
      });
      const markerSource = map.getSource('closure_marker_source') as maplibregl.GeoJSONSource | undefined;
      markerSource?.setData(closureMarkerCollection(collection, isClosureActive ? appliedClosureId : null) as any);
    };
    const applyFilters = () => {
      for (const layer of ['closures_layer', 'closures_casing_layer', 'closure_marker_layer', 'closure_marker_label_layer']) {
        if (!map.getLayer(layer)) continue;
        map.setFilter(layer, appliedClosureId
          ? ['==', ['get', 'closure_id'], appliedClosureId]
          : ['==', ['get', 'closure_id'], '__no_active_closure__']);
        map.setLayoutProperty(layer, 'visibility', showClosures && isClosureActive ? 'visible' : 'none');
      }
      void updateActiveClosure().catch((err) => console.warn('Active closure map update failed:', err));
    };
    if (map.isStyleLoaded()) applyFilters();
    else map.once('load', applyFilters);
  }, [selectedEvent, appliedClosureId, isClosureActive, showClosures]);

  // Show the Mangaluru relief centre only for scenario 1 and include its real
  // location in the map view without changing the Bantwal facility labels.
  useEffect(() => {
    const map = mapRef.current;
    const marker = miniTownHallMarkerRef.current;
    if (!map || !marker) return;
    const showMiniTownHall = showFacilities && isClosureActive
      && appliedClosureId === MINI_TOWN_HALL_SCENARIO_ID;
    marker.getElement().style.display = showMiniTownHall ? '' : 'none';
    if (mapBoundsRef.current) {
      fitReliefSiteBounds(map, mapBoundsRef.current, showMiniTownHall, 600);
    }
  }, [appliedClosureId, isClosureActive, showFacilities]);

  // Keep the map source in sync even when a scenario request clears routes.
  // Otherwise the static cached route can remain visible while a new closure
  // is being recalculated or if the request fails.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getSource('routes_source')) return;
    (map.getSource('routes_source') as maplibregl.GeoJSONSource).setData({ type: 'FeatureCollection', features: routes });
  }, [routes, isClosureActive]);

  // Show one path at a time: select a grid cell to inspect its facility-to-zone route.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    const filter = selectedZoneId || '';
    for (const layer of ['routes_halo_layer', 'routes_road_layer', 'routes_secondary_layer']) {
      if (!map.getLayer(layer)) continue;
      if (layer === 'routes_halo_layer') {
        map.setFilter(layer, ['all', ['==', ['get', 'delivery_mode'], 'road'], ['==', ['get', 'zone_id'], filter]]);
      } else {
        map.setFilter(layer, ['all', ['==', ['get', 'delivery_mode'], layer === 'routes_road_layer' ? 'road' : 'secondary'], ['==', ['get', 'zone_id'], filter]]);
      }
    }
  }, [selectedZoneId, routes]);

  // Dynamic Zone Data & Severity Re-Sync
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded() || !map.getSource('zones_source') || zones.length === 0) return;
    fetch('/data/analysis_zones.geojson')
      .then((r) => r.json())
      .then((zonesGeo) => {
        const severityMap = new Map(zones.map((z) => [z.zone_id, z.severity_score]));
        zonesGeo.features.forEach((f: any) => {
          const score = severityMap.get(f.properties.zone_id) ?? 0.5;
          f.properties.severity_score = score;
          f.properties.severity_color =
            score > 0.65 ? '#FB7185' : score > 0.35 ? '#FDE047' : '#2DD4BF';
          f.properties.zone_number = f.properties.zone_id.replace('bantwal_grid_', '');
        });
        (map.getSource('zones_source') as maplibregl.GeoJSONSource).setData(zonesGeo);
      })
      .catch(() => {});
  }, [zones]);

  // Selected Zone highlight filter update
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded() || !map.getLayer('zones_selected')) return;
    map.setFilter('zones_selected', ['==', 'zone_id', selectedZoneId || '']);
  }, [selectedZoneId]);

  // Update layer visibility based on toggles
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    if (map.getLayer('zones_fill')) {
      map.setLayoutProperty('zones_fill', 'visibility', showZones && !is3DMode ? 'visible' : 'none');
      map.setLayoutProperty('zones_line', 'visibility', showZones ? 'visible' : 'none');
      map.setLayoutProperty('zones_extrusion', 'visibility', showZones && is3DMode ? 'visible' : 'none');
    }

    if (map.getLayer('sar_overlay_layer')) {
      map.setLayoutProperty('sar_overlay_layer', 'visibility', showSar ? 'visible' : 'none');
      map.setPaintProperty('sar_overlay_layer', 'raster-opacity', sarOpacity);
    }

    if (map.getLayer('river_layer')) {
      map.setLayoutProperty('river_layer', 'visibility', showRiver ? 'visible' : 'none');
    }

    if (map.getLayer('roads_layer')) {
      map.setLayoutProperty('roads_layer', 'visibility', showRoads ? 'visible' : 'none');
    }

    if (map.getLayer('facilities_layer')) {
      map.setLayoutProperty('facilities_layer', 'visibility', showFacilities ? 'visible' : 'none');
      facilityLabelMarkersRef.current.forEach((marker) => {
        const element = marker.getElement();
        element.style.display = showFacilities ? '' : 'none';
      });
    }
    const showMiniTownHall = showFacilities && isClosureActive
      && appliedClosureId === MINI_TOWN_HALL_SCENARIO_ID;
    if (miniTownHallMarkerRef.current) {
      miniTownHallMarkerRef.current.getElement().style.display = showMiniTownHall ? '' : 'none';
    }

    if (map.getLayer('closures_layer')) {
      map.setLayoutProperty('closures_layer', 'visibility', showClosures && isClosureActive ? 'visible' : 'none');
      map.setFilter('closures_layer', appliedClosureId
        ? ['==', ['get', 'closure_id'], appliedClosureId]
        : ['==', ['get', 'closure_id'], '__no_active_closure__']);
    }
    if (map.getLayer('closures_casing_layer')) {
      map.setLayoutProperty('closures_casing_layer', 'visibility', showClosures && isClosureActive ? 'visible' : 'none');
      map.setFilter('closures_casing_layer', appliedClosureId
        ? ['==', ['get', 'closure_id'], appliedClosureId]
        : ['==', ['get', 'closure_id'], '__no_active_closure__']);
    }
    for (const layer of ['closure_marker_layer', 'closure_marker_label_layer']) {
      if (map.getLayer(layer)) map.setLayoutProperty(layer, 'visibility', showClosures && isClosureActive ? 'visible' : 'none');
    }

    if (map.getLayer('routes_road_layer')) {
      map.setLayoutProperty('routes_road_layer', 'visibility', showRoutes ? 'visible' : 'none');
      map.setLayoutProperty('routes_secondary_layer', 'visibility', showRoutes ? 'visible' : 'none');
    }
  }, [
    showZones,
    showSar,
    sarOpacity,
    showRiver,
    showRoads,
    showFacilities,
    appliedClosureId,
    isClosureActive,
    showClosures,
    isClosureActive,
    appliedClosureId,
    showRoutes,
    is3DMode,
  ]);

  // 3D Tilt handler
  const handleToggle3D = () => {
    const map = mapRef.current;
    if (!map) return;
    const next3D = !is3DMode;
    setIs3DMode(next3D);

    if (next3D) {
      map.easeTo({ pitch: 55, bearing: -15, duration: 1000 });
    } else {
      map.easeTo({ pitch: 0, bearing: 0, duration: 1000 });
    }
  };

  // Render / Update Zone Stress Pulse Markers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    // Remove previous markers
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    if (!showZones || is3DMode) return;

    zones.forEach((zone) => {
      if (!zone.centroid_lat || !zone.centroid_lon) return;

      // A selected stock-sweep row overrides allocation coverage for the visual
      // what-if. Otherwise show the current allocation run only.
      const zoneIndex = Number.isFinite(Number(zone.grid_row)) && Number.isFinite(Number(zone.grid_column))
        ? (Number(zone.grid_row) - 1) * 4 + Number(zone.grid_column) - 1
        : zones.indexOf(zone);
      const zoneAlloc = allocations.filter((a) => a.zone_id === zone.zone_id);
      let coveragePct: number | null = coveragePreview && Number.isFinite(coveragePreview[zoneIndex])
        ? Number(coveragePreview[zoneIndex])
        : null;
      if (coveragePct == null && zoneAlloc.length > 0) {
        const totalNeed = zoneAlloc.reduce((s, a) => s + (a.estimated_need || 0), 0);
        const totalAlloc = zoneAlloc.reduce((s, a) => s + (a.allocated || 0), 0);
        coveragePct = totalNeed > 0 ? (totalAlloc / totalNeed) * 100 : null;
      }

      // Marker element
      const el = document.createElement('div');
      el.className = 'resq-zone-marker cursor-pointer select-none';
      el.setAttribute('title', coveragePct == null
        ? `Grid zone ${zone.zone_id}; allocation not loaded`
        : `Grid zone ${zone.zone_id}: ${coveragePct.toFixed(1)}% ${coveragePreview ? `coverage at ${coveragePreviewStockPct}% assumed stock` : 'mean resource coverage'}`);

      // Determine ring thickness and animation speed inversely proportional to coverage
      let ringThickness = '1px';
      let ringColor = coveragePct == null ? 'rgba(148,163,184,0.72)' : 'rgba(16, 185, 129, 0.7)';
      let animDuration = 'none';
      let badgeBg = 'rgba(15, 23, 42, 0.85)';

      if (coveragePct != null && coveragePct < 40) {
        ringThickness = '4.5px';
        ringColor = 'rgba(239, 68, 68, 0.85)'; // red alert
        animDuration = '0.85s';
        badgeBg = 'rgba(153, 27, 27, 0.9)';
      } else if (coveragePct != null && coveragePct < 70) {
        ringThickness = '3px';
        ringColor = 'rgba(245, 158, 11, 0.8)'; // amber
        animDuration = '1.6s';
        badgeBg = 'rgba(180, 83, 9, 0.9)';
      } else if (coveragePct != null && coveragePct < 90) {
        ringThickness = '1.8px';
        ringColor = 'rgba(6, 182, 212, 0.7)'; // cyan
        animDuration = '2.5s';
        badgeBg = 'rgba(21, 94, 117, 0.9)';
      }

      const isPulsing = coveragePct != null && coveragePct < 90;

      el.innerHTML = `
        <div style="position: relative; display: flex; align-items: center; justify-content: center; width: 44px; height: 44px;">
          ${
            isPulsing
              ? `<div class="stress-pulse-ring" style="
                  position: absolute;
                  inset: 0;
                  border-radius: 9999px;
                  border: ${ringThickness} solid ${ringColor};
                  animation: zone-stress-pulse ${animDuration} infinite ease-in-out;
                  pointer-events: none;
                "></div>`
              : `<div style="
                  position: absolute;
                  inset: 6px;
                  border-radius: 9999px;
                  border: 1.5px solid ${ringColor};
                  pointer-events: none;
                "></div>`
          }
          <div style="
            position: relative;
            z-index: 2;
            padding: 2px 5px;
            border-radius: 6px;
            background: ${badgeBg};
            border: 1px solid ${ringColor};
            color: #f8fafc;
            font-family: monospace;
            font-size: 9px;
            font-weight: 700;
            box-shadow: 0 2px 6px rgba(0,0,0,0.5);
            text-align: center;
          ">
            ${zone.zone_id.match(/(\d+)$/)?.[1]?.padStart(2, '0') ?? 'â€”'}
            ${coveragePct == null ? '' : `<div style="font-size: 8px; opacity: 0.85; font-weight: normal;">${coveragePct.toFixed(0)}%</div>`}
          </div>
        </div>
      `;

      el.addEventListener('click', () => {
        onSelectZone(zone);
      });

      const marker = new maplibregl.Marker({ element: el, anchor: 'center' })
        .setLngLat([zone.centroid_lon, zone.centroid_lat])
        .addTo(map);

      markersRef.current.push(marker);
    });

    return () => {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
    };
  }, [zones, allocations, coveragePreview, coveragePreviewStockPct, showZones, is3DMode, onSelectZone]);

  return (
    <div id="resq-map-container" className="relative w-full h-full flex-1 min-h-[500px] overflow-hidden bg-ink-950">
      {/* MapLibre Canvas Container */}
      <div ref={mapContainerRef} className="absolute inset-0 w-full h-full" />

      {/* Verified closure state, without fabricated detour distances. */}
      {isClosureActive && (
        <div role="status" aria-live="polite" className="absolute top-3 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2.5 rounded-full border border-accent-alert/50 bg-ink-950/90 px-4 py-1.5 shadow-[0_0_20px_rgba(255,59,92,0.4)] backdrop-blur-md">
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-alert opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-accent-alert" />
          </span>
          <span className="text-xs font-mono font-bold text-accent-alert uppercase">
            Bantwal Road Blocked
          </span>
          <span className="text-xs font-mono text-text-secondary border-l border-white/10 pl-2">
            {closureDetourInfo
              ? `Distance: ${closureDetourInfo.beforeDistanceKm} km to ${closureDetourInfo.afterDistanceKm} km (+${(closureDetourInfo.afterDistanceKm - closureDetourInfo.beforeDistanceKm).toFixed(1)} km)`
            : `${closureRouteChangeCount ?? (routes.length || 16)} routes recalculated`}
          </span>
        </div>
      )}

      {selectedZoneId && (() => {
        const route = routes.find((item) => item.properties.zone_id === selectedZoneId);
        if (!route) return null;
        const distanceM = Number((route.properties as any).distance_m ?? (route.properties as any).road_distance_m);
        const mode = route.properties.delivery_mode;
        const routeLabel = mode === 'road' ? 'A*' : mode === 'secondary' ? 'Secondary distance' : 'No route available';
        return (
          <div className={`absolute ${isClosureActive ? 'top-14' : 'top-3'} left-1/2 -translate-x-1/2 z-20 flex items-center gap-3 rounded-xl border border-amber-200/25 bg-[#101b18]/95 px-4 py-2.5 shadow-xl backdrop-blur-md`}>
            <span className="w-2 h-2 rounded-full bg-amber-300 shadow-[0_0_12px_rgba(255,208,113,.8)]" />
            <span className="grid gap-0.5"><strong className="text-xs text-amber-100">Zone {selectedZoneId.match(/(\d+)$/)?.[1]?.padStart(2, '0')} - {routeLabel}</strong><span className="text-[10px] text-slate-300">{Number.isFinite(distanceM) ? `${(distanceM / 1000).toFixed(1)} km along cached OSM route` : 'No road distance recorded'}</span></span>
          </div>
        );
      })()}

      {/* SAR Opacity Slider â€“ top-right area */}
      {showOpacitySlider && (
        <div className="absolute top-16 right-16 z-30 glass-panel rounded-xl p-3 shadow-2xl flex items-center gap-3">
          <span className="text-xs font-mono text-text-secondary whitespace-nowrap">SAR Opacity:</span>
          <input type="range" min="0" max="1" step="0.05" value={sarOpacity} onChange={(e) => setSarOpacity(parseFloat(e.target.value))} className="w-28 accent-accent-cyan cursor-pointer" />
          <span className="text-xs font-mono font-bold text-accent-cyan w-8">{(sarOpacity * 100).toFixed(0)}%</span>
        </div>
      )}

      {/* Right-side Vertical Layer Toggle Panel */}
      <div className="map-layer-controls absolute right-3 bottom-3 z-20 pointer-events-auto grid grid-cols-2 gap-1 glass-panel rounded-2xl p-1.5 shadow-2xl backdrop-blur-xl border border-white/15">
        {[
          { active: false,        onClick: () => mapRef.current?.zoomIn(),      label: 'Zoom in',          icon: <Plus className="w-4 h-4" /> },
          { active: false,        onClick: () => mapRef.current?.zoomOut(),     label: 'Zoom out',         icon: <Minus className="w-4 h-4" /> },
          { active: showZones,      onClick: () => setShowZones(v => !v),      label: 'Grid Zones (16)',  icon: <Layers className="w-4 h-4" /> },
          { active: showSar,        onClick: () => { if (showSar) setShowOpacitySlider(v => !v); else { setShowSar(true); setShowOpacitySlider(false); } }, label: 'Candidate SAR signal', icon: <Radio className="w-4 h-4 text-accent-cyan" /> },
          { active: showRiver,      onClick: () => setShowRiver(v => !v),      label: 'River',            icon: <div className="w-3.5 h-3.5 rounded-full border-2 border-[#0C7894] bg-[#0C7894]/40" /> },
          { active: showRoads,      onClick: () => setShowRoads(v => !v),      label: 'Roads',            icon: <div className="w-3.5 h-1 bg-slate-400 rounded" /> },
          { active: showFacilities, onClick: () => setShowFacilities(v => !v), label: 'Facilities',       icon: <Shield className="w-4 h-4 text-amber-400" /> },
          { active: showClosures,   onClick: () => setShowClosures(v => !v),   label: 'Closures',         icon: <AlertTriangle className="w-4 h-4 text-accent-alert" /> },
          { active: showRoutes,     onClick: () => setShowRoutes(v => !v),     label: 'Routes',           icon: <Truck className="w-4 h-4 text-accent-cyan" /> },
          { active: is3DMode,       onClick: handleToggle3D,                   label: is3DMode ? 'Flat 2D' : '3D Mode', icon: <Rotate3d className="w-4 h-4 text-accent-indigo" /> },
        ].map((item, i) => (
          <button
            key={i}
            onClick={item.onClick}
            title={item.label}
            className={`relative group w-8 h-8 flex items-center justify-center rounded-lg transition-all ${
              item.active
                ? 'bg-accent-cyan/20 border border-accent-cyan/40 text-accent-cyan'
                : 'bg-white/[0.03] border border-white/10 text-text-muted hover:bg-white/[0.08] hover:text-text-primary hover:border-white/20'
            }`}
          >
            {item.icon}
            <span className="absolute right-full mr-2 px-2 py-1 rounded-md bg-ink-900/95 border border-white/15 text-[10px] font-mono text-text-secondary whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none shadow-lg">
              {item.label}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
};

export default MapConsole;


