import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import '../styles/MapComponent.css';

const API_BASE = 'http://localhost:8001';

// Aveiro University bounds (lat/lng)
const AVEIRO_BOUNDS = [
  [40.628, -8.662],  // Southwest
  [40.635, -8.654],  // Northeast
];

const AVEIRO_CENTER = [
  (40.628 + 40.635) / 2,
  (-8.662 + -8.654) / 2,
];

export function MapComponent() {
  const mapContainer = useRef(null);
  const map = useRef(null);
  const markersRef = useRef({});
  const edgeLines = useRef({});
  const [pointsForEdge, setPointsForEdge] = useState({ from: null, to: null });

  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [editingNode, setEditingNode] = useState(null);
  const [showNodeForm, setShowNodeForm] = useState(false);
  const [newNodePosition, setNewNodePosition] = useState(null);
  const [formData, setFormData] = useState({ name: '', type: 'normal' });
  const [creatingEdge, setCreatingEdge] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [nodeSearchQuery, setNodeSearchQuery] = useState('');
  const [edgeSearchQuery, setEdgeSearchQuery] = useState('');
  const [newNodeIds, setNewNodeIds] = useState(new Set());
  const [selectedNode, setSelectedNode] = useState(null);
  const [selectedEdgeFromList, setSelectedEdgeFromList] = useState(null);
  const [rectangleSelectMode, setRectangleSelectMode] = useState(false);
  const [selectedForDelete, setSelectedForDelete] = useState({ nodes: [], edges: [] });
  const [editFormData, setEditFormData] = useState({
    name: '',
    type: 'normal',
    level: 0,
    description: '',
    num_servers: null,
    service_rate: null,
    block: '',
    row: null,
    number: null,
    x: 0,
    y: 0,
  });
  const [draggedPosition, setDraggedPosition] = useState(null);
  const rectangleRef = useRef(null);
  const startCoordsRef = useRef(null);

  // Fetch nodes and edges from backend
  const fetchData = async () => {
    try {
      setLoading(true);
      const [nodesRes, edgesRes] = await Promise.all([
        fetch(`${API_BASE}/nodes`),
        fetch(`${API_BASE}/edges`),
      ]);

      if (!nodesRes.ok || !edgesRes.ok) {
        throw new Error('Failed to fetch data');
      }

      const nodesData = await nodesRes.json();
      const edgesData = await edgesRes.json();

      setNodes(nodesData);
      setEdges(edgesData);
    } catch (err) {
      setError(err.message);
      console.error('Error fetching data:', err);
    } finally {
      setLoading(false);
    }
  };

  // Selecionar um node para ver detalhes
  const selectNode = (node) => {
    if (creatingEdge) return; // não interfere com criação de aresta
    setSelectedNode(node);
    if (editingNode) setEditingNode(null); // sai do modo edição se estiver
  };

  // Iniciar edição
  const startEditNode = (node) => {
    setEditingNode(node.id);
    setEditFormData({
      name: node.name || '',
      type: node.type || 'normal',
      level: node.level || 0,
      description: node.description || '',
      num_servers: node.num_servers || null,
      service_rate: node.service_rate || null,
      block: node.block || '',
      row: node.row || null,
      number: node.number || null,
      x: node.x,
      y: node.y,
    });
    setDraggedPosition({ lat: node.y, lng: node.x });
    if (map.current) {
      map.current.setView([node.y, node.x], map.current.getZoom());
    }
  };

  // Atualizar node
  const updateNode = async () => {
    if (!editingNode || !draggedPosition) return;
    try {
      const response = await fetch(`${API_BASE}/nodes/${editingNode}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...editFormData,
          x: draggedPosition.lng,
          y: draggedPosition.lat,
        }),
      });
      if (!response.ok) throw new Error('Failed to update node');
      await fetchData();
      setEditingNode(null);
      setDraggedPosition(null);
      setSelectedNode(null);
    } catch (err) {
      setError(err.message);
    }
  };

  const cancelEdit = () => {
    setEditingNode(null);
    setDraggedPosition(null);
  };

  // Apagar node (usado no painel de detalhes)
  const deleteNode = async (nodeId) => {
    if (!confirm('Tem a certeza que pretende eliminar este node? As arestas ligadas também serão apagadas.')) return;
    try {
      await fetch(`${API_BASE}/nodes/${nodeId}`, { method: 'DELETE' });
      await fetchData();
      setSelectedNode(null);
    } catch (err) {
      setError(err.message);
    }
  };

  // Apagar edge
  const deleteEdge = async (edgeId) => {
    if (!confirm('Tem a certeza que pretende eliminar esta aresta?')) return;
    try {
      await fetch(`${API_BASE}/edges/${edgeId}`, { method: 'DELETE' });
      await fetchData();
    } catch (err) {
      setError(err.message);
    }
  };

  // Criar node
  const createNode = async () => {
    if (!newNodePosition || !formData.name) {
      alert('Please enter a node name');
      return;
    }

    const newId = `node_${Date.now()}`;
    try {
      const response = await fetch(`${API_BASE}/nodes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: newId,
          name: formData.name,
          x: newNodePosition[1],
          y: newNodePosition[0],
          type: formData.type,
          level: 0,
          description: '',
          num_servers: null,
          service_rate: null,
          block: '',
          row: null,
          number: null,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to create node');
      }

      await fetchData();
      setShowNodeForm(false);
      setNewNodePosition(null);
      setFormData({ name: '', type: 'normal' });
      setNewNodeIds(prev => new Set([...prev, newId]));
    } catch (err) {
      setError(err.message);
      console.error('Error creating node:', err);
    }
  };

  // Criar aresta
  const createEdge = async () => {
    if (!pointsForEdge.from || !pointsForEdge.to) {
      alert('Please select two nodes');
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/edges`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: `edge_${Date.now()}`,
          from_id: pointsForEdge.from,
          to_id: pointsForEdge.to,
          weight: 1.0,
          accessible: true,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to create edge');
      }

      await fetchData();
      setPointsForEdge({ from: null, to: null });
      setCreatingEdge(false);
    } catch (err) {
      setError(err.message);
      console.error('Error creating edge:', err);
    }
  };

  // Bulk delete
  const deleteSelectedItems = async () => {
    if (selectedForDelete.nodes.length === 0 && selectedForDelete.edges.length === 0) return;

    try {
      for (const edge of selectedForDelete.edges) {
        await fetch(`${API_BASE}/edges/${edge.id}`, { method: 'DELETE' });
      }
      for (const node of selectedForDelete.nodes) {
        await fetch(`${API_BASE}/nodes/${node.id}`, { method: 'DELETE' });
      }

      await fetchData();
      setSelectedForDelete({ nodes: [], edges: [] });
      setRectangleSelectMode(false);
      if (rectangleRef.current) {
        map.current.removeLayer(rectangleRef.current);
        rectangleRef.current = null;
      }
    } catch (err) {
      setError(`Error deleting items: ${err.message}`);
    }
  };

  // Desenhar mapa
  const updateMapView = () => {
    if (!map.current) return;

    Object.values(markersRef.current).forEach(marker => marker.remove());
    markersRef.current = {};
    Object.values(edgeLines.current).forEach(line => line.remove());
    edgeLines.current = {};

    // Desenhar arestas
    edges.forEach(edge => {
      const fromNode = nodes.find(n => n.id === edge.from_id);
      const toNode = nodes.find(n => n.id === edge.to_id);
      const isEdgeSelected = selectedEdgeFromList === edge.id;
      const isInDeleteSelection = selectedForDelete.edges.some(e => e.id === edge.id);

      if (fromNode && toNode) {
        let color = 'var(--ifm-color-primary)';
        if (isEdgeSelected) color = '#ff6b6b';
        if (isInDeleteSelection) color = '#ffa500';

        const line = L.polyline(
          [[fromNode.y, fromNode.x], [toNode.y, toNode.x]],
          {
            color: color,
            weight: isEdgeSelected || isInDeleteSelection ? 4 : 2,
            opacity: 0.7,
          }
        ).addTo(map.current);
        edgeLines.current[edge.id] = line;
      }
    });

    // Desenhar nodes
    nodes.forEach(node => {
      const isFromNode = pointsForEdge.from === node.id;
      const isToNode = pointsForEdge.to === node.id;
      const isEdgeSelected = isFromNode || isToNode;
      const isListSelected = selectedNode?.id === node.id;
      const isPartOfSelectedEdge = selectedEdgeFromList &&
        ((edges.find(e => e.id === selectedEdgeFromList)?.from_id === node.id) ||
         (edges.find(e => e.id === selectedEdgeFromList)?.to_id === node.id));
      const isNewNode = newNodeIds.has(node.id);
      const matchesSearch = nodeSearchQuery === '' || (node.name && node.name.toLowerCase().includes(nodeSearchQuery.toLowerCase()));
      const isInDeleteSelection = selectedForDelete.nodes.some(n => n.id === node.id);

      const baseColor = isNewNode ? '#4CAF50' : '#313b84';
      let fillColor = baseColor;
      let radius = 7;

      if (isInDeleteSelection) {
        fillColor = '#ffa500';
        radius = 10;
      } else if (isListSelected) {
        fillColor = '#ff6b6b';
        radius = 14;
      } else if (isPartOfSelectedEdge) {
        fillColor = '#ff6b6b';
        radius = 12;
      } else if (isEdgeSelected) {
        fillColor = '#ffc107';
        radius = 10;
      }

      let marker;

      if (node.id === editingNode && draggedPosition) {
        marker = L.marker([draggedPosition.lat, draggedPosition.lng], {
          draggable: true,
          icon: L.divIcon({
            className: 'editing-marker',
            html: '<div style="background-color: #ff6b6b; width: 24px; height: 24px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 10px rgba(255,107,107,0.5);"></div>',
            iconSize: [24, 24],
            iconAnchor: [12, 12],
          })
        }).addTo(map.current);

        marker.on('drag', (e) => {
          const pos = e.target.getLatLng();
          setDraggedPosition({ lat: pos.lat, lng: pos.lng });
        });

        marker.on('dragend', (e) => {
          const pos = e.target.getLatLng();
          setDraggedPosition({ lat: pos.lat, lng: pos.lng });
        });

        marker.bindPopup(`<strong>A editar: ${node.name || node.id}</strong><br/>Arraste para mover`);
      } else {
        marker = L.circleMarker([node.y, node.x], {
          radius: radius,
          fill: true,
          fillColor: fillColor,
          fillOpacity: matchesSearch ? 0.9 : 0.4,
          stroke: true,
          strokeColor: '#ffffff',
          weight: 2,
          color: fillColor,
        }).addTo(map.current);

        marker.bindPopup(`
          <strong>${node.name || 'Unnamed'}</strong><br/>
          ID: ${node.id}<br/>
          Tipo: ${node.type || 'normal'}<br/>
          Coordenadas:<br/>
          Lat: ${node.y.toFixed(6)}<br/>
          Lng: ${node.x.toFixed(6)}<br/>
          ${isNewNode ? '<em>Novo</em>' : ''}
        `);
      }

      marker.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        marker.openPopup();

        if (creatingEdge) {
          if (!pointsForEdge.from) {
            setPointsForEdge({ ...pointsForEdge, from: node.id });
          } else if (!pointsForEdge.to && node.id !== pointsForEdge.from) {
            setPointsForEdge({ ...pointsForEdge, to: node.id });
          }
        } else {
          selectNode(node);
        }
      });

      markersRef.current[node.id] = marker;
    });

    // Marcador temporário para novo node
    if (newNodePosition) {
      L.circleMarker(newNodePosition, {
        radius: 8,
        fill: true,
        fillColor: '#4CAF50',
        fillOpacity: 0.8,
        stroke: true,
        strokeColor: '#ffffff',
        weight: 2,
      }).addTo(map.current);
    }
  };

  // Inicializar mapa
  useEffect(() => {
    if (map.current) return;

    map.current = L.map(mapContainer.current, {
      maxBounds: AVEIRO_BOUNDS,
      maxBoundsViscosity: 1.0,
      dragging: false,
      touchZoom: true,
      scrollWheelZoom: true,
    }).setView(AVEIRO_CENTER, 16);

    if (map.current.dragging) {
      map.current.dragging.disable();
    }

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
      maxZoom: 19,
    }).addTo(map.current);

    let isPanning = false;
    let panStart = null;
    const container = map.current.getContainer();

    container.addEventListener('mousedown', (e) => {
      if (e.button === 1) {
        e.preventDefault();
        isPanning = true;
        panStart = { x: e.clientX, y: e.clientY };
        container.style.cursor = 'grabbing';
      } else if (e.button === 0) {
        isPanning = false;
        panStart = null;
      }
    });

    container.addEventListener('mousemove', (e) => {
      if (isPanning && panStart) {
        e.preventDefault();
        const deltaX = e.clientX - panStart.x;
        const deltaY = e.clientY - panStart.y;
        map.current.panBy([-deltaX, -deltaY], { animate: false });
        panStart = { x: e.clientX, y: e.clientY };
      }
    });

    container.addEventListener('mouseup', () => {
      isPanning = false;
      panStart = null;
      container.style.cursor = 'default';
    });

    container.addEventListener('mouseleave', () => {
      isPanning = false;
      panStart = null;
      container.style.cursor = 'default';
    });

    fetchData();

    return () => {
      if (map.current) {
        map.current.remove();
        map.current = null;
      }
    };
  }, []);

  // Listeners de eventos que dependem de estado
  useEffect(() => {
    if (!map.current) return;

    const handleMapClick = (e) => {
      if (rectangleSelectMode) return;
      if (showNodeForm && !newNodePosition) {
        setNewNodePosition([e.latlng.lat, e.latlng.lng]);
      }
    };

    const handleMouseDown = (e) => {
      if (!rectangleSelectMode) return;
      startCoordsRef.current = e.latlng;
    };

    const handleMouseMove = (e) => {
      if (!rectangleSelectMode || !startCoordsRef.current) return;
      if (rectangleRef.current) map.current.removeLayer(rectangleRef.current);
      const bounds = L.latLngBounds(startCoordsRef.current, e.latlng);
      rectangleRef.current = L.rectangle(bounds, {
        color: '#ff6b6b',
        weight: 2,
        opacity: 0.3,
        fill: true,
        fillColor: '#ff6b6b',
        fillOpacity: 0.1,
      }).addTo(map.current);
    };

    const handleMouseUp = (e) => {
      if (!rectangleSelectMode || !startCoordsRef.current) return;
      const bounds = L.latLngBounds(startCoordsRef.current, e.latlng);
      const nodesInBounds = nodes.filter(node => {
        const latLng = L.latLng(node.y, node.x);
        return bounds.contains(latLng);
      });
      const edgesInBounds = edges.filter(edge => {
        const fromInBounds = nodesInBounds.some(n => n.id === edge.from_id);
        const toInBounds = nodesInBounds.some(n => n.id === edge.to_id);
        return fromInBounds && toInBounds;
      });
      setSelectedForDelete({ nodes: nodesInBounds, edges: edgesInBounds });
      startCoordsRef.current = null;
    };

    map.current.on('click', handleMapClick);
    map.current.on('mousedown', handleMouseDown);
    map.current.on('mousemove', handleMouseMove);
    map.current.on('mouseup', handleMouseUp);

    return () => {
      if (map.current) {
        map.current.off('click', handleMapClick);
        map.current.off('mousedown', handleMouseDown);
        map.current.off('mousemove', handleMouseMove);
        map.current.off('mouseup', handleMouseUp);
      }
    };
  }, [showNodeForm, newNodePosition, rectangleSelectMode, nodes, edges]);

  // Ajustar zoom para mostrar todos os nodes
  useEffect(() => {
    if (!map.current || nodes.length === 0) return;
    const bounds = nodes.map(node => [node.y, node.x]);
    if (bounds.length > 0) {
      try {
        const featureGroup = L.featureGroup(bounds.map(coord => L.marker(coord)));
        map.current.fitBounds(featureGroup.getBounds(), { padding: [50, 50] });
      } catch (err) {
        console.error('Error fitting bounds:', err);
      }
    }
  }, [nodes]);

  // Atualizar vista quando dados mudam
  useEffect(() => {
    if (map.current) {
      updateMapView();
    }
  }, [nodes, edges, pointsForEdge, newNodePosition, selectedNode, selectedEdgeFromList, selectedForDelete, nodeSearchQuery, creatingEdge, editingNode, draggedPosition]);

  return (
    <div className="map-container">
      <div ref={mapContainer} className="map" />

      <div className="map-sidebar">
        <h2>Map Editor</h2>

        <div className="hint" style={{ marginBottom: '12px', padding: '8px', backgroundColor: '#1e2a5f', borderLeft: '3px solid #5562c3' }}>
          <strong>💡 Pan Map:</strong> Hold middle mouse button to move the map
        </div>

        {error && <div className="error-message">{error}</div>}
        {loading && <div className="loading">Loading...</div>}

        {/* Indicadores de modo */}
        {creatingEdge && (
          <div className="hint" style={{ backgroundColor: '#ffc107', color: '#000', marginBottom: '10px' }}>
            Modo: Criar aresta. Clique em dois nós para conectar.
          </div>
        )}
        {rectangleSelectMode && (
          <div className="hint" style={{ backgroundColor: '#dc3545', color: '#fff', marginBottom: '10px' }}>
            Modo: Seleção retangular. Arraste no mapa para selecionar.
          </div>
        )}

        {/* Node Creation */}
        <div className="control-section">
          <h3>Add Node</h3>
          {!showNodeForm ? (
            <button
              className="btn-primary"
              onClick={() => {
                setShowNodeForm(true);
                setNewNodePosition(null);
              }}
              disabled={creatingEdge || rectangleSelectMode}
            >
              + Add Node
            </button>
          ) : (
            <>
              <div className="form-group">
                <label>Node Name:</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="Enter node name"
                />
              </div>
              <div className="form-group">
                <label>Type:</label>
                <select
                  value={formData.type}
                  onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                >
                  <option value="normal">Normal</option>
                  <option value="corridor">Corridor</option>
                  <option value="stairs">Stairs</option>
                  <option value="exit">Exit</option>
                </select>
              </div>
              <p className="hint">
                {newNodePosition ? `Position set: (${newNodePosition[0].toFixed(4)}, ${newNodePosition[1].toFixed(4)})` : 'Click on map to set position'}
              </p>
              <div className="button-group">
                <button
                  className="btn-primary"
                  onClick={createNode}
                  disabled={!newNodePosition}
                >
                  Create
                </button>
                <button
                  className="btn-secondary"
                  onClick={() => {
                    setShowNodeForm(false);
                    setNewNodePosition(null);
                    setFormData({ name: '', type: 'normal' });
                  }}
                >
                  Cancel
                </button>
              </div>
            </>
          )}
        </div>

        {/* Bulk Delete */}
        <div className="control-section">
          <h3>Bulk Delete</h3>
          {!rectangleSelectMode ? (
            <button
              className="btn-primary"
              onClick={() => {
                setRectangleSelectMode(true);
                setSelectedForDelete({ nodes: [], edges: [] });
              }}
              disabled={creatingEdge || showNodeForm}
            >
              📦 Rectangle Select
            </button>
          ) : (
            <>
              <p className="hint">Drag on the map to select nodes and edges</p>
              {selectedForDelete.nodes.length > 0 || selectedForDelete.edges.length > 0 ? (
                <>
                  <p style={{ color: '#ffc107', fontWeight: 'bold' }}>
                    Selected: {selectedForDelete.nodes.length} nodes, {selectedForDelete.edges.length} edges
                  </p>
                  <div className="button-group">
                    <button
                      className="btn-primary"
                      style={{ backgroundColor: '#dc3545' }}
                      onClick={deleteSelectedItems}
                    >
                      🗑️ Delete All
                    </button>
                    <button
                      className="btn-secondary"
                      onClick={() => {
                        setRectangleSelectMode(false);
                        setSelectedForDelete({ nodes: [], edges: [] });
                        if (rectangleRef.current) {
                          map.current.removeLayer(rectangleRef.current);
                          rectangleRef.current = null;
                        }
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <button
                  className="btn-secondary"
                  onClick={() => {
                    setRectangleSelectMode(false);
                    setSelectedForDelete({ nodes: [], edges: [] });
                    if (rectangleRef.current) {
                      map.current.removeLayer(rectangleRef.current);
                      rectangleRef.current = null;
                    }
                  }}
                >
                  Cancel
                </button>
              )}
            </>
          )}
        </div>

        {/* Edge Creation */}
        <div className="control-section">
          <h3>Connect Nodes</h3>
          {!creatingEdge ? (
            <button
              className="btn-primary"
              onClick={() => setCreatingEdge(true)}
              disabled={showNodeForm || rectangleSelectMode}
            >
              + Create Edge
            </button>
          ) : (
            <>
              <p className="hint">Click two nodes to connect them</p>
              {pointsForEdge.from && (
                <p className="selected-nodes">From: {pointsForEdge.from}</p>
              )}
              {pointsForEdge.to && (
                <p className="selected-nodes">To: {pointsForEdge.to}</p>
              )}
              <div className="button-group">
                <button
                  className="btn-primary"
                  onClick={createEdge}
                  disabled={!pointsForEdge.from || !pointsForEdge.to}
                >
                  Create Edge
                </button>
                <button
                  className="btn-secondary"
                  onClick={() => {
                    setCreatingEdge(false);
                    setPointsForEdge({ from: null, to: null });
                  }}
                >
                  Cancel
                </button>
              </div>
            </>
          )}
        </div>

        {/* Node Details / Edit Panel */}
        {selectedNode && !editingNode && (
          <div className="control-section">
            <h3>Node Details</h3>
            <div className="form-group">
              <label>ID:</label>
              <div>{selectedNode.id}</div>
            </div>
            <div className="form-group">
              <label>Name:</label>
              <div>{selectedNode.name || '-'}</div>
            </div>
            <div className="form-group">
              <label>Type:</label>
              <div>{selectedNode.type}</div>
            </div>
            <div className="form-group">
              <label>Level:</label>
              <div>{selectedNode.level}</div>
            </div>
            <div className="form-group">
              <label>Description:</label>
              <div>{selectedNode.description || '-'}</div>
            </div>
            <div className="form-group">
              <label>Num Servers:</label>
              <div>{selectedNode.num_servers ?? '-'}</div>
            </div>
            <div className="form-group">
              <label>Service Rate:</label>
              <div>{selectedNode.service_rate ?? '-'}</div>
            </div>
            <div className="form-group">
              <label>Block:</label>
              <div>{selectedNode.block || '-'}</div>
            </div>
            <div className="form-group">
              <label>Row:</label>
              <div>{selectedNode.row ?? '-'}</div>
            </div>
            <div className="form-group">
              <label>Number:</label>
              <div>{selectedNode.number ?? '-'}</div>
            </div>
            <div className="form-group">
              <label>Coordinates:</label>
              <div>Lat: {selectedNode.y.toFixed(6)}, Lng: {selectedNode.x.toFixed(6)}</div>
            </div>
            <div className="button-group">
              <button className="btn-primary" onClick={() => startEditNode(selectedNode)}>
                ✏️ Edit
              </button>
              <button className="btn-danger" onClick={() => deleteNode(selectedNode.id)} style={{ backgroundColor: '#dc3545' }}>
                🗑️ Delete
              </button>
              <button className="btn-secondary" onClick={() => setSelectedNode(null)}>
                Close
              </button>
            </div>
          </div>
        )}

        {/* Edit Node Form */}
        {editingNode && (
          <div className="control-section">
            <h3>Edit Node</h3>
            <div className="form-group">
              <label>Name:</label>
              <input
                type="text"
                value={editFormData.name}
                onChange={(e) => setEditFormData({ ...editFormData, name: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label>Type:</label>
              <select
                value={editFormData.type}
                onChange={(e) => setEditFormData({ ...editFormData, type: e.target.value })}
              >
                <option value="normal">Normal</option>
                <option value="corridor">Corridor</option>
                <option value="stairs">Stairs</option>
                <option value="exit">Exit</option>
              </select>
            </div>
            <div className="form-group">
              <label>Level:</label>
              <input
                type="number"
                value={editFormData.level}
                onChange={(e) => setEditFormData({ ...editFormData, level: parseInt(e.target.value) || 0 })}
              />
            </div>
            <div className="form-group">
              <label>Description:</label>
              <input
                type="text"
                value={editFormData.description}
                onChange={(e) => setEditFormData({ ...editFormData, description: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label>Num Servers:</label>
              <input
                type="number"
                value={editFormData.num_servers ?? ''}
                onChange={(e) => setEditFormData({ ...editFormData, num_servers: e.target.value ? parseInt(e.target.value) : null })}
              />
            </div>
            <div className="form-group">
              <label>Service Rate:</label>
              <input
                type="number"
                step="0.1"
                value={editFormData.service_rate ?? ''}
                onChange={(e) => setEditFormData({ ...editFormData, service_rate: e.target.value ? parseFloat(e.target.value) : null })}
              />
            </div>
            <div className="form-group">
              <label>Block:</label>
              <input
                type="text"
                value={editFormData.block}
                onChange={(e) => setEditFormData({ ...editFormData, block: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label>Row:</label>
              <input
                type="number"
                value={editFormData.row ?? ''}
                onChange={(e) => setEditFormData({ ...editFormData, row: e.target.value ? parseInt(e.target.value) : null })}
              />
            </div>
            <div className="form-group">
              <label>Number:</label>
              <input
                type="number"
                value={editFormData.number ?? ''}
                onChange={(e) => setEditFormData({ ...editFormData, number: e.target.value ? parseInt(e.target.value) : null })}
              />
            </div>
            <div className="form-group">
              <label>Coordinates:</label>
              <div style={{ display: 'flex', gap: '5px' }}>
                <input
                  type="number"
                  step="any"
                  placeholder="Lat"
                  value={draggedPosition?.lat.toFixed(6) || ''}
                  onChange={(e) => setDraggedPosition({ ...draggedPosition, lat: parseFloat(e.target.value) })}
                />
                <input
                  type="number"
                  step="any"
                  placeholder="Lng"
                  value={draggedPosition?.lng.toFixed(6) || ''}
                  onChange={(e) => setDraggedPosition({ ...draggedPosition, lng: parseFloat(e.target.value) })}
                />
              </div>
              <p className="hint">Drag the red marker on map to adjust position</p>
            </div>
            <div className="button-group">
              <button className="btn-primary" onClick={updateNode}>Save</button>
              <button className="btn-secondary" onClick={cancelEdit}>Cancel</button>
            </div>
          </div>
        )}

        {/* Nodes List com pesquisa */}
        <div className="control-section">
          <h3>Nodes ({nodes.filter(n => nodeSearchQuery === '' || (n.name && n.name.toLowerCase().includes(nodeSearchQuery.toLowerCase()))).length}/{nodes.length})</h3>
          <div className="form-group">
            <input
              type="text"
              placeholder="Search nodes..."
              value={nodeSearchQuery}
              onChange={(e) => setNodeSearchQuery(e.target.value)}
              style={{ marginBottom: '10px' }}
            />
          </div>
          <ul className="items-list">
            {nodes
              .filter(node => nodeSearchQuery === '' || (node.name && node.name.toLowerCase().includes(nodeSearchQuery.toLowerCase())))
              .map((node) => {
                const isNewNode = newNodeIds.has(node.id);
                const isSelected = selectedNode?.id === node.id;
                return (
                  <li
                    key={node.id}
                    className={`${pointsForEdge.from === node.id || pointsForEdge.to === node.id ? 'selected' : ''} ${isNewNode ? 'new-node' : ''} ${isSelected ? 'list-selected' : ''}`}
                    onClick={() => selectNode(node)}
                    style={{ cursor: 'pointer' }}
                  >
                    <strong>{node.name || 'Unnamed'}</strong>
                    {isNewNode && <span className="badge">NEW</span>}
                    <small>{node.id}</small>
                    <tiny>({node.y.toFixed(4)}, {node.x.toFixed(4)})</tiny>
                  </li>
                );
              })}
          </ul>
        </div>

        {/* Edges List com pesquisa */}
        <div className="control-section">
          <h3>Edges ({edges.filter(edge => {
            const fromNode = nodes.find(n => n.id === edge.from_id);
            const toNode = nodes.find(n => n.id === edge.to_id);
            const searchLower = edgeSearchQuery.toLowerCase();
            return edgeSearchQuery === '' ||
              edge.id.toLowerCase().includes(searchLower) ||
              (fromNode?.name && fromNode.name.toLowerCase().includes(searchLower)) ||
              (toNode?.name && toNode.name.toLowerCase().includes(searchLower)) ||
              edge.from_id.toLowerCase().includes(searchLower) ||
              edge.to_id.toLowerCase().includes(searchLower);
          }).length}/{edges.length})</h3>
          <div className="form-group">
            <input
              type="text"
              placeholder="Search edges..."
              value={edgeSearchQuery}
              onChange={(e) => setEdgeSearchQuery(e.target.value)}
              style={{ marginBottom: '10px' }}
            />
          </div>
          <ul className="items-list">
            {edges
              .filter(edge => {
                const fromNode = nodes.find(n => n.id === edge.from_id);
                const toNode = nodes.find(n => n.id === edge.to_id);
                const searchLower = edgeSearchQuery.toLowerCase();
                return edgeSearchQuery === '' ||
                  edge.id.toLowerCase().includes(searchLower) ||
                  (fromNode?.name && fromNode.name.toLowerCase().includes(searchLower)) ||
                  (toNode?.name && toNode.name.toLowerCase().includes(searchLower)) ||
                  edge.from_id.toLowerCase().includes(searchLower) ||
                  edge.to_id.toLowerCase().includes(searchLower);
              })
              .map((edge) => {
                const fromNode = nodes.find(n => n.id === edge.from_id);
                const toNode = nodes.find(n => n.id === edge.to_id);
                const isSelected = selectedEdgeFromList === edge.id;
                return (
                  <li
                    key={edge.id}
                    className={isSelected ? 'list-selected' : ''}
                    style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
                  >
                    <span onClick={() => setSelectedEdgeFromList(selectedEdgeFromList === edge.id ? null : edge.id)}>
                      <small>{fromNode?.name || edge.from_id} → {toNode?.name || edge.to_id}</small>
                    </span>
                    <button
                      onClick={(e) => { e.stopPropagation(); deleteEdge(edge.id); }}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px', marginLeft: '8px' }}
                      title="Delete edge"
                    >
                      🗑️
                    </button>
                  </li>
                );
              })}
          </ul>
        </div>
      </div>
    </div>
  );
}