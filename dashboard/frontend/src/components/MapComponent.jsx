import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import 'leaflet-draw/dist/leaflet.draw.css';
import 'leaflet-draw';
import '../styles/MapComponent.css';

export function MapComponent() {

  const mapContainer = useRef(null);
  const map = useRef(null);
  const drawnItems = useRef(new L.FeatureGroup());
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);

  // Map bounds - customize this to your location
  // Format: [[south, west], [north, east]]
  const mapBounds = [
    [51.50, -0.10],  // Southwest corner
    [51.51, -0.08],  // Northeast corner
  ];
  
  // Center and default zoom
  const centerLat = (mapBounds[0][0] + mapBounds[1][0]) / 2;
  const centerLng = (mapBounds[0][1] + mapBounds[1][1]) / 2;

  useEffect(() => {
    if (map.current) return;

    // Initialize map with bounds limiting
    map.current = L.map(mapContainer.current, {
      maxBounds: mapBounds,
      maxBoundsViscosity: 1.0, // Prevent dragging outside bounds
    }).setView([centerLat, centerLng], 16);

    // Add OSM tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
      maxZoom: 19,
    }).addTo(map.current);

    // Add drawn items layer
    map.current.addLayer(drawnItems.current);

    // Initialize Leaflet Draw
    const drawControl = new L.Control.Draw({
      draw: {
        polygon: false,
        polyline: true,
        rectangle: false,
        circle: false,
        marker: true,
      },
      edit: {
        featureGroup: drawnItems.current,
        remove: true,
      },
    });
    map.current.addControl(drawControl);

    // Handle drawn items creation
    map.current.on('draw:created', (e) => {
      const layer = e.layer;
      drawnItems.current.addLayer(layer);

      if (e.layerType === 'marker') {
        const { lat, lng } = layer.getLatLng();
        const newNode = {
          id: Date.now(),
          lat,
          lng,
          label: `Node ${nodes.length + 1}`,
        };
        setNodes([...nodes, newNode]);
        console.log('Node created:', newNode);
      } else if (e.layerType === 'polyline') {
        const latlngs = layer.getLatLngs();
        const newEdge = {
          id: Date.now(),
          from: latlngs[0],
          to: latlngs[1],
        };
        setEdges([...edges, newEdge]);
        console.log('Edge created:', newEdge);
      }
    });

    // Handle item editing
    map.current.on('draw:edited', (e) => {
      e.layers.eachLayer((layer) => {
        if (layer instanceof L.Marker) {
          const { lat, lng } = layer.getLatLng();
          setNodes(
            nodes.map((node) =>
              node.id === layer._leaflet_id ? { ...node, lat, lng } : node
            )
          );
          console.log('Node updated:', lat, lng);
        }
      });
    });

    // Handle item deletion
    map.current.on('draw:deleted', (e) => {
      e.layers.eachLayer((layer) => {
        if (layer instanceof L.Marker) {
          setNodes(nodes.filter((node) => node.id !== layer._leaflet_id));
        }
      });
    });

    return () => {
      if (map.current) {
        map.current.remove();
        map.current = null;
      }
    };
  }, [nodes, edges]);

  return (
    <div className="map-container">
      <div ref={mapContainer} className="map" />
      <div className="map-sidebar">
        <h3>Nodes</h3>
        <ul>
          {nodes.map((node) => (
            <li key={node.id}>
              {node.label} - ({node.lat.toFixed(4)}, {node.lng.toFixed(4)})
            </li>
          ))}
        </ul>
        <h3>Edges</h3>
        <ul>
          {edges.map((edge) => (
            <li key={edge.id}>
              Edge - {edges.indexOf(edge) + 1}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
