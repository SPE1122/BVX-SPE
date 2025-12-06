"""
BVX Auswertung - Streamlit Version
Eine Web-Anwendung zur Analyse von BVX (CAD/CAM) Dateien von Hundegger CNC-Holzbearbeitungsmaschinen.

Installation:
    pip install streamlit pandas plotly openpyxl

Ausführen:
    streamlit run bvx_auswertung_streamlit.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import math
import io
from dataclasses import dataclass
from typing import Optional, List, Dict
from collections import Counter


@dataclass
class Operation:
    op_type: str
    diameter: Optional[float] = None
    length: Optional[float] = None
    depth: Optional[float] = None
    volume: float = 0.0
    count: int = 1
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    production_state: Optional[str] = None
    plunge_type: Optional[str] = None


@dataclass
class Part:
    name: str
    length: float = 0.0
    width: float = 0.0
    height: float = 0.0


@dataclass
class AnalysisResult:
    file_name: str
    part_count: int
    operation_count: int
    total_operation_count: int
    total_volume: float
    machined_volume: float
    operations: List[Operation]
    parts: List[Part]
    part_dimensions: Optional[Dict[str, float]] = None


class BVXParser:
    """Parser für BVX-Dateien (XML und Text-Format)"""
    
    OPERATION_TYPES = [
        'Drilling', 'SawCut', 'Slot', 'Step', 'Pocket', 'BlindSlot', 'BlindStep',
        'Mill', 'Countersink', 'Thread', 'FrameBox', 'BirdsMouth', 'Mortise',
        'Tenon', 'Notch', 'Rabbet', 'Chamfer', 'Groove', 'Dado', 'LapJoint',
        'DovetailJoint', 'FingerJoint', 'ScarfJoint', 'HalfLap', 'CrossLap',
        'LowerBoomSingleStepJoint', 'CADPosition', 'CADPositionList', 'Kappen'
    ]
    
    def parse(self, file_content: str, file_name: str = "uploaded.bvx") -> AnalysisResult:
        """Analysiert BVX-Dateiinhalt und gibt Analyseergebnis zurück"""
        if file_content.strip().startswith('<?xml'):
            return self._parse_xml_format(file_content, file_name)
        else:
            return self._parse_text_format(file_content, file_name)
    
    def _extract_xml_attribute(self, tag: str, attr_name: str) -> Optional[str]:
        """Extrahiert XML-Attributwert aus Tag"""
        pattern = rf'{attr_name}="([^"]*)"'
        match = re.search(pattern, tag, re.IGNORECASE)
        return match.group(1) if match else None
    
    def _parse_xml_format(self, file_content: str, file_name: str) -> AnalysisResult:
        """Parst XML-Format BVX-Dateien"""
        parts: List[Part] = []
        operations: List[Dict] = []
        
        # Parse RectangularPart sections
        part_sections = re.findall(r'<RectangularPart[^>]*>([\s\S]*?)</RectangularPart>', file_content)
        part_tags_content = re.findall(r'<RectangularPart([^>]*)>', file_content)
        
        for i, (attrs, content) in enumerate(zip(part_tags_content, part_sections) if part_sections else []):
            full_tag = f'<RectangularPart{attrs}>'
            name = self._extract_xml_attribute(full_tag, 'Name') or f'Bauteil_{i+1}'
            dim_x = float(self._extract_xml_attribute(full_tag, 'DimensionX') or '0')
            dim_y = float(self._extract_xml_attribute(full_tag, 'DimensionY') or '0')
            dim_z = float(self._extract_xml_attribute(full_tag, 'DimensionZ') or '0')
            
            parts.append(Part(name=name, length=dim_x, width=dim_y, height=dim_z))
            
            # Parse operations within part
            op_pattern = '|'.join(self.OPERATION_TYPES)
            
            # Self-closing tags
            self_closing = re.findall(rf'<({op_pattern})\s+([^>]*)/>', content)
            # Tags with content
            content_tags = re.findall(rf'<({op_pattern})\s+([^>]*)>[\s\S]*?</\1>', content)
            
            for op_type, attrs in self_closing + content_tags:
                op = self._parse_operation(op_type, f'<{op_type} {attrs}>')
                operations.append(op)
            
            # Add Kappen operations (2 per part)
            blade_thickness = 6
            operations.append({
                'type': 'Kappen',
                'diameter': blade_thickness,
                'length': dim_y,
                'depth': dim_z,
            })
            operations.append({
                'type': 'Kappen',
                'diameter': blade_thickness,
                'length': dim_y,
                'depth': dim_z,
            })
        
        # Parse self-closing RectangularPart tags
        self_closing_parts = re.findall(r'<RectangularPart([^>]*)/>', file_content)
        for i, attrs in enumerate(self_closing_parts):
            full_tag = f'<RectangularPart{attrs}/>'
            name = self._extract_xml_attribute(full_tag, 'Name') or f'Bauteil_{len(parts)+1}'
            dim_x = float(self._extract_xml_attribute(full_tag, 'DimensionX') or '0')
            dim_y = float(self._extract_xml_attribute(full_tag, 'DimensionY') or '0')
            dim_z = float(self._extract_xml_attribute(full_tag, 'DimensionZ') or '0')
            parts.append(Part(name=name, length=dim_x, width=dim_y, height=dim_z))
        
        # Parse global Operations section
        global_ops_match = re.search(r'<Operations>([\s\S]*?)</Operations>', file_content)
        if global_ops_match:
            ops_content = global_ops_match.group(1)
            global_ops = re.findall(r'<([A-Z][a-zA-Z]+)\s+([^>]*)/>', ops_content)
            for op_type, attrs in global_ops:
                op = self._parse_operation(op_type, f'<{op_type} {attrs}/>')
                operations.append(op)
        
        return self._build_result(file_name, parts, operations)
    
    def _parse_operation(self, op_type: str, tag: str) -> Dict:
        """Parst einzelne Operation aus XML-Tag"""
        x = float(self._extract_xml_attribute(tag, 'X') or '0')
        y = float(self._extract_xml_attribute(tag, 'Y') or '0')
        z = float(self._extract_xml_attribute(tag, 'Z') or '0')
        
        drill_diam = float(self._extract_xml_attribute(tag, 'DrillDiam') or '0')
        hole_depth = float(self._extract_xml_attribute(tag, 'HoleDepth') or '0')
        dim_x = float(self._extract_xml_attribute(tag, 'DimensionX') or '0')
        dim_y = float(self._extract_xml_attribute(tag, 'DimensionY') or '0')
        dim_z = float(self._extract_xml_attribute(tag, 'DimensionZ') or '0')
        depth_attr = float(self._extract_xml_attribute(tag, 'Depth') or '0')
        prod_state = self._extract_xml_attribute(tag, 'ProductionState')
        plunge = self._extract_xml_attribute(tag, 'PlungeType') or self._extract_xml_attribute(tag, 'PocketPlungeType')
        
        diameter = None
        depth = None
        length = None
        
        if op_type == 'Drilling':
            diameter = drill_diam if drill_diam > 0 else None
            depth = hole_depth if hole_depth > 0 else None
        elif op_type == 'Slot':
            diameter = dim_x if dim_x > 0 else None
            length = dim_y if dim_y > 0 else None
            depth = z if z > 0 else (depth_attr if depth_attr > 0 else None)
        elif op_type == 'Step':
            diameter = y if y > 0 else None
            length = z if z > 0 else None
            depth = 20
        elif op_type == 'Pocket':
            diameter = dim_x if dim_x > 0 else None
            length = dim_y if dim_y > 0 else None
            depth = dim_z if dim_z > 0 else (depth_attr if depth_attr > 0 else None)
        elif op_type == 'SawCut':
            diameter = dim_x if dim_x > 0 else None
            length = dim_y if dim_y > 0 else None
            depth = dim_z if dim_z > 0 else (depth_attr if depth_attr > 0 else None)
        else:
            diameter = dim_x if dim_x > 0 else (drill_diam if drill_diam > 0 else None)
            depth = hole_depth if hole_depth > 0 else (depth_attr if depth_attr > 0 else (z if z > 0 else None))
            length = dim_x if dim_x > 0 else None
        
        return {
            'type': op_type,
            'diameter': diameter,
            'depth': depth,
            'length': length,
            'x': x,
            'y': y,
            'z': z,
            'production_state': prod_state,
            'plunge_type': plunge,
        }
    
    def _parse_text_format(self, file_content: str, file_name: str) -> AnalysisResult:
        """Parst Text-Format BVX-Dateien"""
        lines = [line.strip() for line in file_content.split('\n')]
        parts: List[Part] = []
        operations: List[Dict] = []
        
        for i, line in enumerate(lines):
            if 'BEGIN PART' in line or 'PART_DEF' in line:
                name = self._extract_text_value(line, 'NAME') or f'Part_{len(parts)+1}'
                dims = self._extract_dimensions(lines, i)
                parts.append(Part(name=name, **dims))
            
            if 'OPERATION' in line:
                if 'DRILL' in line or 'BOHR' in line:
                    diameter = self._extract_number(line, ['DIA', 'DIAMETER', 'D'])
                    depth = self._extract_number(line, ['DEPTH', 'TIEFE'])
                    if diameter and depth:
                        operations.append({
                            'type': 'Bohrung',
                            'diameter': diameter,
                            'depth': depth,
                            'x': self._extract_number(line, ['X']),
                            'y': self._extract_number(line, ['Y']),
                            'z': self._extract_number(line, ['Z']),
                        })
                
                if 'MILL' in line or 'FRÄS' in line or 'FRAS' in line:
                    diameter = self._extract_number(line, ['DIA', 'DIAMETER', 'D', 'WIDTH'])
                    depth = self._extract_number(line, ['DEPTH', 'TIEFE', 'Z'])
                    length = self._extract_number(line, ['LENGTH', 'LÄNGE', 'L'])
                    if diameter and depth:
                        operations.append({
                            'type': 'Fräsung',
                            'diameter': diameter,
                            'depth': depth,
                            'length': length or diameter,
                            'x': self._extract_number(line, ['X']),
                            'y': self._extract_number(line, ['Y']),
                        })
                
                if 'COUNTERSINK' in line or 'SENK' in line:
                    diameter = self._extract_number(line, ['DIA', 'DIAMETER', 'D'])
                    depth = self._extract_number(line, ['DEPTH', 'TIEFE'])
                    if diameter and depth:
                        operations.append({
                            'type': 'Senkung',
                            'diameter': diameter,
                            'depth': depth,
                            'x': self._extract_number(line, ['X']),
                            'y': self._extract_number(line, ['Y']),
                        })
                
                if 'THREAD' in line or 'GEWINDE' in line:
                    diameter = self._extract_number(line, ['DIA', 'DIAMETER', 'D', 'M'])
                    length = self._extract_number(line, ['LENGTH', 'LÄNGE', 'L'])
                    if diameter and length:
                        operations.append({
                            'type': 'Gewinde',
                            'diameter': diameter,
                            'length': length,
                            'x': self._extract_number(line, ['X']),
                            'y': self._extract_number(line, ['Y']),
                        })
        
        if not parts:
            parts.append(Part(name='Bauteil', length=1000, width=500, height=200))
        
        return self._build_result(file_name, parts, operations)
    
    def _extract_text_value(self, line: str, key: str) -> Optional[str]:
        """Extrahiert Wert aus Text-Zeile"""
        pattern = rf'{key}[=:\s]+([^\s,;]+)'
        match = re.search(pattern, line, re.IGNORECASE)
        return match.group(1) if match else None
    
    def _extract_number(self, line: str, keys: List[str]) -> Optional[float]:
        """Extrahiert Zahlenwert aus Text-Zeile"""
        for key in keys:
            pattern = rf'{key}[=:\s]+([\d.]+)'
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                return float(match.group(1))
        return None
    
    def _extract_dimensions(self, lines: List[str], start_idx: int) -> Dict[str, float]:
        """Extrahiert Dimensionen aus Textzeilen"""
        dims = {'length': 1000, 'width': 500, 'height': 200}
        for i in range(start_idx, min(start_idx + 20, len(lines))):
            line = lines[i]
            length = self._extract_number(line, ['LENGTH', 'LÄNGE', 'L'])
            width = self._extract_number(line, ['WIDTH', 'BREITE', 'W'])
            height = self._extract_number(line, ['HEIGHT', 'HÖHE', 'H'])
            if length: dims['length'] = length
            if width: dims['width'] = width
            if height: dims['height'] = height
            if 'END PART' in line or line == '':
                break
        return dims
    
    def _calculate_volume(self, op: Dict) -> float:
        """Berechnet Volumen einer Operation in m³"""
        op_type = op.get('type', '')
        diameter = op.get('diameter') or 0
        depth = op.get('depth') or 0
        length = op.get('length') or 0
        
        volume_mm3 = 0
        
        if op_type == 'Drilling':
            radius = diameter / 2
            volume_mm3 = math.pi * radius**2 * depth
        elif op_type in ['Slot', 'Step', 'Pocket']:
            width = diameter or length
            vol_length = length or width
            vol_depth = depth or 10
            volume_mm3 = width * vol_length * vol_depth
        elif op_type in ['Kappen', 'SawCut']:
            blade_thickness = diameter or 6
            width = length or 100
            height = depth or 100
            volume_mm3 = width * height * blade_thickness
        else:
            if diameter and depth:
                radius = diameter / 2
                volume_mm3 = math.pi * radius**2 * depth
            elif diameter and length and depth:
                volume_mm3 = diameter * length * depth
        
        return volume_mm3 / 1_000_000_000  # Convert to m³
    
    def _group_operations(self, operations: List[Dict]) -> List[Operation]:
        """Gruppiert identische Operationen"""
        groups: Dict[str, List[Dict]] = {}
        
        for op in operations:
            diameter = f"{op.get('diameter', 0):.2f}" if op.get('diameter') else 'none'
            length = f"{op.get('length', 0):.2f}" if op.get('length') else 'none'
            depth = f"{op.get('depth', 0):.2f}" if op.get('depth') else 'none'
            prod_state = op.get('production_state') or 'active'
            plunge = op.get('plunge_type') or 'none'
            key = f"{op['type']}_{diameter}_{length}_{depth}_{prod_state}_{plunge}"
            
            if key not in groups:
                groups[key] = []
            groups[key].append(op)
        
        result: List[Operation] = []
        for ops in groups.values():
            first = ops[0]
            total_volume = sum(self._calculate_volume(op) for op in ops)
            result.append(Operation(
                op_type=first['type'],
                diameter=first.get('diameter'),
                length=first.get('length'),
                depth=first.get('depth'),
                volume=total_volume,
                count=len(ops),
                x=first.get('x'),
                y=first.get('y'),
                z=first.get('z'),
                production_state=first.get('production_state'),
                plunge_type=first.get('plunge_type'),
            ))
        
        return result
    
    def _build_result(self, file_name: str, parts: List[Part], operations: List[Dict]) -> AnalysisResult:
        """Erstellt Analyseergebnis"""
        total_operation_count = len(operations)
        grouped_ops = self._group_operations(operations)
        
        total_volume = sum(p.length * p.width * p.height for p in parts) / 1_000_000_000
        machined_volume = sum(op.volume for op in grouped_ops)
        
        part_dims = None
        if parts:
            part_dims = {
                'length': parts[0].length,
                'width': parts[0].width,
                'height': parts[0].height,
            }
        
        return AnalysisResult(
            file_name=file_name,
            part_count=len(parts),
            operation_count=len(grouped_ops),
            total_operation_count=total_operation_count,
            total_volume=total_volume,
            machined_volume=machined_volume,
            operations=grouped_ops,
            parts=parts,
            part_dimensions=part_dims,
        )


def format_volume(volume: float) -> str:
    """Formatiert Volumen für Anzeige"""
    if volume < 0.001:
        return f"{volume * 1_000_000:.2f} mm³"
    elif volume < 1:
        return f"{volume * 1000:.4f} dm³"
    else:
        return f"{volume:.6f} m³"


def main():
    """Hauptfunktion der Streamlit-App"""
    st.set_page_config(
        page_title="BVX Auswertung",
        page_icon="🔧",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Custom CSS
    st.markdown("""
        <style>
        .main-header {
            font-size: 2.5rem;
            font-weight: bold;
            color: #1a1a2e;
            margin-bottom: 1rem;
        }
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 1.5rem;
            border-radius: 1rem;
            color: white;
            text-align: center;
        }
        .stat-value {
            font-size: 2rem;
            font-weight: bold;
        }
        .stat-label {
            font-size: 0.9rem;
            opacity: 0.9;
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<p class="main-header">🔧 BVX Auswertung</p>', unsafe_allow_html=True)
    st.markdown("Laden Sie eine BVX-Datei hoch, um eine detaillierte Analyse der Bauteile und Bearbeitungen zu erhalten.")
    
    # Sidebar
    with st.sidebar:
        st.header("📁 Datei Upload")
        uploaded_file = st.file_uploader(
            "BVX-Datei hochladen",
            type=['bvx'],
            help="Unterstützt: .bvx Dateien (XML und Text-Format)"
        )
        
        if uploaded_file:
            st.success(f"✅ {uploaded_file.name}")
    
    if uploaded_file is None:
        st.info("👆 Bitte laden Sie eine BVX-Datei in der Seitenleiste hoch.")
        
        # Info boxes
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
            ### Unterstützte Formate
            - **XML Format (BVX 2.1)** - Modernes XML-basiertes Format
            - **Text Format** - Legacy-Text-Format
            """)
        with col2:
            st.markdown("""
            ### Erkannte Operationen
            - Bohrungen (Drilling)
            - Fräsungen (Slot, Pocket, Mill)
            - Sägeschnitte (SawCut, Kappen)
            - Und viele mehr...
            """)
        return
    
    # Parse file
    try:
        content = uploaded_file.read().decode('utf-8')
    except UnicodeDecodeError:
        content = uploaded_file.read().decode('latin-1')
    
    parser = BVXParser()
    result = parser.parse(content, uploaded_file.name)
    
    # Stats Cards
    st.header("📊 Übersicht")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Bauteile",
            value=result.part_count,
            delta=None
        )
    
    with col2:
        st.metric(
            label="Operationstypen",
            value=result.operation_count,
            delta=f"{result.total_operation_count} gesamt"
        )
    
    with col3:
        st.metric(
            label="Bauteilvolumen",
            value=format_volume(result.total_volume),
        )
    
    with col4:
        st.metric(
            label="Bearbeitetes Volumen",
            value=format_volume(result.machined_volume),
        )
    
    # Part dimensions
    if result.part_dimensions:
        st.subheader("📐 Bauteilabmessungen")
        dims = result.part_dimensions
        col1, col2, col3 = st.columns(3)
        with col1:
            st.info(f"**Länge:** {dims['length']:.1f} mm")
        with col2:
            st.info(f"**Breite:** {dims['width']:.1f} mm")
        with col3:
            st.info(f"**Höhe:** {dims['height']:.1f} mm")
    
    # Tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Operationstabelle", "📊 Diagramme", "🗺️ Positionsübersicht", "📄 Export"])
    
    with tab1:
        st.subheader("Bearbeitungen Details")
        
        # Filters
        col1, col2 = st.columns([1, 2])
        with col1:
            operation_types = sorted(set(op.op_type for op in result.operations))
            selected_type = st.selectbox(
                "Nach Typ filtern",
                ["Alle"] + operation_types,
                key="filter_type"
            )
        with col2:
            search_term = st.text_input("Suchen...", key="search", placeholder="Typ, Durchmesser oder Tiefe")
        
        # Filter operations
        filtered_ops = result.operations
        if selected_type != "Alle":
            filtered_ops = [op for op in filtered_ops if op.op_type == selected_type]
        if search_term:
            search_lower = search_term.lower()
            filtered_ops = [op for op in filtered_ops if 
                search_lower in op.op_type.lower() or
                (op.diameter and search_lower in str(op.diameter)) or
                (op.depth and search_lower in str(op.depth))
            ]
        
        # Create DataFrame
        df_data = []
        for op in filtered_ops:
            df_data.append({
                'Typ': op.op_type,
                'Anzahl': op.count,
                'Durchmesser (mm)': f"{op.diameter:.1f}" if op.diameter else "-",
                'Länge/Tiefe (mm)': f"{op.depth:.1f}" if op.depth else "-",
                'Volumen': format_volume(op.volume),
            })
        
        df = pd.DataFrame(df_data)
        
        if not df.empty:
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
            )
            
            # Summary
            total_ops = sum(op.count for op in filtered_ops)
            st.caption(f"Zeigt {len(filtered_ops)} Operationstypen ({total_ops} Operationen gesamt)")
        else:
            st.warning("Keine Operationen gefunden.")
    
    with tab2:
        st.subheader("Visualisierungen")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Operations by type (pie chart)
            type_counts = Counter(op.op_type for op in result.operations for _ in range(op.count))
            fig_pie = px.pie(
                values=list(type_counts.values()),
                names=list(type_counts.keys()),
                title="Operationen nach Typ",
                hole=0.4,
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with col2:
            # Volume by type (bar chart)
            volume_by_type = {}
            for op in result.operations:
                if op.op_type not in volume_by_type:
                    volume_by_type[op.op_type] = 0
                volume_by_type[op.op_type] += op.volume
            
            fig_bar = px.bar(
                x=list(volume_by_type.keys()),
                y=[v * 1_000_000 for v in volume_by_type.values()],  # Convert to mm³
                title="Volumen nach Operationstyp (mm³)",
                labels={'x': 'Operationstyp', 'y': 'Volumen (mm³)'},
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        
        # Diameter distribution
        diameters = [op.diameter for op in result.operations if op.diameter and op.diameter > 0]
        if diameters:
            fig_hist = px.histogram(
                x=diameters,
                nbins=20,
                title="Verteilung der Durchmesser",
                labels={'x': 'Durchmesser (mm)', 'y': 'Anzahl'},
            )
            st.plotly_chart(fig_hist, use_container_width=True)
    
    with tab3:
        st.subheader("2D Positionsübersicht")
        
        # Get operations with positions
        ops_with_pos = [op for op in result.operations if op.x is not None and op.y is not None]
        
        if ops_with_pos:
            # Create scatter plot
            fig_scatter = go.Figure()
            
            # Group by operation type for coloring
            for op_type in set(op.op_type for op in ops_with_pos):
                type_ops = [op for op in ops_with_pos if op.op_type == op_type]
                fig_scatter.add_trace(go.Scatter(
                    x=[op.x for op in type_ops],
                    y=[op.y for op in type_ops],
                    mode='markers',
                    name=op_type,
                    marker=dict(size=10),
                    text=[f"{op.op_type}<br>D: {op.diameter or '-'} mm" for op in type_ops],
                    hovertemplate='<b>%{text}</b><br>X: %{x}<br>Y: %{y}<extra></extra>'
                ))
            
            # Add part outline if dimensions available
            if result.part_dimensions:
                dims = result.part_dimensions
                fig_scatter.add_shape(
                    type="rect",
                    x0=0, y0=0,
                    x1=dims['length'], y1=dims['width'],
                    line=dict(color="gray", dash="dash"),
                )
            
            fig_scatter.update_layout(
                title="Operationspositionen auf Bauteil",
                xaxis_title="X Position (mm)",
                yaxis_title="Y Position (mm)",
                showlegend=True,
                height=500,
            )
            
            st.plotly_chart(fig_scatter, use_container_width=True)
        else:
            st.info("Keine Positionsdaten in der BVX-Datei vorhanden.")
    
    with tab4:
        st.subheader("Daten exportieren")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # CSV Export
            df_export = pd.DataFrame([{
                'Typ': op.op_type,
                'Anzahl': op.count,
                'Durchmesser_mm': op.diameter,
                'Tiefe_mm': op.depth,
                'Laenge_mm': op.length,
                'Volumen_m3': op.volume,
                'X': op.x,
                'Y': op.y,
                'Z': op.z,
            } for op in result.operations])
            
            csv = df_export.to_csv(index=False)
            st.download_button(
                label="📥 Als CSV herunterladen",
                data=csv,
                file_name=f"{result.file_name.replace('.bvx', '')}_analyse.csv",
                mime="text/csv",
            )
        
        with col2:
            # Excel Export
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_export.to_excel(writer, sheet_name='Operationen', index=False)
                
                # Summary sheet
                summary_data = {
                    'Eigenschaft': ['Dateiname', 'Anzahl Bauteile', 'Anzahl Operationstypen', 
                                   'Gesamtoperationen', 'Bauteilvolumen (m³)', 'Bearbeitetes Volumen (m³)'],
                    'Wert': [result.file_name, result.part_count, result.operation_count,
                            result.total_operation_count, result.total_volume, result.machined_volume]
                }
                pd.DataFrame(summary_data).to_excel(writer, sheet_name='Zusammenfassung', index=False)
            
            st.download_button(
                label="📥 Als Excel herunterladen",
                data=output.getvalue(),
                file_name=f"{result.file_name.replace('.bvx', '')}_analyse.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        
        # Show raw summary
        with st.expander("📋 Zusammenfassung anzeigen"):
            st.json({
                "dateiname": result.file_name,
                "bauteile": result.part_count,
                "operationstypen": result.operation_count,
                "gesamtoperationen": result.total_operation_count,
                "bauteilvolumen_m3": result.total_volume,
                "bearbeitetes_volumen_m3": result.machined_volume,
                "bauteilabmessungen": result.part_dimensions,
            })


if __name__ == "__main__":
    main()
