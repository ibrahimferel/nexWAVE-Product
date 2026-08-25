'use client';

import React from 'react';
import AddIcon from '@mui/icons-material/Add';
import RemoveIcon from '@mui/icons-material/Remove';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import { Box, IconButton, Paper, Tooltip, Typography } from '@mui/material';
import mapData from '@/data/master_map_data.json';
import { getCursorAnchoredScrollOffset, getMapCanvasSize } from '@/lib/map-viewport';
import { IO_NODE, type RouteLeg } from '@/lib/route-legs';

type RouteStep = {
  id?: number;
  route_item_id?: number;
  location_id: string;
  product_ref?: string;
  status: string;
};

interface MapViewerProps {
  activeLevel: number;
  route: RouteStep[];
  routeLegs: RouteLeg[];
  activeLegIndex?: number;
}

type Segment = { x1: number; y1: number; x2: number; y2: number };

const MIN_ZOOM = 0.65;
const MAX_ZOOM = 2.4;
const ZOOM_STEP = 0.15;
const VIEWBOX_WIDTH = 1142;
const VIEWBOX_HEIGHT = 1329;
const MAP_GUTTER_X = 80;
const MAP_GUTTER_Y = 32;

function clampZoom(value: number) {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Number(value.toFixed(2))));
}

export default function MapViewer({ activeLevel, route, routeLegs }: MapViewerProps) {
  const { graph, racks } = mapData;
  const [zoom, setZoom] = React.useState(1);
  const [dragging, setDragging] = React.useState(false);
  const scrollAreaRef = React.useRef<HTMLDivElement>(null);
  const dragStart = React.useRef<{ pointerId: number; x: number; y: number; scrollLeft: number; scrollTop: number } | null>(null);
  const zoomAnchor = React.useRef<{ scrollLeft: number; scrollTop: number; cursorX: number; cursorY: number; previousZoom: number; nextZoom: number; viewportWidth: number; viewportHeight: number } | null>(null);
  const layoutFileName = activeLevel <= 2 ? 'Layout_1-2.svg' : 'Layout_3-4.svg';
  const canvasSize = getMapCanvasSize(zoom);

  // 1. Ekstraksi koordinat segmen garis peta
  const legSegments = React.useMemo(() => routeLegs.map((leg) => {
    const segments: Segment[] = [];
    for (let index = 0; index < leg.waypoints.length - 1; index += 1) {
      const fromNode = graph[leg.waypoints[index] as keyof typeof graph];
      const toNode = graph[leg.waypoints[index + 1] as keyof typeof graph];
      if (fromNode && toNode) segments.push({ x1: fromNode.x, y1: fromNode.y, x2: toNode.x, y2: toNode.y });
    }
    return segments;
  }), [graph, routeLegs]);

  // 2. Evaluasi indeks garis aktif dan garis masa depan secara akurat (Bayangan algoritma buildRouteLegs)
  const { activeLegIndex: trueActiveLegIndex, nextFutureLegIndex } = React.useMemo(() => {
    // Cari index tugas pertama yang belum selesai
    const firstUnpickedIdx = route.findIndex(s => s.status !== 'picked' && s.status !== 'problem');

    // Jika semua item sudah selesai, rute yang aktif adalah rute kembali ke Depot (leg terakhir)
    if (firstUnpickedIdx === -1) {
      return { 
        activeLegIndex: routeLegs.length > 0 ? routeLegs.length - 1 : -1, 
        nextFutureLegIndex: routeLegs.length 
      };
    }

    let physicalLegCount = 0;
    let fromNode = IO_NODE;

    // Telusuri pergerakan fisik dari Depot hingga target tugas saat ini
    for (let i = 0; i <= firstUnpickedIdx; i++) {
      const toNode = racks[route[i].location_id as keyof typeof racks]?.access_node;
      
      if (toNode && fromNode !== toNode) {
        if (i === firstUnpickedIdx) {
          // Harus bergerak ke lokasi berbeda
          return { activeLegIndex: physicalLegCount, nextFutureLegIndex: physicalLegCount + 1 };
        }
        physicalLegCount++;
        fromNode = toNode;
      } else if (i === firstUnpickedIdx) {
        // Sedang berada di lokasi yang sama (jarak 0 pixel, tidak perlu berjalan)
        return { activeLegIndex: -1, nextFutureLegIndex: physicalLegCount };
      }
    }
    
    return { activeLegIndex: -1, nextFutureLegIndex: routeLegs.length };
  }, [route, racks, routeLegs]);

  // 3. Agregasi Tampilan Pin dan Product Ref per Lokasi (Mencegah overlapping)
  const locationAggregates = React.useMemo(() => {
    const map = new Map<string, { location_id: string, x: number, y: number, isCurrentTarget: boolean, isFullyPicked: boolean, items: { ref: string, status: string }[] }>();
    
    const activeStepIndex = route.findIndex(s => s.status !== 'picked' && s.status !== 'problem');
    const currentTargetLoc = activeStepIndex !== -1 ? route[activeStepIndex].location_id : null;

    route.forEach((step) => {
      const rack = racks[step.location_id as keyof typeof racks];
      if (!rack) return;

      if (!map.has(step.location_id)) {
        map.set(step.location_id, {
          location_id: step.location_id,
          x: rack.actual_x,
          y: rack.actual_y,
          isCurrentTarget: step.location_id === currentTargetLoc,
          isFullyPicked: true,
          items: []
        });
      }
      
      const agg = map.get(step.location_id)!;
      agg.items.push({ ref: step.product_ref || 'Item', status: step.status });
      
      if (step.status !== 'picked' && step.status !== 'problem') {
        agg.isFullyPicked = false;
      }
    });

    return Array.from(map.values());
  }, [route, racks]);

  const setBoundedZoom = (nextZoom: number, cursor?: { x: number; y: number }) => {
    const area = scrollAreaRef.current;
    const boundedZoom = clampZoom(nextZoom);
    if (!area || boundedZoom === zoom) return;
    zoomAnchor.current = {
      scrollLeft: area.scrollLeft,
      scrollTop: area.scrollTop,
      cursorX: cursor?.x ?? area.clientWidth / 2,
      cursorY: cursor?.y ?? area.clientHeight / 2,
      previousZoom: zoom,
      nextZoom: boundedZoom,
      viewportWidth: area.clientWidth,
      viewportHeight: area.clientHeight,
    };
    setZoom(boundedZoom);
  };

  React.useLayoutEffect(() => {
    const area = scrollAreaRef.current;
    const anchor = zoomAnchor.current;
    if (!area || !anchor || anchor.nextZoom !== zoom) return;
    const offset = getCursorAnchoredScrollOffset(anchor);
    area.scrollLeft = offset.left;
    area.scrollTop = offset.top;
    zoomAnchor.current = null;
  }, [zoom]);

  return (
    <Box className="relative h-full min-h-0 w-full overflow-hidden rounded-b-2xl bg-[#eef2f8]">
      <Box
        ref={scrollAreaRef}
        className="map-scroll-area h-full w-full overflow-scroll"
        sx={{ cursor: dragging ? 'grabbing' : 'grab', touchAction: 'none' }}
        onWheel={(event) => {
          event.preventDefault();
          const bounds = event.currentTarget.getBoundingClientRect();
          setBoundedZoom(zoom + (event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP), {
            x: event.clientX - bounds.left,
            y: event.clientY - bounds.top,
          });
        }}
        onPointerDown={(event) => {
          const area = scrollAreaRef.current;
          if (!area || event.button !== 0) return;
          event.currentTarget.setPointerCapture(event.pointerId);
          dragStart.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, scrollLeft: area.scrollLeft, scrollTop: area.scrollTop };
          setDragging(true);
        }}
        onPointerMove={(event) => {
          const area = scrollAreaRef.current;
          const start = dragStart.current;
          if (!area || !start || start.pointerId !== event.pointerId) return;
          area.scrollLeft = start.scrollLeft - (event.clientX - start.x);
          area.scrollTop = start.scrollTop - (event.clientY - start.y);
        }}
        onPointerUp={(event) => {
          if (dragStart.current?.pointerId === event.pointerId) dragStart.current = null;
          setDragging(false);
        }}
        onPointerCancel={() => { dragStart.current = null; setDragging(false); }}
      >
        <Box
          className="flex min-h-full items-start justify-center"
          sx={{
            minWidth: canvasSize.width + MAP_GUTTER_X * 2,
            minHeight: canvasSize.height + MAP_GUTTER_Y * 2,
            px: `${MAP_GUTTER_X}px`,
            py: `${MAP_GUTTER_Y}px`,
          }}
        >
          <svg
            viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`}
            width={canvasSize.width}
            height={canvasSize.height}
            className="block max-w-none shrink-0 select-none rounded-[28px] bg-[#e3e8f0] shadow-[inset_0_0_0_1px_rgba(130,147,171,0.18)]"
            role="img"
            aria-label={`Peta gudang level ${activeLevel}`}
          >
            <image href={`/maps/${layoutFileName}`} x="0" y="0" width={VIEWBOX_WIDTH} height={VIEWBOX_HEIGHT} />
            <image href="/maps/Jalur_map.svg" x="0" y="0" width={VIEWBOX_WIDTH} height={VIEWBOX_HEIGHT} />

            {/* LAYER 1: RUTE MASA DEPAN (ORANYE) */}
            {legSegments.map((segments, legIndex) => {
              if (legIndex < nextFutureLegIndex) return null;
              return (
                <g key={`future-leg-${legIndex}`}>
                  {segments.map((segment, segmentIndex) => (
                    <line key={`seg-${segmentIndex}`} x1={segment.x1} y1={segment.y1} x2={segment.x2} y2={segment.y2} stroke="#ff6600" strokeWidth={4} />
                  ))}
                </g>
              );
            })}

            {/* LAYER 2: RUTE AKTIF (BIRU) */}
            {trueActiveLegIndex !== -1 && legSegments[trueActiveLegIndex] && (
              <g key={`active-leg-${trueActiveLegIndex}`}>
                {legSegments[trueActiveLegIndex].map((segment, segmentIndex) => (
                  <line key={`seg-${segmentIndex}`} x1={segment.x1} y1={segment.y1} x2={segment.x2} y2={segment.y2} stroke="#0056d6" strokeWidth={6} style={{ transition: 'stroke 240ms ease' }} />
                ))}
              </g>
            )}

            {/* LAYER 3: MARKER & DAFTAR PRODUK */}
            {locationAggregates.map((loc, idx) => {
              const pinColor = (loc.isCurrentTarget || loc.isFullyPicked) ? '#0056d6' : '#ff6600';
              
              return (
                <g key={`loc-${idx}`} transform={`translate(${loc.x - 12}, ${loc.y - 24})`}>
                  {loc.isCurrentTarget && (
                    <circle cx="12" cy="12" r="18" fill="none" stroke="#0056d6" strokeWidth="3" className="animate-ping opacity-75" />
                  )}
                  
                  <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7Zm0 9.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z" fill={pinColor} stroke="#ffffff" strokeWidth="2" />
                  
                  <text x="12" y="-8" fontSize="13" fill="#202938" textAnchor="middle" fontWeight="800" paintOrder="stroke" stroke="#ffffff" strokeWidth="4">
                    {loc.location_id}
                  </text>

                  {loc.items.map((item, itemIdx) => (
                    <text 
                      key={itemIdx} 
                      x="12" 
                      y={28 + (itemIdx * 12)} 
                      fontSize="10" 
                      fill={item.status === 'picked' ? '#0056d6' : (item.status === 'problem' ? '#ef4444' : '#526176')} 
                      textAnchor="middle" 
                      fontWeight="700" 
                      paintOrder="stroke" 
                      stroke="#ffffff" 
                      strokeWidth="3"
                    >
                      {item.status === 'picked' ? '✓ ' : ''}{item.ref}
                    </text>
                  ))}
                </g>
              );
            })}
          </svg>
        </Box>
      </Box>

      <Paper elevation={3} className="absolute right-5 top-4 z-10 flex items-center rounded-xl" aria-label="Kontrol zoom peta">
        <Tooltip title="Perkecil"><span><IconButton color="primary" onClick={() => setBoundedZoom(zoom - ZOOM_STEP)} disabled={zoom <= MIN_ZOOM} aria-label="Perkecil peta"><RemoveIcon /></IconButton></span></Tooltip>
        <Tooltip title="Atur ulang zoom"><IconButton color="primary" onClick={() => setBoundedZoom(1)} aria-label="Atur ulang zoom peta"><Typography variant="caption" sx={{ fontWeight: 800 }}>{Math.round(zoom * 100)}%</Typography></IconButton></Tooltip>
        <Tooltip title="Perbesar"><span><IconButton color="primary" onClick={() => setBoundedZoom(zoom + ZOOM_STEP)} disabled={zoom >= MAX_ZOOM} aria-label="Perbesar peta"><AddIcon /></IconButton></span></Tooltip>
        <Tooltip title="Kembali ke ukuran awal"><IconButton color="primary" onClick={() => setBoundedZoom(1)} aria-label="Kembali ke ukuran awal"><RestartAltIcon /></IconButton></Tooltip>
      </Paper>
    </Box>
  );
}