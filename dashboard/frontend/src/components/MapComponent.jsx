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
  const [showNodeForm, setShowNodeForm] = useState(false);
  const [newNodePosition, setNewNodePosition] = useState(null);
  const [formData, setFormData] = useState({ name: '', type: 'normal' });
  const [creatingEdge, setCreatingEdge] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [newNodeIds, setNewNodeIds] = useState(new Set());
  const [selectedNodeFromList, setSelectedNodeFromList] = useState(null);
  const [selectedEdgeFromList, setSelectedEdgeFromList] = useState(null);
  const [rectangleSelectMode, setRectangleSelectMode] = useState(false);
  const [selectedForDelete, setSelectedForDelete] = useState({ nodes: [], edges: [] });
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

      console.log('========== DEBUG: NODES FROM BACKEND ==========');
      console.log('Raw response:', nodesData);
      console.log('Number of nodes:', nodesData.length);
      if (nodesData.length > 0) {
        console.log('First node:', nodesData[0]);
        console.log('First node fields - id:', nodesData[0].id, 'x:', nodesData[0].x, 'y:', nodesData[0].y);
      }
      console.log('==============================================');

      setNodes(nodesData);
      setEdges(edgesData);
    } catch (err) {
      setError(err.message);
      console.error('Error fetching data:', err);
    } finally {
      setLoading(false);
    }
  };

  // Create a new node
  const createNode = async () => {
    if (!newNodePosition || !formData.name) {
      alert('Please enter a node name');
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/nodes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: `node_${Date.now()}`,
          name: formData.name,
          x: newNodePosition[1],  // longitude (y in Leaflet format)
          y: newNodePosition[0],  // latitude (x in Leaflet format)
          type: formData.type,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to create node');
      }

      await fetchData();
      setShowNodeForm(false);
      setNewNodePosition(null);
      setFormData({ name: '', type: 'normal' });
      // Track this as a new node
      setNewNodeIds(prev => new Set([...prev, `node_${Date.now()}`]));
    } catch (err) {
      setError(err.message);
      console.error('Error creating node:', err);
    }
  };

  // Create an edge between two nodes
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

  // Delete selected nodes and edges
  const deleteSelectedItems = async () => {
    if (selectedForDelete.nodes.length === 0 && selectedForDelete.edges.length === 0) {
      return;
    }

    try {
      // Delete edges first
      for (const edge of selectedForDelete.edges) {
        await fetch(`${API_BASE}/edges/${edge.id}`, { method: 'DELETE' });
      }

      // Delete nodes
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
      console.error('Error deleting:', err);
    }
  };

  // Draw markers and edges on map
  const updateMapView = () => {
    if (!map.current) return;

    // Clear existing markers
    Object.values(markersRef.current).forEach(marker => marker.remove());
    markersRef.current = {};

    // Clear existing edges
    Object.values(edgeLines.current).forEach(line => line.remove());
    edgeLines.current = {};

    // Draw edges first (so they appear behind markers)
    edges.forEach(edge => {
      const fromNode = nodes.find(n => n.id === edge.from_id);
      const toNode = nodes.find(n => n.id === edge.to_id);
      const isEdgeSelected = selectedEdgeFromList === edge.id;

      if (fromNode && toNode) {
        const line = L.polyline(
          [[fromNode.y, fromNode.x], [toNode.y, toNode.x]],
          {
            color: isEdgeSelected ? '#ff6b6b' : 'var(--ifm-color-primary)',
            weight: isEdgeSelected ? 4 : 2,
            opacity: isEdgeSelected ? 1 : 0.7,
          }
        ).addTo(map.current);
        edgeLines.current[edge.id] = line;
      }
    });

    // Draw markers for nodes
    nodes.forEach(node => {
      const isFromNode = pointsForEdge.from === node.id;
      const isToNode = pointsForEdge.to === node.id;
      const isEdgeSelected = isFromNode || isToNode;
      const isListSelected = selectedNodeFromList === node.id;
      const isPartOfSelectedEdge = selectedEdgeFromList && 
        ((edges.find(e => e.id === selectedEdgeFromList)?.from_id === node.id) || 
         (edges.find(e => e.id === selectedEdgeFromList)?.to_id === node.id));
      
      const isNewNode = newNodeIds.has(node.id);
      const matchesSearch = searchQuery === '' || (node.name && node.name.toLowerCase().includes(searchQuery.toLowerCase()));

      // Different colors for new vs backend nodes
      const baseColor = isNewNode ? '#4CAF50' : '#313b84';  // Green for new, blue for backend
      
      let fillColor = baseColor;
      let radius = 7;
      
      if (isListSelected) {
        fillColor = '#ff6b6b';  // Red when selected from list
        radius = 14;  // Bigger
      } else if (isPartOfSelectedEdge) {
        fillColor = '#ff6b6b';  // Red when part of selected edge
        radius = 12;
      } else if (isEdgeSelected) {
        fillColor = '#ffc107';  // Gold when selected for edge
        radius = 10;
      }

      const marker = L.circleMarker([node.y, node.x], {
        radius: radius,
        fill: true,
        fillColor: fillColor,
        fillOpacity: matchesSearch ? 0.9 : 0.4,  // Fade out non-matching results
        stroke: true,
        strokeColor: '#ffffff',
        strokeWeight: 2,
        weight: 2,
        color: fillColor,
      })
        .bindPopup(`<strong>${node.name || 'Node'}</strong><br/>ID: ${node.id}${isNewNode ? '<br/><em>(New)</em>' : ''}`)
        .addTo(map.current);

      marker.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        console.log('Marker clicked. Node ID:', node.id, 'creatingEdge:', creatingEdge);
        
        // Always open the popup
        marker.openPopup();
        
        if (creatingEdge) {
          console.log('Current pointsForEdge:', pointsForEdge);
          if (!pointsForEdge.from) {
            console.log('Setting from node...');
            setPointsForEdge({ ...pointsForEdge, from: node.id });
          } else if (!pointsForEdge.to && node.id !== pointsForEdge.from) {
            console.log('Setting to node...');
            setPointsForEdge({ ...pointsForEdge, to: node.id });
          }
        } else {
          // Allow selecting node from map
          setSelectedNodeFromList(selectedNodeFromList === node.id ? null : node.id);
        }
      });

      markersRef.current[node.id] = marker;
    });

    // Highlight temporary new node position if selecting location
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

  // Initialize map
  useEffect(() => {
    if (map.current) return;

    map.current = L.map(mapContainer.current, {
      maxBounds: AVEIRO_BOUNDS,
      maxBoundsViscosity: 1.0,
      dragging: false,  // Disable default left-click dragging
      touchZoom: true,  // Keep touch zoom
      scrollWheelZoom: true,  // Keep scroll zoom
    }).setView(AVEIRO_CENTER, 16);

    // Disable all dragging handlers
    if (map.current.dragging) {
      map.current.dragging.disable();
    }

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
      maxZoom: 19,
    }).addTo(map.current);

    // Middle mouse button for panning
    let isPanning = false;
    let panStart = null;

    map.current.getContainer().addEventListener('mousedown', (e) => {
      if (e.button === 1) {  // Middle mouse button
        e.preventDefault();
        isPanning = true;
        panStart = { x: e.clientX, y: e.clientY };
        map.current.getContainer().style.cursor = 'grabbing';
      } else if (e.button === 0) {  // Left mouse button - prevent panning
        isPanning = false;
        panStart = null;
      }
    });

    map.current.getContainer().addEventListener('mousemove', (e) => {
      if (isPanning && panStart) {
        e.preventDefault();
        const deltaX = e.clientX - panStart.x;
        const deltaY = e.clientY - panStart.y;
        map.current.panBy([-deltaX, -deltaY], { animate: false });
        panStart = { x: e.clientX, y: e.clientY };
      }
    });

    map.current.getContainer().addEventListener('mouseup', () => {
      isPanning = false;
      panStart = null;
      map.current.getContainer().style.cursor = 'default';
    });

    map.current.getContainer().addEventListener('mouseleave', () => {
      isPanning = false;
      panStart = null;
      map.current.getContainer().style.cursor = 'default';
    });

    // Click to place new node
    map.current.on('click', (e) => {
      if (rectangleSelectMode) return; // Prevent other interactions during rectangle select
      
      console.log('Map clicked. showNodeForm:', showNodeForm, 'newNodePosition:', newNodePosition);
      if (showNodeForm && !newNodePosition) {
        console.log('Setting new node position...');
        setNewNodePosition([e.latlng.lat, e.latlng.lng]);
      }
    });

    // Rectangle select handlers
    map.current.on('mousedown', (e) => {
      if (!rectangleSelectMode) return;
      startCoordsRef.current = e.latlng;
    });

    map.current.on('mousemove', (e) => {
      if (!rectangleSelectMode || !startCoordsRef.current) return;

      // Remove previous rectangle
      if (rectangleRef.current) {
        map.current.removeLayer(rectangleRef.current);
      }

      // Draw new rectangle
      const bounds = L.latLngBounds(startCoordsRef.current, e.latlng);
      rectangleRef.current = L.rectangle(bounds, {
        color: '#ff6b6b',
        weight: 2,
        opacity: 0.3,
        fill: true,
        fillColor: '#ff6b6b',
        fillOpacity: 0.1,
      }).addTo(map.current);
    });

    map.current.on('mouseup', (e) => {
      if (!rectangleSelectMode || !startCoordsRef.current) return;

      const bounds = L.latLngBounds(startCoordsRef.current, e.latlng);

      // Find nodes within bounds
      const nodesInBounds = nodes.filter(node => {
        const latLng = L.latLng(node.y, node.x);
        return bounds.contains(latLng);
      });

      // Find edges within bounds (both nodes must be in bounds)
      const edgesInBounds = edges.filter(edge => {
        const fromInBounds = nodesInBounds.some(n => n.id === edge.from_id);
        const toInBounds = nodesInBounds.some(n => n.id === edge.to_id);
        return fromInBounds && toInBounds;
      });

      setSelectedForDelete({
        nodes: nodesInBounds,
        edges: edgesInBounds,
      });

      startCoordsRef.current = null;
    });

    fetchData();

    return () => {
      if (map.current) {
        map.current.remove();
        map.current = null;
      }
    };
  }, [showNodeForm, newNodePosition]);

  // Auto-fit map to show all nodes
  useEffect(() => {
    if (!map.current || nodes.length === 0) return;

    // Swap x,y to y,x because backend stores x=longitude, y=latitude
    // but Leaflet expects [latitude, longitude]
    const bounds = nodes.map(node => [node.y, node.x]);
    console.log('========== DEBUG: PLOTTING NODES ==========');
    console.log('Total nodes to plot:', nodes.length);
    console.log('Bounds array (should be [lat, lng]):', bounds);
    console.log('Sample bounds[0]:', bounds[0]);
    console.log('=========================================');

    if (bounds.length > 0) {
      try {
        const featureGroup = L.featureGroup(
          bounds.map(coord => L.marker(coord))
        );
        map.current.fitBounds(featureGroup.getBounds(), { padding: [50, 50] });
      } catch (err) {
        console.error('Error fitting bounds:', err);
      }
    }
  }, [nodes]);

  // Update map view whenever edges or selections change
  useEffect(() => {
    if (map.current) {
      updateMapView();
    }
  }, [edges, pointsForEdge, newNodePosition, creatingEdge, nodes, searchQuery, newNodeIds, selectedNodeFromList, selectedEdgeFromList, rectangleSelectMode, selectedForDelete]);

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

        {/* Rectangle Select */}
        <div className="control-section">
          <h3>Bulk Delete</h3>
          {!rectangleSelectMode ? (
            <button 
              className="btn-primary"
              onClick={() => {
                setRectangleSelectMode(true);
                setSelectedForDelete({ nodes: [], edges: [] });
              }}
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

        {/* Nodes List */}
        <div className="control-section">
          <h3>Nodes ({nodes.filter(n => searchQuery === '' || (n.name && n.name.toLowerCase().includes(searchQuery.toLowerCase()))).length}/{nodes.length})</h3>
          <div className="form-group">
            <input
              type="text"
              placeholder="Search nodes..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ marginBottom: '10px' }}
            />
          </div>
          <ul className="items-list">
            {nodes
              .filter(node => searchQuery === '' || (node.name && node.name.toLowerCase().includes(searchQuery.toLowerCase())))
              .map((node) => {
                const isNewNode = newNodeIds.has(node.id);
                const isSelected = selectedNodeFromList === node.id;
                return (
                  <li 
                    key={node.id}
                    className={`${pointsForEdge.from === node.id || pointsForEdge.to === node.id ? 'selected' : ''} ${isNewNode ? 'new-node' : ''} ${isSelected ? 'list-selected' : ''}`}
                    onClick={() => setSelectedNodeFromList(selectedNodeFromList === node.id ? null : node.id)}
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

        {/* Edges List */}
        <div className="control-section">
          <h3>Edges ({edges.length})</h3>
          <ul className="items-list">
            {edges.map((edge) => {
              const fromNode = nodes.find(n => n.id === edge.from_id);
              const toNode = nodes.find(n => n.id === edge.to_id);
              const isSelected = selectedEdgeFromList === edge.id;
              return (
                <li 
                  key={edge.id}
                  className={isSelected ? 'list-selected' : ''}
                  onClick={() => setSelectedEdgeFromList(selectedEdgeFromList === edge.id ? null : edge.id)}
                  style={{ cursor: 'pointer' }}
                >
                  <small>{fromNode?.name || edge.from_id} → {toNode?.name || edge.to_id}</small>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}
