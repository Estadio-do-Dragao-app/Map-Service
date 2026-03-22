import { useEffect, useRef, useState } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faLocationCrosshairs,
  faCircleNodes,
  faTrash,
  faDumpster,
  faMousePointer,
  faHexagonNodes,
  faFileExport,
  faFileImport,
} from '@fortawesome/free-solid-svg-icons';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import '../styles/MapComponent.css';

const API_BASE = 'http://localhost:8001';

const AVEIRO_CENTER = [
  (40.628 + 40.635) / 2,
  (-8.662 + -8.654) / 2,
];

const NODE_TYPE_OPTIONS = [
  'corridor',
  'row_aisle',
  'seat',
  'gate',
  'stairs',
  'ramp',
  'restroom',
  'food',
  'bar',
  'merchandise',
  'first_aid',
  'emergency_exit',
  'information',
  'vip_box',
  'normal',
];

export function MapComponent() {
  const mapContainer     = useRef(null);
  const map              = useRef(null);
  const markersRef       = useRef({});
  const edgeLines        = useRef({});
  const tempNodeMarkerRef = useRef(null);
  const [pointsForEdge, setPointsForEdge] = useState({ from: null, to: null });

  const [nodes, setNodes]                         = useState([]);
  const [edges, setEdges]                         = useState([]);
  const [editingNode, setEditingNode]             = useState(null);
  const [showNodeForm, setShowNodeForm]           = useState(false);
  const [newNodePosition, setNewNodePosition]     = useState(null);
  const [formData, setFormData]                   = useState({ name: '', type: 'normal', door_id: null });
  const [creatingEdge, setCreatingEdge]           = useState(false);
  const [loading, setLoading]                     = useState(false);
  const [error, setError]                         = useState('');
  const [nodeSearchQuery, setNodeSearchQuery]     = useState('');
  const [edgeSearchQuery, setEdgeSearchQuery]     = useState('');
  const [newNodeIds, setNewNodeIds]               = useState(new Set());
  const [selectedNode, setSelectedNode]           = useState(null);
  const [selectedEdgeFromList, setSelectedEdgeFromList] = useState(null);
  const [showAllEdges, setShowAllEdges]           = useState(false);
  const [selectingDoor, setSelectingDoor]         = useState(false);
  const [rectangleSelectMode, setRectangleSelectMode] = useState(false);
  const [deleteMode, setDeleteMode]               = useState(false);
  const [rectStart, setRectStart]                 = useState(null);
  const [rectEnd, setRectEnd]                     = useState(null);
  const [selectedForDelete, setSelectedForDelete] = useState({ nodes: [], edges: [] });
  const [mapZoom, setMapZoom]                     = useState(null);
  const [editFormData, setEditFormData]           = useState({
    name: '', type: 'normal', level: 0, description: '',
    num_servers: null, service_rate: null, block: '',
    row: null, number: null, x: 0, y: 0, door_id: null,
  });
  const [draggedPosition, setDraggedPosition]     = useState(null);
  const rectangleRef = useRef(null);
  const hasFitBoundsRef = useRef(false);
  const markerTimersRef = useRef({});
  const FADE_DURATION_MS = 180;
  const prevHideNonPoiRef = useRef(false);

  // ── Fetch ────────────────────────────────────────────────────────────────
  const fetchData = async () => {
    try {
      setLoading(true);
      const [nodesRes, edgesRes] = await Promise.all([
        fetch(`${API_BASE}/nodes`),
        fetch(`${API_BASE}/edges`),
      ]);
      if (!nodesRes.ok || !edgesRes.ok) throw new Error('Failed to fetch data');
      setNodes(await nodesRes.json());
      setEdges(await edgesRes.json());
    } catch (err) {
      setError(err.message);
      console.error('Error fetching data:', err);
    } finally {
      setLoading(false);
    }
  };

  // ── Select node ──────────────────────────────────────────────────────────
  const selectNode = (node) => {
    if (selectingDoor && editingNode) {
      setEditFormData({ ...editFormData, door_id: node.id });
      setSelectingDoor(false);
      return;
    }
    if (creatingEdge || rectangleSelectMode) return;
    if (node.door_id) {
      const doorNode = nodes.find(n => n.id === node.door_id);
      if (doorNode) {
        setSelectedNode(doorNode);
        setSelectedEdgeFromList(null);
        if (editingNode) setEditingNode(null);
        return;
      }
    }
    setSelectedNode(node);
    setSelectedEdgeFromList(null);
    if (editingNode) setEditingNode(null);
  };

  const selectEdge = (edgeId) => {
    setSelectedEdgeFromList(selectedEdgeFromList === edgeId ? null : edgeId);
    setSelectedNode(null);
  };

  // ── Edit ─────────────────────────────────────────────────────────────────
  const startEditNode = (node) => {
    setEditingNode(node.id);
    setEditFormData({
      name: node.name || '', type: node.type || 'normal',
      level: node.level || 0, description: node.description || '',
      num_servers: node.num_servers || null, service_rate: node.service_rate || null,
      block: node.block || '', row: node.row || null,
      number: node.number || null, x: node.x, y: node.y,
      door_id: node.door_id || null,
    });
    setDraggedPosition({ lat: node.y, lng: node.x });
    if (map.current) map.current.setView([node.y, node.x], map.current.getZoom());
  };

  const updateNode = async () => {
    if (!editingNode || !draggedPosition) return;
    try {
      const response = await fetch(`${API_BASE}/nodes/${editingNode}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...editFormData,
          x: draggedPosition.lng, y: draggedPosition.lat,
          door_id: editFormData.door_id || null,
        }),
      });
      if (!response.ok) throw new Error('Failed to update node');
      await fetchData();
      setEditingNode(null); setDraggedPosition(null); setSelectedNode(null);
    } catch (err) { setError(err.message); }
  };

  const cancelEdit = () => { setEditingNode(null); setDraggedPosition(null); };

  // ── Delete node ──────────────────────────────────────────────────────────
  const deleteNode = async (nodeId) => {
    if (!confirm('Are you sure you want to delete this node? Connected edges will also be deleted.')) return;
    try {
      await fetch(`${API_BASE}/nodes/${nodeId}`, { method: 'DELETE' });
      await fetchData();
      setSelectedNode(null);
      setNewNodeIds(prev => { const s = new Set(prev); s.delete(nodeId); return s; });
    } catch (err) { setError(err.message); }
  };

  // ── Delete edge ──────────────────────────────────────────────────────────
  const deleteEdge = async (edgeId) => {
    if (!confirm('Are you sure you want to delete this edge?')) return;
    try {
      await fetch(`${API_BASE}/edges/${edgeId}`, { method: 'DELETE' });
      await fetchData();
    } catch (err) { setError(err.message); }
  };

  // ── Create node ──────────────────────────────────────────────────────────
  const createNode = async () => {
    if (!newNodePosition || !formData.name) { alert('Please enter a node name'); return; }
    const newId = `node_${Date.now()}`;
    try {
      const response = await fetch(`${API_BASE}/nodes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: newId, name: formData.name,
          x: newNodePosition[1], y: newNodePosition[0],
          type: formData.type, level: 0, description: '',
          num_servers: null, service_rate: null, block: '',
          row: null, number: null, door_id: formData.door_id || null,
        }),
      });
      if (!response.ok) throw new Error('Failed to create node');
      await fetchData();
      setShowNodeForm(false); setNewNodePosition(null);
      setFormData({ name: '', type: 'normal', door_id: null });
      setNewNodeIds(prev => new Set([...prev, newId]));
      if (tempNodeMarkerRef.current) {
        map.current.removeLayer(tempNodeMarkerRef.current);
        tempNodeMarkerRef.current = null;
      }
    } catch (err) { setError(err.message); }
  };

  // ── Create edge ──────────────────────────────────────────────────────────
  const createEdge = async () => {
    if (!pointsForEdge.from || !pointsForEdge.to) { alert('Please select two nodes'); return; }
    try {
      const response = await fetch(`${API_BASE}/edges`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: `edge_${Date.now()}`, from_id: pointsForEdge.from,
          to_id: pointsForEdge.to, weight: 1.0, accessible: true,
        }),
      });
      if (!response.ok) throw new Error('Failed to create edge');
      await fetchData();
      setPointsForEdge({ from: null, to: null }); setCreatingEdge(false);
    } catch (err) { setError(err.message); }
  };

  // ── Rectangle select ─────────────────────────────────────────────────────
  const updateSelectedForDeleteFromRect = (start, end) => {
    if (!start || !end || !map.current) return;
    const bounds = L.latLngBounds(start, end);
    const nodesInBounds = nodes.filter(node => bounds.contains(L.latLng(node.y, node.x)));
    const edgesInBounds = edges.filter(edge =>
      nodesInBounds.some(n => n.id === edge.from_id) && nodesInBounds.some(n => n.id === edge.to_id)
    );
    setSelectedForDelete({ nodes: nodesInBounds, edges: edgesInBounds });
  };

  const clearRectangleSelection = () => {
    setRectStart(null); setRectEnd(null);
    setSelectedForDelete({ nodes: [], edges: [] });
    if (rectangleRef.current) { map.current.removeLayer(rectangleRef.current); rectangleRef.current = null; }
  };

  const cancelRectangleMode = () => { setRectangleSelectMode(false); clearRectangleSelection(); };

  const clearTempNodeMarker = () => {
    if (tempNodeMarkerRef.current && map.current) {
      map.current.removeLayer(tempNodeMarkerRef.current);
      tempNodeMarkerRef.current = null;
    }
  };

  // ── Import / Export ──────────────────────────────────────────────────────
  const fileInputRef = useRef(null);

  const exportMap = async () => {
    try {
      const response = await fetch(`${API_BASE}/export`);
      if (!response.ok) throw new Error('Failed to export map');
      const data = await response.json();
      
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'campus_map.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(`Export error: ${err.message}`);
    }
  };

  const handleImportFile = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    try {
      setLoading(true);
      const text = await file.text();
      const data = JSON.parse(text);

      const mappedEdges = (data.edges || []).map(edge => ({
        id: edge.id,
        from_id: edge.from_id || edge.from,
        to_id: edge.to_id || edge.to,
        weight: edge.weight !== undefined ? edge.weight : edge.w,
        accessible: edge.accessible !== undefined ? edge.accessible : true,
      }));

      const response = await fetch(`${API_BASE}/batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nodes: data.nodes || [],
          edges: mappedEdges,
          closures: data.closures || [],
        }),
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Failed to import map');
      }

      await fetchData();
      if (fileInputRef.current) fileInputRef.current.value = '';
      alert('Map imported successfully!');
    } catch (err) {
      setError(`Import error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const setToolMode = (mode) => {
    setCreatingEdge(false);
    setShowNodeForm(false);
    setRectangleSelectMode(false);
    setDeleteMode(false);
    setSelectingDoor(false);
    setPointsForEdge({ from: null, to: null });
    setSelectedNode(null);
    setSelectedEdgeFromList(null);
    clearRectangleSelection();
    clearTempNodeMarker();

    if (mode === 'node') {
      setShowNodeForm(true);
      setNewNodePosition(null);
    }
    if (mode === 'edge') setCreatingEdge(true);
    if (mode === 'bulk') setRectangleSelectMode(true);
    if (mode === 'delete') setDeleteMode(true);
  };

  const deleteSelectedItems = async () => {
    if (!selectedForDelete.nodes.length && !selectedForDelete.edges.length) return;
    try {
      await Promise.all([
        ...selectedForDelete.edges.map(edge => fetch(`${API_BASE}/edges/${edge.id}`, { method: 'DELETE' })),
        ...selectedForDelete.nodes.map(node => fetch(`${API_BASE}/nodes/${node.id}`, { method: 'DELETE' })),
      ]);
      setNewNodeIds(prev => {
        const s = new Set(prev); selectedForDelete.nodes.forEach(n => s.delete(n.id)); return s;
      });
      await fetchData(); cancelRectangleMode();
    } catch (err) { setError(`Error deleting items: ${err.message}`); }
  };

  const clearMarkerTimer = (nodeId) => {
    if (markerTimersRef.current[nodeId]) {
      clearTimeout(markerTimersRef.current[nodeId]);
      delete markerTimersRef.current[nodeId];
    }
  };

  const setMarkerVisible = (entry, visible, fillOpacity = 0.9) => {
    if (!entry) return;
    if (entry.kind === 'circle') {
      entry.marker.setStyle({ opacity: visible ? 1 : 0, fillOpacity: visible ? fillOpacity : 0 });
    } else {
      entry.marker.setOpacity(visible ? 1 : 0);
    }
  };

  const scheduleMarkerRemoval = (nodeId, entry) => {
    clearMarkerTimer(nodeId);
    setMarkerVisible(entry, false);
    markerTimersRef.current[nodeId] = setTimeout(() => {
      entry.marker.remove();
      delete markersRef.current[nodeId];
      delete markerTimersRef.current[nodeId];
    }, FADE_DURATION_MS);
  };

  // ── Map rendering ─────────────────────────────────────────────────────────
  const updateMapView = () => {
    if (!map.current) return;

    const minNodeZoom = 18;
    const hideNonPoi = mapZoom !== null && mapZoom < minNodeZoom && !showAllEdges;
    const fadeOutOnZoom = hideNonPoi && !prevHideNonPoiRef.current;
    const fadeInOnZoom = !hideNonPoi && prevHideNonPoiRef.current;
    const nodeIdSet = new Set(nodes.map((node) => node.id));

    Object.values(edgeLines.current).forEach(line => line.remove());
    edgeLines.current = {};

    // Edges
    edges.forEach(edge => {
      const fromNode = nodes.find(n => n.id === edge.from_id);
      const toNode   = nodes.find(n => n.id === edge.to_id);
      const isEdgeSelected = selectedEdgeFromList === edge.id;
      const isInDelete     = selectedForDelete.edges.some(e => e.id === edge.id);
      if (!fromNode || !toNode) return;

      // Only draw if explicitly shown, selected, or in delete selection
      if (!showAllEdges && !isEdgeSelected && !isInDelete) return;

      let color = '#4CAF50', weight = 3;
      if (isInDelete)        { color = '#ffa500'; weight = 4; }
      else if (isEdgeSelected){ color = '#ff6b6b'; weight = 4; }

      const line = L.polyline([[fromNode.y, fromNode.x], [toNode.y, toNode.x]], {
        color, weight, opacity: 0.7,
      }).addTo(map.current);

      line.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        if (deleteMode) {
          deleteEdge(edge.id);
          return;
        }
        if (creatingEdge || rectangleSelectMode) return;
        selectEdge(edge.id);
      });
      edgeLines.current[edge.id] = line;
    });

    // Nodes
    const visibleNodeIds = new Set();
    const hiddenByZoom = new Set();
    nodes.forEach(node => {
      const poiTypes = new Set([
        'poi',
        'restroom',
        'food',
        'bar',
        'merchandise',
        'first_aid',
        'emergency_exit',
        'information',
        'vip_box',
      ]);
      const isPoi = poiTypes.has((node.type || '').toLowerCase());
      if (hideNonPoi && !isPoi) {
        hiddenByZoom.add(node.id);
        return;
      }
      visibleNodeIds.add(node.id);
      const isFromNode       = pointsForEdge.from === node.id;
      const isToNode         = pointsForEdge.to   === node.id;
      const isEdgeSelected   = isFromNode || isToNode;
      const isListSelected   = selectedNode?.id === node.id;
      const isPartOfEdgeSel  = selectedEdgeFromList &&
        (edges.find(e => e.id === selectedEdgeFromList)?.from_id === node.id ||
         edges.find(e => e.id === selectedEdgeFromList)?.to_id   === node.id);
      const isNewNode        = newNodeIds.has(node.id);
      const matchesSearch    = nodeSearchQuery === '' ||
        (node.name && node.name.toLowerCase().includes(nodeSearchQuery.toLowerCase()));
      const isInDelete       = selectedForDelete.nodes.some(n => n.id === node.id);
      const isSelectingDoor  = selectingDoor && editingNode;

      const baseColor = isNewNode ? '#4CAF50' : '#313b84';
      let fillColor = baseColor, radius = 7;

      if (isSelectingDoor)     { fillColor = '#9c27b0'; radius = 9; }
      else if (isInDelete)     { fillColor = '#ffa500'; radius = 10; }
      else if (isListSelected) { fillColor = '#ff6b6b'; radius = 14; }
      else if (isPartOfEdgeSel){ fillColor = '#ff6b6b'; radius = 12; }
      else if (isEdgeSelected) { fillColor = '#ffc107'; radius = 10; }

      const markerKind = node.id === editingNode && draggedPosition
        ? 'edit'
        : (isPoi ? 'poi' : 'circle');
      const existingEntry = markersRef.current[node.id];
      let entry = existingEntry;

      if (!entry || entry.kind !== markerKind) {
        if (entry) entry.marker.remove();

        if (markerKind === 'edit') {
          const editMarker = L.marker([draggedPosition.lat, draggedPosition.lng], {
            draggable: true,
            icon: L.divIcon({
              className: 'editing-marker',
              html: '<div style="background-color:#ff6b6b;width:24px;height:24px;border-radius:50%;border:3px solid white;box-shadow:0 0 10px rgba(255,107,107,0.5);"></div>',
              iconSize: [24, 24], iconAnchor: [12, 12],
            }),
          }).addTo(map.current);
          editMarker.on('drag',    (e) => { const p = e.target.getLatLng(); setDraggedPosition({ lat: p.lat, lng: p.lng }); });
          editMarker.on('dragend', (e) => { const p = e.target.getLatLng(); setDraggedPosition({ lat: p.lat, lng: p.lng }); });
          editMarker.bindPopup(`<strong>Editing: ${node.name || node.id}</strong><br/>Drag to move`);
          entry = { marker: editMarker, kind: 'edit' };
        } else if (markerKind === 'poi') {
          const poiStateClass = isInDelete
            ? 'poi-delete'
            : (isListSelected || isPartOfEdgeSel || isEdgeSelected ? 'poi-selected' : '');
          const poiMarker = L.marker([node.y, node.x], {
            icon: L.divIcon({
              className: `poi-marker ${poiStateClass}`,
              html: '<div class="poi-marker-pin"></div><div class="poi-marker-dot"></div>',
              iconSize: [22, 30],
              iconAnchor: [11, 30],
              popupAnchor: [0, -24],
            }),
          }).addTo(map.current);
          poiMarker.bindPopup(`
            <strong>${node.name || 'Unnamed'}</strong><br/>
            ID: ${node.id}<br/>
            Tipo: ${node.type || 'normal'}<br/>
            ${node.description ? `Desc: ${node.description}<br/>` : ''}
            Lat: ${node.y.toFixed(6)}<br/>
            Lng: ${node.x.toFixed(6)}<br/>
            ${isNewNode ? '<em>New</em>' : ''}
          `);
          entry = { marker: poiMarker, kind: 'poi' };
        } else {
          const circleMarker = L.circleMarker([node.y, node.x], {
            radius, fill: true, fillColor,
            fillOpacity: matchesSearch ? 0.9 : 0.4,
            stroke: true, color: fillColor, weight: 2,
            opacity: 1,
          }).addTo(map.current);
          circleMarker.bindPopup(`
            <strong>${node.name || 'Unnamed'}</strong><br/>
            ID: ${node.id}<br/>
            Tipo: ${node.type || 'normal'}<br/>
            ${node.description ? `Desc: ${node.description}<br/>` : ''}
            Lat: ${node.y.toFixed(6)}<br/>
            Lng: ${node.x.toFixed(6)}<br/>
            ${isNewNode ? '<em>New</em>' : ''}
          `);
          entry = { marker: circleMarker, kind: 'circle' };
        }

        markersRef.current[node.id] = entry;
      }

      entry.marker.off('click');
      entry.marker.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        if (!creatingEdge) entry.marker.openPopup();
        if (deleteMode) {
          deleteNode(node.id);
          return;
        }
        if (creatingEdge) {
          setPointsForEdge((prev) => {
            if (!prev.from) return { ...prev, from: node.id };
            if (!prev.to && node.id !== prev.from) return { ...prev, to: node.id };
            return prev;
          });
          return;
        }
        selectNode(node);
      });

      clearMarkerTimer(node.id);

      if (entry.kind === 'circle') {
        entry.marker.setLatLng([node.y, node.x]);
        entry.marker.setRadius(radius);
        entry.marker.setStyle({
          fillColor,
          color: fillColor,
          opacity: 1,
          fillOpacity: matchesSearch ? 0.9 : 0.4,
        });
      } else if (entry.kind === 'poi') {
        const poiStateClass = isInDelete
          ? 'poi-delete'
          : (isListSelected || isPartOfEdgeSel || isEdgeSelected ? 'poi-selected' : '');
        entry.marker.setLatLng([node.y, node.x]);
        entry.marker.setIcon(L.divIcon({
          className: `poi-marker ${poiStateClass}`,
          html: '<div class="poi-marker-pin"></div><div class="poi-marker-dot"></div>',
          iconSize: [22, 30],
          iconAnchor: [11, 30],
          popupAnchor: [0, -24],
        }));
      } else if (entry.kind === 'edit' && draggedPosition) {
        entry.marker.setLatLng([draggedPosition.lat, draggedPosition.lng]);
      }

      if (fadeInOnZoom) {
        if (entry.kind === 'circle') setMarkerVisible(entry, false, 0);
        else setMarkerVisible(entry, false);
        setTimeout(() => {
          if (entry.kind === 'circle') setMarkerVisible(entry, true, matchesSearch ? 0.9 : 0.4);
          else setMarkerVisible(entry, true);
        }, 0);
      }
    });

    Object.entries(markersRef.current).forEach(([nodeId, entry]) => {
      if (!nodeIdSet.has(nodeId)) {
        clearMarkerTimer(nodeId);
        entry.marker.remove();
        delete markersRef.current[nodeId];
        return;
      }
      if (hiddenByZoom.has(nodeId)) {
        if (fadeOutOnZoom) scheduleMarkerRemoval(nodeId, entry);
        return;
      }
      if (!visibleNodeIds.has(nodeId)) {
        clearMarkerTimer(nodeId);
        entry.marker.remove();
        delete markersRef.current[nodeId];
      }
    });

    prevHideNonPoiRef.current = hideNonPoi;

    // Temp marker
    if (tempNodeMarkerRef.current) { map.current.removeLayer(tempNodeMarkerRef.current); tempNodeMarkerRef.current = null; }
    if (newNodePosition) {
      const marker = L.circleMarker(newNodePosition, {
        radius: 8, fill: true, fillColor: '#4CAF50', fillOpacity: 0.8,
        stroke: true, color: '#4CAF50', weight: 2,
      }).addTo(map.current);
      tempNodeMarkerRef.current = marker;
    }
  };

  // ── Init map ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (map.current) return;

    map.current = L.map(mapContainer.current, {
      dragging: false,
      touchZoom: true,
      scrollWheelZoom: true,
      maxZoom: 50,
      zoomControl: false,
    }).setView(AVEIRO_CENTER, 16);

    L.control.zoom({ position: 'bottomright' }).addTo(map.current);

    if (map.current.dragging) map.current.dragging.disable();

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
      maxZoom: 50,
      maxNativeZoom: 19,
    }).addTo(map.current);

    setMapZoom(map.current.getZoom());
    const handleZoom = () => setMapZoom(map.current.getZoom());
    map.current.on('zoomend', handleZoom);

    // Left-click drag or middle-click drag to pan
    let isPanning = false, panStart = null;
    const container = map.current.getContainer();

    container.addEventListener('mousedown', (e) => {
      if (e.button === 0 || e.button === 1) {
        e.preventDefault();
        isPanning = true;
        panStart = { x: e.clientX, y: e.clientY };
        container.style.cursor = 'grabbing';
      }
    });
    container.addEventListener('mousemove', (e) => {
      if (isPanning && panStart) {
        e.preventDefault();
        const dx = e.clientX - panStart.x;
        const dy = e.clientY - panStart.y;
        map.current.panBy([-dx, -dy], { animate: false });
        panStart = { x: e.clientX, y: e.clientY };
      }
    });
    const stopPan = () => { isPanning = false; panStart = null; container.style.cursor = ''; };
    container.addEventListener('mouseup',    stopPan);
    container.addEventListener('mouseleave', stopPan);

    fetchData();

    return () => {
      if (map.current) {
        map.current.off('zoomend', handleZoom);
        map.current.remove();
        map.current = null;
      }
      Object.values(markerTimersRef.current).forEach((timerId) => clearTimeout(timerId));
      markerTimersRef.current = {};
    };
  }, []);

  // ── Map click handler ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!map.current) return;
    const handleMapClick = (e) => {
      if (deleteMode) return;
      if (rectangleSelectMode) {
        if (!rectStart) {
          setRectStart(e.latlng);
          if (rectangleRef.current) { map.current.removeLayer(rectangleRef.current); rectangleRef.current = null; }
        } else if (!rectEnd) {
          setRectEnd(e.latlng);
          const bounds = L.latLngBounds(rectStart, e.latlng);
          rectangleRef.current = L.rectangle(bounds, {
            color: '#ff6b6b', weight: 2, opacity: 0.5,
            fill: true, fillColor: '#ff6b6b', fillOpacity: 0.2,
          }).addTo(map.current);
          updateSelectedForDeleteFromRect(rectStart, e.latlng);
        }
        return;
      }
      if (showNodeForm && !newNodePosition) setNewNodePosition([e.latlng.lat, e.latlng.lng]);
    };
    map.current.on('click', handleMapClick);
    return () => { if (map.current) map.current.off('click', handleMapClick); };
  }, [rectangleSelectMode, rectStart, rectEnd, showNodeForm, newNodePosition, deleteMode]);

  // ── Fit bounds on first load ──────────────────────────────────────────────
  useEffect(() => {
    if (!map.current || nodes.length === 0 || hasFitBoundsRef.current) return;
    try {
      const fg = L.featureGroup(nodes.map(n => L.marker([n.y, n.x])));
      map.current.fitBounds(fg.getBounds(), { padding: [50, 50] });
      hasFitBoundsRef.current = true;
    } catch (err) { console.error('Error fitting bounds:', err); }
  }, [nodes]);

  // ── Redraw ────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (map.current) updateMapView();
  }, [nodes, edges, pointsForEdge, newNodePosition, selectedNode, selectedEdgeFromList,
      selectedForDelete, nodeSearchQuery, creatingEdge, editingNode, draggedPosition,
      showAllEdges, selectingDoor, deleteMode, mapZoom]);

  // ── Filtered lists ────────────────────────────────────────────────────────
  const filteredNodes = nodes.filter(node =>
    nodeSearchQuery === '' || (node.name && node.name.toLowerCase().includes(nodeSearchQuery.toLowerCase()))
  );

  const filteredEdges = edges.filter(edge => {
    const fromNode = nodes.find(n => n.id === edge.from_id);
    const toNode   = nodes.find(n => n.id === edge.to_id);
    const q = edgeSearchQuery.toLowerCase();
    return !q || edge.id.toLowerCase().includes(q) ||
      (fromNode?.name && fromNode.name.toLowerCase().includes(q)) ||
      (toNode?.name   && toNode.name.toLowerCase().includes(q)) ||
      edge.from_id.toLowerCase().includes(q) || edge.to_id.toLowerCase().includes(q);
  });

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="map-container">
      <div className="map-stage">
        <div ref={mapContainer} className="map" />

        <div className="map-toolbar-left">
          <input
            type="file"
            accept=".json"
            style={{ display: 'none' }}
            ref={fileInputRef}
            onChange={handleImportFile}
          />
          <button
            className="tool-button"
            title="Import"
            onClick={() => fileInputRef.current && fileInputRef.current.click()}>
            <FontAwesomeIcon icon={faFileImport} />
            <span>Import</span>
          </button>
          <button
            className="tool-button"
            title="Export"
            onClick={exportMap}>
            <FontAwesomeIcon icon={faFileExport} />
            <span>Export</span>
          </button>
        </div>

        <div className="map-toolbar">
          <button
            className={`tool-button ${!showNodeForm && !creatingEdge && !rectangleSelectMode && !deleteMode ? 'active' : ''}`}
            onClick={() => setToolMode('select')}
            title="Select">
            <FontAwesomeIcon icon={faMousePointer} />
            <span>Select</span>
          </button>
          <button
            className={`tool-button ${showNodeForm ? 'active' : ''}`}
            onClick={() => setToolMode(showNodeForm ? 'select' : 'node')}
            title="Add node">
            <FontAwesomeIcon icon={faLocationCrosshairs} />
            <span>Add Node</span>
          </button>
          <button
            className={`tool-button ${creatingEdge ? 'active' : ''}`}
            onClick={() => setToolMode(creatingEdge ? 'select' : 'edge')}
            title="Add edge">
            <FontAwesomeIcon icon={faCircleNodes} />
            <span>Add Edge</span>
          </button>
          <button
            className={`tool-button ${deleteMode ? 'active' : ''}`}
            onClick={() => setToolMode(deleteMode ? 'select' : 'delete')}
            title="Delete">
            <FontAwesomeIcon icon={faTrash} />
            <span>Delete</span>
          </button>
          <button
            className={`tool-button ${rectangleSelectMode ? 'active' : ''}`}
            onClick={() => setToolMode(rectangleSelectMode ? 'select' : 'bulk')}
            title="Bulk delete">
            <FontAwesomeIcon icon={faDumpster} />
            <span>Bulk Delete</span>
          </button>
        </div>

        <div className="edge-filter">
          <button
            className={`edge-filter-button ${showAllEdges ? 'active' : ''}`}
            onClick={() => setShowAllEdges(!showAllEdges)}>
            <FontAwesomeIcon icon={faHexagonNodes} />
          </button>
          <div className="edge-filter-tooltip">
            {showAllEdges ? 'Hide All edges' : 'Show All edges'}
          </div>
        </div>
      </div>

      <div className="map-sidebar">

        {/* Header */}
        <div className="sidebar-header">
          <h2>Map Editor</h2>
          <div className="subtitle">{nodes.length} nodes · {edges.length} edges · drag to pan</div>
        </div>

        <div className="sidebar-body">

          {error   && <div className="error-message">{error}</div>}
          {loading && <div className="loading">Loading...</div>}

          {/* Mode banners */}
          {creatingEdge && (
            <div className="mode-banner edge">Edge mode — click two nodes to connect</div>
          )}
          {selectingDoor && (
            <div className="mode-banner door">Door mode — click a node on the map</div>
          )}
          {rectangleSelectMode && (
            <div className="mode-banner rect">
              Rectangle select
              {rectStart && !rectEnd && ' — click the opposite corner'}
              {!rectStart && ' — click the first corner'}
            </div>
          )}
          {deleteMode && (
            <div className="mode-banner delete">Delete mode — click a node or edge to remove</div>
          )}

          {showNodeForm && (
            <div className="control-section">
              <h3>Add Node</h3>
              <div className="form-group">
                <label>Name</label>
                <input type="text" value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="Node name" autoFocus />
              </div>
              <div className="form-group">
                <label>Type</label>
                <select value={formData.type} onChange={(e) => setFormData({ ...formData, type: e.target.value })}>
                  {NODE_TYPE_OPTIONS.map((type) => (
                    <option key={type} value={type}>{type}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Door Node (optional)</label>
                <select value={formData.door_id || ''} onChange={(e) => setFormData({ ...formData, door_id: e.target.value || null })}>
                  <option value="">None</option>
                  {nodes.map(node => <option key={node.id} value={node.id}>{node.name || node.id}</option>)}
                </select>
              </div>
              <p className="hint">
                {newNodePosition
                  ? `Position: (${newNodePosition[0].toFixed(4)}, ${newNodePosition[1].toFixed(4)})`
                  : 'Click on the map to set position'}
              </p>
              <div className="button-group">
                <button className="btn-primary" onClick={createNode} disabled={!newNodePosition}>Create</button>
                <button className="btn-secondary" onClick={() => {
                  setToolMode('select');
                  setNewNodePosition(null);
                  setFormData({ name: '', type: 'normal', door_id: null });
                }}>Cancel</button>
              </div>
            </div>
          )}

          {rectangleSelectMode && (
            <div className="control-section">
              <h3>Bulk Delete</h3>
              <p className="hint">
                {!rectStart && 'Click on the map for the first corner'}
                {rectStart && !rectEnd && 'Click the opposite corner'}
              </p>
              {rectStart && rectEnd && (
                <>
                  <p className="selected-nodes">
                    {selectedForDelete.nodes.length} nodes · {selectedForDelete.edges.length} edges
                  </p>
                  <div className="button-group">
                    <button className="btn-primary btn-delete" onClick={deleteSelectedItems}>Delete All</button>
                    <button className="btn-secondary" onClick={cancelRectangleMode}>Cancel</button>
                  </div>
                </>
              )}
              {(!rectStart || (rectStart && !rectEnd)) && (
                <button className="btn-secondary" onClick={cancelRectangleMode} style={{ marginTop: '8px' }}>Cancel</button>
              )}
            </div>
          )}

          {creatingEdge && (
            <div className="control-section">
              <h3>Connect Nodes</h3>
              <p className="hint">Click two nodes to connect them</p>
              {pointsForEdge.from && <p className="selected-nodes">From: {pointsForEdge.from}</p>}
              {pointsForEdge.to   && <p className="selected-nodes">To: {pointsForEdge.to}</p>}
              <div className="button-group">
                <button className="btn-primary" onClick={createEdge} disabled={!pointsForEdge.from || !pointsForEdge.to}>
                  Create Edge
                </button>
                <button className="btn-secondary" onClick={() => setToolMode('select')}>
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* ── Node Details ──────────────────────────────────────────── */}
          {selectedNode && !editingNode && (
            <div className="control-section">
              <h3>Node Details</h3>
              {[
                ['ID',           selectedNode.id],
                ['Name',         selectedNode.name || '—'],
                ['Type',         selectedNode.type],
                ['Level',        selectedNode.level],
                ['Description',    selectedNode.description || '—'],
                ['Num. Servers', selectedNode.num_servers ?? '—'],
                ['Service Rate', selectedNode.service_rate ?? '—'],
                ['Block',        selectedNode.block || '—'],
                ['Row',         selectedNode.row ?? '—'],
                ['Number',       selectedNode.number ?? '—'],
                ['Door',        selectedNode.door_id
                  ? (nodes.find(n => n.id === selectedNode.door_id)?.name || selectedNode.door_id)
                  : '—'],
                ['Coordinates',  `${selectedNode.y.toFixed(6)}, ${selectedNode.x.toFixed(6)}`],
              ].map(([label, val]) => (
                <div className="form-group" key={label}>
                  <label>{label}</label>
                  <div>{val}</div>
                </div>
              ))}
              <div className="button-group" style={{ gap: '4px', marginTop: '8px' }}>
                <button className="btn-primary" style={{ padding: '5px 8px', fontSize: '11px' }} onClick={() => startEditNode(selectedNode)}>Edit</button>
                <button className="btn-primary btn-delete" style={{ padding: '5px 8px', fontSize: '11px' }} onClick={() => deleteNode(selectedNode.id)}>Delete</button>
                <button className="btn-secondary" style={{ padding: '5px 8px', fontSize: '11px' }} onClick={() => setSelectedNode(null)}>Close</button>
              </div>
            </div>
          )}

          {/* ── Edit Node ─────────────────────────────────────────────── */}
          {editingNode && (
            <div className="control-section">
              <h3>Edit Node</h3>
              <div className="form-group">
                <label>Name</label>
                <input type="text" value={editFormData.name}
                  onChange={(e) => setEditFormData({ ...editFormData, name: e.target.value })} />
              </div>
              <div className="form-group">
                <label>Type</label>
                <select value={editFormData.type} onChange={(e) => setEditFormData({ ...editFormData, type: e.target.value })}>
                  {NODE_TYPE_OPTIONS.map((type) => (
                    <option key={type} value={type}>{type}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Door Node</label>
                <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                  <select value={editFormData.door_id || ''}
                    onChange={(e) => setEditFormData({ ...editFormData, door_id: e.target.value || null })}
                    style={{ flex: 1 }}>
                    <option value="">None</option>
                    {nodes.map(node => <option key={node.id} value={node.id}>{node.name || node.id}</option>)}
                  </select>
                  <button className={`btn-secondary ${selectingDoor ? 'btn-active' : ''}`}
                    onClick={() => setSelectingDoor(!selectingDoor)}
                    style={{ borderColor: selectingDoor ? '#bc8cff' : undefined, color: selectingDoor ? '#bc8cff' : undefined, minWidth: '90px', width: 'auto' }}>
                    {selectingDoor ? 'Selecting' : 'Select'}
                  </button>
                </div>
                {selectingDoor && (
                  <p className="hint" style={{ borderColor: '#bc8cff' }}>Click a node on the map to set as door</p>
                )}
                {editFormData.door_id && (
                  <p className="hint">Selected: {nodes.find(n => n.id === editFormData.door_id)?.name || editFormData.door_id}</p>
                )}
              </div>
              <div className="form-group">
                <label>Level</label>
                <input type="number" value={editFormData.level}
                  onChange={(e) => setEditFormData({ ...editFormData, level: parseInt(e.target.value) || 0 })} />
              </div>
              <div className="form-group">
                <label>Description</label>
                <input type="text" value={editFormData.description}
                  onChange={(e) => setEditFormData({ ...editFormData, description: e.target.value })} />
              </div>
              <div className="form-group">
                <label>Num. Servers</label>
                <input type="number" value={editFormData.num_servers ?? ''}
                  onChange={(e) => setEditFormData({ ...editFormData, num_servers: e.target.value ? parseInt(e.target.value) : null })} />
              </div>
              <div className="form-group">
                <label>Service Rate</label>
                <input type="number" step="0.1" value={editFormData.service_rate ?? ''}
                  onChange={(e) => setEditFormData({ ...editFormData, service_rate: e.target.value ? parseFloat(e.target.value) : null })} />
              </div>
              <div className="form-group">
                <label>Block</label>
                <input type="text" value={editFormData.block}
                  onChange={(e) => setEditFormData({ ...editFormData, block: e.target.value })} />
              </div>
              <div className="form-group">
                <label>Row</label>
                <input type="number" value={editFormData.row ?? ''}
                  onChange={(e) => setEditFormData({ ...editFormData, row: e.target.value ? parseInt(e.target.value) : null })} />
              </div>
              <div className="form-group">
                <label>Number</label>
                <input type="number" value={editFormData.number ?? ''}
                  onChange={(e) => setEditFormData({ ...editFormData, number: e.target.value ? parseInt(e.target.value) : null })} />
              </div>
              <div className="form-group">
                <label>Coordinates</label>
                <div style={{ display: 'flex', gap: '5px' }}>
                  <input type="number" step="any" placeholder="Lat"
                    value={draggedPosition?.lat.toFixed(6) || ''}
                    onChange={(e) => setDraggedPosition({ ...draggedPosition, lat: parseFloat(e.target.value) })} />
                  <input type="number" step="any" placeholder="Lng"
                    value={draggedPosition?.lng.toFixed(6) || ''}
                    onChange={(e) => setDraggedPosition({ ...draggedPosition, lng: parseFloat(e.target.value) })} />
                </div>
                <p className="hint">Drag the red marker to reposition</p>
              </div>
              <div className="button-group">
                <button className="btn-primary" onClick={updateNode}>Save</button>
                <button className="btn-secondary" onClick={cancelEdit}>Cancel</button>
              </div>
            </div>
          )}

          {/* ── Nodes List ────────────────────────────────────────────── */}
          <div className="control-section">
            <h3>Nodes ({filteredNodes.length}/{nodes.length})</h3>
            <div className="form-group">
              <input type="text" placeholder="Search nodes..."
                value={nodeSearchQuery}
                onChange={(e) => setNodeSearchQuery(e.target.value)} />
            </div>
            <ul className="items-list">
              {filteredNodes.map((node) => {
                const isNewNode  = newNodeIds.has(node.id);
                const isSelected = selectedNode?.id === node.id;
                const isEdgePt   = pointsForEdge.from === node.id || pointsForEdge.to === node.id;
                return (
                  <li key={node.id}
                    className={`${isEdgePt ? 'selected' : ''} ${isNewNode ? 'new-node' : ''} ${isSelected ? 'list-selected' : ''}`}
                    onClick={() => selectNode(node)}
                    style={{ cursor: 'pointer' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <strong>{node.name || 'Unnamed'}</strong>
                      {isNewNode && <span className="badge">NEW</span>}
                      <span className="node-type-pill" data-type={node.type || 'normal'}>
                        {node.type || 'normal'}
                      </span>
                    </div>
                    {node.description
                      ? <small style={{ fontStyle: 'italic' }}>{node.description}</small>
                      : <small>{node.y.toFixed(4)}, {node.x.toFixed(4)}</small>
                    }
                  </li>
                );
              })}
            </ul>
          </div>

          {/* ── Edges List ────────────────────────────────────────────── */}
          <div className="control-section">
            <h3>Edges ({filteredEdges.length}/{edges.length})</h3>
            <div className="form-group">
              <input type="text" placeholder="Search edges..."
                value={edgeSearchQuery}
                onChange={(e) => setEdgeSearchQuery(e.target.value)} />
            </div>
            <ul className="items-list edges-list">
              {filteredEdges.map((edge) => {
                const fromNode = nodes.find(n => n.id === edge.from_id);
                const toNode   = nodes.find(n => n.id === edge.to_id);
                const isSel    = selectedEdgeFromList === edge.id;
                return (
                  <li key={edge.id}
                    className={`edge-row ${isSel ? 'list-selected' : ''}`}
                    onClick={() => selectEdge(edge.id)}
                    style={{ cursor: 'pointer' }}>
                    <small style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {fromNode?.name || edge.from_id} → {toNode?.name || edge.to_id}
                    </small>
                    <button className="edge-delete-btn"
                      onClick={(e) => { e.stopPropagation(); deleteEdge(edge.id); }}
                      title="Delete edge">×</button>
                  </li>
                );
              })}
            </ul>
          </div>

        </div>
      </div>
    </div>
  );
}