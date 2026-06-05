"""
BVX Auswertung + Verladeplanung - Streamlit Version

Installation:
    pip install streamlit pandas plotly openpyxl

Ausführen:
    streamlit run bvx_auswertung_streamlit_verladung.py

Hinweis:
    Die Verladeplanung ist als grober, eigenständiger Modulbereich aufgebaut.
    Die Transportabmessungen sind Beispiel-/Stammdaten und müssen intern geprüft und angepasst werden.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import math
import io
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from collections import Counter


# =============================================================================
# Datenmodelle
# =============================================================================

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
    part_no: str = ""
    part_id: str = ""
    unit: str = ""
    profile: str = ""
    surface: str = ""
    grade: str = ""
    user_attribute_2: str = ""
    volume_m3: float = 0.0
    attributes: Dict[str, str] = field(default_factory=dict)


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


# =============================================================================
# BVX Parser
# =============================================================================

class BVXParser:
    """Parser für BVX-Dateien (XML und Text-Format)."""

    OPERATION_TYPES = [
        'Drilling', 'SawCut', 'Slot', 'Step', 'Pocket', 'BlindSlot', 'BlindStep',
        'Mill', 'Countersink', 'Thread', 'FrameBox', 'BirdsMouth', 'Mortise',
        'Tenon', 'Notch', 'Rabbet', 'Chamfer', 'Groove', 'Dado', 'LapJoint',
        'DovetailJoint', 'FingerJoint', 'ScarfJoint', 'HalfLap', 'CrossLap',
        'LowerBoomSingleStepJoint', 'CADPosition', 'CADPositionList', 'Kappen'
    ]

    def parse(self, file_content: str, file_name: str = "uploaded.bvx") -> AnalysisResult:
        """Analysiert BVX-Dateiinhalt und gibt Analyseergebnis zurück."""
        if file_content.strip().startswith('<?xml') or '<RectangularPart' in file_content:
            return self._parse_xml_format(file_content, file_name)
        return self._parse_text_format(file_content, file_name)

    def _extract_xml_attribute(self, tag: str, attr_name: str) -> Optional[str]:
        """Extrahiert XML-Attributwert aus einem Tag."""
        pattern = rf'{re.escape(attr_name)}="([^"]*)"'
        match = re.search(pattern, tag, re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_all_xml_attributes(self, tag: str) -> Dict[str, str]:
        """Extrahiert alle XML-Attribute aus einem Tag."""
        return {key: value for key, value in re.findall(r'([\w:.-]+)="([^"]*)"', tag)}

    def _get_attr_first(self, attrs: Dict[str, str], keys: List[str], default: str = "") -> str:
        """Sucht ein Attribut case-insensitive über mehrere mögliche Namen."""
        lower_map = {k.lower(): v for k, v in attrs.items()}
        for key in keys:
            value = lower_map.get(key.lower())
            if value is not None:
                return value
        return default

    def _safe_float(self, value: Optional[str], default: float = 0.0) -> float:
        """Sicher einen String zu Float konvertieren."""
        if value is None or value == "":
            return default
        try:
            return float(str(value).replace(',', '.'))
        except (ValueError, TypeError):
            return default

    def _make_part_from_tag(self, tag: str, fallback_name: str) -> Part:
        attrs = self._extract_all_xml_attributes(tag)

        name = self._get_attr_first(attrs, ['Name', 'PartName'], fallback_name)
        dim_x = self._safe_float(self._get_attr_first(attrs, ['DimensionX', 'Length', 'Laenge']))
        dim_y = self._safe_float(self._get_attr_first(attrs, ['DimensionY', 'Width', 'Breite']))
        dim_z = self._safe_float(self._get_attr_first(attrs, ['DimensionZ', 'Height', 'Hoehe', 'Höhe']))

        # BVX-Grundannahme für Verladung:
        # X = Länge, Y = Breite, Z = Höhe
        volume_m3 = (dim_x * dim_y * dim_z) / 1_000_000_000 if dim_x and dim_y and dim_z else 0.0

        part_no = self._get_attr_first(attrs, ['PartNo', 'PartNumber', 'Number', 'Bauteilnummer', 'PieceNo'])
        part_id = self._get_attr_first(attrs, ['PartId', 'PartID', 'Id', 'ID', 'Guid'])
        unit = self._get_attr_first(attrs, ['Unit', 'Pak', 'Package', 'Paket'])
        profile = self._get_attr_first(attrs, ['Profile', 'Profil'])
        surface = self._get_attr_first(attrs, ['Surface', 'Oberflaeche', 'Oberfläche'])
        grade = self._get_attr_first(attrs, ['Grade', 'Quality', 'Qualitaet', 'Qualität'])
        user_attribute_2 = self._get_attr_first(attrs, ['User_Attribut_2', 'User_Attribute_2', 'UserAttribut2'])

        return Part(
            name=name,
            length=dim_x,
            width=dim_y,
            height=dim_z,
            part_no=part_no,
            part_id=part_id,
            unit=unit,
            profile=profile,
            surface=surface,
            grade=grade,
            user_attribute_2=user_attribute_2,
            volume_m3=volume_m3,
            attributes=attrs,
        )

    def _parse_xml_format(self, file_content: str, file_name: str) -> AnalysisResult:
        """Parst XML-Format BVX-Dateien."""
        parts: List[Part] = []
        operations: List[Dict[str, Any]] = []

        # RectangularPart mit Inhalt
        part_matches = re.finditer(r'<RectangularPart\b([^>]*)>([\s\S]*?)</RectangularPart>', file_content, re.IGNORECASE)
        for i, match in enumerate(part_matches):
            attrs_text = match.group(1)
            content = match.group(2)
            full_tag = f'<RectangularPart{attrs_text}>'
            part = self._make_part_from_tag(full_tag, f'Bauteil_{len(parts) + 1}')
            parts.append(part)

            op_pattern = '|'.join(self.OPERATION_TYPES)
            self_closing = re.findall(rf'<({op_pattern})\s+([^>]*)/>', content, re.IGNORECASE)
            content_tags = re.findall(rf'<({op_pattern})\s+([^>]*)>[\s\S]*?</\1>', content, re.IGNORECASE)

            for op_type, attrs in self_closing + content_tags:
                op = self._parse_operation(op_type, f'<{op_type} {attrs}>')
                operations.append(op)

            # Kappen grob als zwei Sägeschnitte je Bauteil erfassen
            blade_thickness = 6
            if part.width and part.height:
                operations.append({
                    'type': 'Kappen',
                    'diameter': blade_thickness,
                    'length': part.width,
                    'depth': part.height,
                })
                operations.append({
                    'type': 'Kappen',
                    'diameter': blade_thickness,
                    'length': part.width,
                    'depth': part.height,
                })

        # Self-closing RectangularPart tags
        self_closing_parts = re.finditer(r'<RectangularPart\b([^>]*)/>', file_content, re.IGNORECASE)
        for match in self_closing_parts:
            full_tag = f'<RectangularPart{match.group(1)}/>'
            parts.append(self._make_part_from_tag(full_tag, f'Bauteil_{len(parts) + 1}'))

        # Globale Operations-Sektion
        global_ops_match = re.search(r'<Operations>([\s\S]*?)</Operations>', file_content, re.IGNORECASE)
        if global_ops_match:
            ops_content = global_ops_match.group(1)
            global_ops = re.findall(r'<([A-Z][a-zA-Z]+)\s+([^>]*)/>', ops_content)
            for op_type, attrs in global_ops:
                op = self._parse_operation(op_type, f'<{op_type} {attrs}/>')
                operations.append(op)

        return self._build_result(file_name, parts, operations)

    def _parse_operation(self, op_type: str, tag: str) -> Dict[str, Any]:
        """Parst einzelne Operation aus XML-Tag."""
        x = self._safe_float(self._extract_xml_attribute(tag, 'X'))
        y = self._safe_float(self._extract_xml_attribute(tag, 'Y'))
        z = self._safe_float(self._extract_xml_attribute(tag, 'Z'))

        drill_diam = self._safe_float(self._extract_xml_attribute(tag, 'DrillDiam'))
        hole_depth = self._safe_float(self._extract_xml_attribute(tag, 'HoleDepth'))
        dim_x = self._safe_float(self._extract_xml_attribute(tag, 'DimensionX'))
        dim_y = self._safe_float(self._extract_xml_attribute(tag, 'DimensionY'))
        dim_z = self._safe_float(self._extract_xml_attribute(tag, 'DimensionZ'))
        depth_attr = self._safe_float(self._extract_xml_attribute(tag, 'Depth'))
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
        """Parst Text-Format BVX-Dateien."""
        lines = [line.strip() for line in file_content.split('\n')]
        parts: List[Part] = []
        operations: List[Dict[str, Any]] = []

        for i, line in enumerate(lines):
            if 'BEGIN PART' in line or 'PART_DEF' in line:
                name = self._extract_text_value(line, 'NAME') or f'Part_{len(parts) + 1}'
                dims = self._extract_dimensions(lines, i)
                volume_m3 = dims['length'] * dims['width'] * dims['height'] / 1_000_000_000
                parts.append(Part(name=name, volume_m3=volume_m3, **dims))

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
            parts.append(Part(name='Bauteil', length=1000, width=500, height=200, volume_m3=0.1))

        return self._build_result(file_name, parts, operations)

    def _extract_text_value(self, line: str, key: str) -> Optional[str]:
        """Extrahiert Wert aus Text-Zeile."""
        pattern = rf'{key}[=:\s]+([^\s,;]+)'
        match = re.search(pattern, line, re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_number(self, line: str, keys: List[str]) -> Optional[float]:
        """Extrahiert Zahlenwert aus Text-Zeile."""
        for key in keys:
            pattern = rf'{key}[=:\s]+([\d.]+)'
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                return float(match.group(1))
        return None

    def _extract_dimensions(self, lines: List[str], start_idx: int) -> Dict[str, float]:
        """Extrahiert Dimensionen aus Textzeilen."""
        dims = {'length': 1000, 'width': 500, 'height': 200}
        for i in range(start_idx, min(start_idx + 20, len(lines))):
            line = lines[i]
            length = self._extract_number(line, ['LENGTH', 'LÄNGE', 'LAENGE', 'L'])
            width = self._extract_number(line, ['WIDTH', 'BREITE', 'W'])
            height = self._extract_number(line, ['HEIGHT', 'HÖHE', 'HOEHE', 'H'])
            if length:
                dims['length'] = length
            if width:
                dims['width'] = width
            if height:
                dims['height'] = height
            if 'END PART' in line or line == '':
                break
        return dims

    def _calculate_volume(self, op: Dict[str, Any]) -> float:
        """Berechnet Volumen einer Operation in m³."""
        op_type = op.get('type', '')
        diameter = op.get('diameter') or 0
        depth = op.get('depth') or 0
        length = op.get('length') or 0

        volume_mm3 = 0

        if op_type == 'Drilling':
            radius = diameter / 2
            volume_mm3 = math.pi * radius ** 2 * depth
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
                volume_mm3 = math.pi * radius ** 2 * depth
            elif diameter and length and depth:
                volume_mm3 = diameter * length * depth

        return volume_mm3 / 1_000_000_000

    def _group_operations(self, operations: List[Dict[str, Any]]) -> List[Operation]:
        """Gruppiert identische Operationen."""
        groups: Dict[str, List[Dict[str, Any]]] = {}

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

    def _build_result(self, file_name: str, parts: List[Part], operations: List[Dict[str, Any]]) -> AnalysisResult:
        """Erstellt Analyseergebnis."""
        total_operation_count = len(operations)
        grouped_ops = self._group_operations(operations)

        total_volume = sum((p.volume_m3 or (p.length * p.width * p.height / 1_000_000_000)) for p in parts)
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


# =============================================================================
# Allgemeine Hilfsfunktionen
# =============================================================================

def read_uploaded_text(uploaded_file) -> str:
    raw = uploaded_file.read()
    for encoding in ('utf-8', 'latin-1', 'cp1252'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='ignore')


def format_volume(volume: float) -> str:
    """Formatiert Volumen für Anzeige."""
    if volume < 0.001:
        return f"{volume * 1_000_000:.2f} mm³"
    if volume < 1:
        return f"{volume * 1000:.4f} dm³"
    return f"{volume:.6f} m³"


def parts_to_dataframe(parts: List[Part], density_kg_m3: float = 500.0) -> pd.DataFrame:
    rows = []
    for idx, part in enumerate(parts, start=1):
        volume_m3 = part.volume_m3 or (part.length * part.width * part.height / 1_000_000_000)
        rows.append({
            'Index': idx,
            'Name': part.name,
            'Bauteilnummer': part.part_no or part.name,
            'PartId': part.part_id,
            'Pak/Unit': part.unit,
            'Profil': part.profile,
            'Oberfläche': part.surface,
            'Qualität': part.grade,
            'User_Attribut_2': part.user_attribute_2,
            'Länge_mm': float(part.length or 0),
            'Breite_mm': float(part.width or 0),
            'Höhe_mm': float(part.height or 0),
            'Volumen_m3': float(volume_m3 or 0),
            'Gewicht_kg': float((volume_m3 or 0) * density_kg_m3),
        })
    return pd.DataFrame(rows)


def sort_parts_dataframe(
    df: pd.DataFrame,
    main_attr: str,
    main_asc: bool,
    second_attr: str,
    second_asc: bool,
) -> pd.DataFrame:
    sort_cols = []
    sort_ascending = []

    if main_attr and main_attr in df.columns:
        sort_cols.append(main_attr)
        sort_ascending.append(main_asc)
    if second_attr and second_attr != 'Keine' and second_attr in df.columns and second_attr not in sort_cols:
        sort_cols.append(second_attr)
        sort_ascending.append(second_asc)

    if not sort_cols:
        return df.copy()

    result = df.copy()
    for col in sort_cols:
        # leere Werte sauber ans Ende bringen
        if result[col].dtype == object:
            result[col] = result[col].fillna('').astype(str)
    return result.sort_values(by=sort_cols, ascending=sort_ascending, kind='stable').reset_index(drop=True)


# =============================================================================
# Verladeplanung
# =============================================================================

def yes_no_to_bool(value: Any) -> bool:
    """Wandelt JA/NEIN, True/False, 1/0 robust in Bool."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)) and not pd.isna(value):
        return value != 0
    text = str(value).strip().lower()
    return text in {'ja', 'j', 'yes', 'y', 'true', 'wahr', '1', 'x'}


def safe_number(value: Any, default: float = 0.0) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        return float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        return default


def get_transport_presets() -> Dict[str, List[Dict[str, Any]]]:
    """Fallback-Stammdaten, falls keine Excel-Vorlage geladen wird."""
    return {
        'LKW solo': [
            {'Freigabe': True, 'Pritsche': 'LKW', 'Pritschenname': 'LKW', 'Fuhrenoption': 'LKW solo', 'Pritschen_Reihenfolge': 1,
             'Länge_mm': 9300, 'Breite_mm': 2450, 'Max_Höhe_mm': 2600, 'Überhang_vorne_mm': 0,
             'Überhang_hinten_mm': 300, 'Max_Gewicht_kg': 15000, 'Kantholz_erste_Lage_mm': 80,
             'Einlage_zwischen_Lagen_mm': 40, 'Drehen_90_erlaubt': False},
        ],
        'LKW mit Anhänger': [
            {'Freigabe': True, 'Pritsche': 'LKW', 'Pritschenname': 'LKW', 'Fuhrenoption': 'LKW mit Anhänger', 'Pritschen_Reihenfolge': 1,
             'Länge_mm': 9300, 'Breite_mm': 2450, 'Max_Höhe_mm': 2600, 'Überhang_vorne_mm': 0,
             'Überhang_hinten_mm': 300, 'Max_Gewicht_kg': 15000, 'Kantholz_erste_Lage_mm': 80,
             'Einlage_zwischen_Lagen_mm': 40, 'Drehen_90_erlaubt': False},
            {'Freigabe': True, 'Pritsche': 'Anhänger', 'Pritschenname': 'Anhänger', 'Fuhrenoption': 'LKW mit Anhänger', 'Pritschen_Reihenfolge': 2,
             'Länge_mm': 8200, 'Breite_mm': 2450, 'Max_Höhe_mm': 2600, 'Überhang_vorne_mm': 0,
             'Überhang_hinten_mm': 300, 'Max_Gewicht_kg': 12000, 'Kantholz_erste_Lage_mm': 80,
             'Einlage_zwischen_Lagen_mm': 40, 'Drehen_90_erlaubt': False},
        ],
        'Anhängerzug': [
            {'Freigabe': True, 'Pritsche': 'LKW', 'Pritschenname': 'LKW', 'Fuhrenoption': 'Anhängerzug', 'Pritschen_Reihenfolge': 1,
             'Länge_mm': 7600, 'Breite_mm': 2450, 'Max_Höhe_mm': 2600, 'Überhang_vorne_mm': 0,
             'Überhang_hinten_mm': 300, 'Max_Gewicht_kg': 12000, 'Kantholz_erste_Lage_mm': 80,
             'Einlage_zwischen_Lagen_mm': 40, 'Drehen_90_erlaubt': False},
            {'Freigabe': True, 'Pritsche': 'Anhänger', 'Pritschenname': 'Anhänger', 'Fuhrenoption': 'Anhängerzug', 'Pritschen_Reihenfolge': 2,
             'Länge_mm': 8200, 'Breite_mm': 2450, 'Max_Höhe_mm': 2600, 'Überhang_vorne_mm': 0,
             'Überhang_hinten_mm': 300, 'Max_Gewicht_kg': 12000, 'Kantholz_erste_Lage_mm': 80,
             'Einlage_zwischen_Lagen_mm': 40, 'Drehen_90_erlaubt': False},
        ],
        'Tiefbettauflieger': [
            {'Freigabe': True, 'Pritsche': 'Tiefbett', 'Pritschenname': 'Tiefbett', 'Fuhrenoption': 'Tiefbettauflieger', 'Pritschen_Reihenfolge': 1,
             'Länge_mm': 13000, 'Breite_mm': 2550, 'Max_Höhe_mm': 3200, 'Überhang_vorne_mm': 500,
             'Überhang_hinten_mm': 1000, 'Max_Gewicht_kg': 24000, 'Kantholz_erste_Lage_mm': 100,
             'Einlage_zwischen_Lagen_mm': 40, 'Drehen_90_erlaubt': True},
        ],
    }


def read_transport_config_excel(uploaded_excel) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any], List[str]]:
    """Liest die Excel-Stammdaten für Fuhrenoptionen, Pritschen und Standards."""
    messages: List[str] = []
    standards: Dict[str, Any] = {
        'Holzdichte': 500.0,
        'Max_Bundgewicht': 1000.0,
        'Standard_Kantholz_erste_Lage': 80.0,
        'Standard_Einlage_zwischen_Lagen': 40.0,
        'Längenversatz_je_Lage': 100.0,
        'Abstand_zwischen_Einheiten': 0.0,
        'Sichtseite_nach_unten': 'JA',
        'Plane_Folie': 'JA',
    }

    if uploaded_excel is None:
        options = pd.DataFrame([
            {'Freigegeben': True, 'Priorität': 1, 'Fuhrenoption': 'LKW solo', 'Wiederholen_bis_alles_verladen': True, 'Strategie': 'Variante A'},
        ])
        preset = get_transport_presets()['LKW solo']
        pritschen = pd.DataFrame(preset)
        return options, pritschen, standards, ['Keine Excel-Stammdaten geladen. Fallback LKW solo wird verwendet.']

    try:
        xls = pd.ExcelFile(uploaded_excel)
        options_raw = pd.read_excel(xls, sheet_name='Fuhrenoptionen')
        pritschen_raw = pd.read_excel(xls, sheet_name='Pritschen')
        standards_raw = pd.read_excel(xls, sheet_name='Standards')
    except Exception as exc:
        preset = get_transport_presets()['LKW solo']
        options = pd.DataFrame([
            {'Freigegeben': True, 'Priorität': 1, 'Fuhrenoption': 'LKW solo', 'Wiederholen_bis_alles_verladen': True, 'Strategie': 'Variante A'},
        ])
        pritschen = pd.DataFrame(preset)
        return options, pritschen, standards, [f'Excel konnte nicht gelesen werden: {exc}. Fallback LKW solo wird verwendet.']

    if {'Parameter', 'Wert'}.issubset(set(standards_raw.columns)):
        for _, row in standards_raw.dropna(how='all').iterrows():
            key = str(row.get('Parameter', '')).strip()
            if not key:
                continue
            value = row.get('Wert')
            if key in ['Sichtseite_nach_unten', 'Plane_Folie']:
                standards[key] = value
            else:
                standards[key] = safe_number(value, standards.get(key, 0.0))

    options = options_raw.dropna(how='all').copy()
    needed_options = ['Freigegeben', 'Priorität', 'Fuhrenoption']
    for col in needed_options:
        if col not in options.columns:
            options[col] = ''
    options = options[options['Fuhrenoption'].notna() & (options['Fuhrenoption'].astype(str).str.strip() != '')].copy()
    options['Freigegeben'] = options['Freigegeben'].apply(yes_no_to_bool)
    options['Priorität'] = options['Priorität'].apply(lambda v: int(safe_number(v, 999)))
    if 'Wiederholen_bis_alles_verladen' not in options.columns:
        options['Wiederholen_bis_alles_verladen'] = True
    options['Wiederholen_bis_alles_verladen'] = options['Wiederholen_bis_alles_verladen'].apply(yes_no_to_bool)
    if 'Strategie' not in options.columns:
        options['Strategie'] = 'Variante A'

    p = pritschen_raw.dropna(how='all').copy()
    rename_map = {
        'Pritschenname': 'Pritschenname',
        'Max_Ladehöhe_mm': 'Max_Höhe_mm',
        'Max_Höhe_mm': 'Max_Höhe_mm',
        'Aktiv': 'Freigabe',
        'Drehen_90_erlaubt': 'Drehen_90_erlaubt',
    }
    p = p.rename(columns={k: v for k, v in rename_map.items() if k in p.columns})

    required_cols = [
        'Fuhrenoption', 'Pritschen_Reihenfolge', 'Pritschenname', 'Freigabe', 'Länge_mm', 'Breite_mm',
        'Max_Höhe_mm', 'Max_Gewicht_kg', 'Überhang_vorne_mm', 'Überhang_hinten_mm',
        'Kantholz_erste_Lage_mm', 'Einlage_zwischen_Lagen_mm', 'Drehen_90_erlaubt'
    ]
    for col in required_cols:
        if col not in p.columns:
            p[col] = ''

    p = p[p['Fuhrenoption'].notna() & (p['Fuhrenoption'].astype(str).str.strip() != '')].copy()
    p['Freigabe'] = p['Freigabe'].apply(yes_no_to_bool)
    p['Drehen_90_erlaubt'] = p['Drehen_90_erlaubt'].apply(yes_no_to_bool)
    p['Pritschen_Reihenfolge'] = p['Pritschen_Reihenfolge'].apply(lambda v: int(safe_number(v, 999)))
    for col in ['Länge_mm', 'Breite_mm', 'Max_Höhe_mm', 'Max_Gewicht_kg', 'Überhang_vorne_mm', 'Überhang_hinten_mm', 'Kantholz_erste_Lage_mm', 'Einlage_zwischen_Lagen_mm']:
        p[col] = p[col].apply(lambda v: safe_number(v, 0.0))
    p['Pritsche'] = p['Pritschenname'].astype(str)

    if options.empty:
        messages.append('Keine gültigen Fuhrenoptionen in der Excel gefunden.')
    if p.empty:
        messages.append('Keine gültigen Pritschen in der Excel gefunden.')
    return options, p, standards, messages


def make_bundle_signature(row: pd.Series, same_height: bool, same_width: bool, same_quality: bool, same_profile: bool) -> Tuple[Any, ...]:
    signature: List[Any] = []
    if same_height:
        signature.append(row.get('Höhe_mm'))
    if same_width:
        signature.append(row.get('Breite_mm'))
    if same_quality:
        signature.append(row.get('Qualität'))
    if same_profile:
        signature.append(row.get('Profil'))
    return tuple(signature)


def build_loading_units(
    sorted_parts: pd.DataFrame,
    use_bundles: bool,
    max_bundle_weight: float,
    bundle_spacer_height: float,
    same_height: bool,
    same_width: bool,
    same_quality: bool,
    same_profile: bool,
) -> pd.DataFrame:
    """Erzeugt Verladeeinheiten: einzelnes Bauteil oder Bund."""
    if sorted_parts.empty:
        return pd.DataFrame()

    units: List[Dict[str, Any]] = []

    if not use_bundles:
        for idx, row in sorted_parts.iterrows():
            units.append({
                'Einheit_ID': f'E{idx + 1:03d}',
                'Typ': 'Bauteil',
                'Anzahl_Bauteile': 1,
                'Bauteile': row.get('Bauteilnummer') or row.get('Name'),
                'Länge_mm': row['Länge_mm'],
                'Breite_mm': row['Breite_mm'],
                'Höhe_mm': row['Höhe_mm'],
                'Volumen_m3': row['Volumen_m3'],
                'Gewicht_kg': row['Gewicht_kg'],
                'Warnung': 'über max. Bundgewicht' if row['Gewicht_kg'] > max_bundle_weight else '',
            })
        return pd.DataFrame(units)

    current_rows: List[pd.Series] = []
    current_weight = 0.0
    current_signature: Optional[Tuple[Any, ...]] = None

    def flush_bundle():
        if not current_rows:
            return
        count = len(current_rows)
        length = max(float(r['Länge_mm']) for r in current_rows)
        width = max(float(r['Breite_mm']) for r in current_rows)
        height = sum(float(r['Höhe_mm']) for r in current_rows) + max(0, count - 1) * bundle_spacer_height
        volume = sum(float(r['Volumen_m3']) for r in current_rows)
        weight = sum(float(r['Gewicht_kg']) for r in current_rows)
        part_labels = [str(r.get('Bauteilnummer') or r.get('Name')) for r in current_rows]
        units.append({
            'Einheit_ID': f'B{len(units) + 1:03d}',
            'Typ': 'Bund' if count > 1 else 'Bauteil',
            'Anzahl_Bauteile': count,
            'Bauteile': ', '.join(part_labels),
            'Länge_mm': length,
            'Breite_mm': width,
            'Höhe_mm': height,
            'Volumen_m3': volume,
            'Gewicht_kg': weight,
            'Warnung': 'über max. Bundgewicht' if weight > max_bundle_weight else '',
        })

    for _, row in sorted_parts.iterrows():
        row_weight = float(row['Gewicht_kg'])
        row_signature = make_bundle_signature(row, same_height, same_width, same_quality, same_profile)
        signature_break = current_signature is not None and row_signature != current_signature
        weight_break = current_rows and (current_weight + row_weight > max_bundle_weight)

        if signature_break or weight_break:
            flush_bundle()
            current_rows = []
            current_weight = 0.0
            current_signature = None

        current_rows.append(row)
        current_weight += row_weight
        current_signature = row_signature

    flush_bundle()
    return pd.DataFrame(units)


def init_platform_state(row: pd.Series, base_wood_height: float, layer_spacer_height: float, gap_length: float) -> Dict[str, Any]:
    base_height = safe_number(row.get('Kantholz_erste_Lage_mm'), base_wood_height)
    layer_height = safe_number(row.get('Einlage_zwischen_Lagen_mm'), layer_spacer_height)
    return {
        'Fuhre_Nr': int(row.get('Fuhre_Nr', 1)) if not pd.isna(row.get('Fuhre_Nr', 1)) else 1,
        'Fuhrenoption': str(row.get('Fuhrenoption', '')),
        'Pritschenname': str(row.get('Pritschenname', row.get('Pritsche', 'Pritsche'))),
        'Pritsche': str(row['Pritsche']),
        'Länge_mm': float(row['Länge_mm']),
        'Breite_mm': float(row['Breite_mm']),
        'Max_Höhe_mm': float(row['Max_Höhe_mm']),
        'Überhang_vorne_mm': float(row['Überhang_vorne_mm']),
        'Überhang_hinten_mm': float(row['Überhang_hinten_mm']),
        'Max_Gewicht_kg': float(row['Max_Gewicht_kg']),
        'Eff_Länge_mm': float(row['Länge_mm']) + float(row['Überhang_vorne_mm']) + float(row['Überhang_hinten_mm']),
        'base_wood_height': float(base_height),
        'layer_spacer_height': float(layer_height),
        'gap_length': float(gap_length),
        'allow_rotation_platform': yes_no_to_bool(row.get('Drehen_90_erlaubt', False)),
        'current_x': 0.0,
        'current_y': 0.0,
        'current_z': float(base_height),
        'row_max_width': 0.0,
        'layer_max_height': 0.0,
        'used_length': 0.0,
        'used_width': 0.0,
        'used_height': float(base_height),
        'total_weight': 0.0,
        'placements': [],
    }


def can_place(state: Dict[str, Any], x: float, y: float, z: float, length: float, width: float, height: float, weight: float) -> bool:
    if state['total_weight'] + weight > state['Max_Gewicht_kg']:
        return False
    if x + length > state['Eff_Länge_mm']:
        return False
    if y + width > state['Breite_mm']:
        return False
    if z + height > state['Max_Höhe_mm']:
        return False
    return True


def commit_place(
    state: Dict[str, Any],
    unit: pd.Series,
    x: float,
    y: float,
    z: float,
    length: float,
    width: float,
    height: float,
    rotation: int,
    mode: str,
) -> Dict[str, Any]:
    placement = {
        'Fuhre_Nr': state['Fuhre_Nr'],
        'Fuhrenoption': state['Fuhrenoption'],
        'Pritschenname': state['Pritschenname'],
        'Pritsche': state['Pritsche'],
        'Einheit_ID': unit['Einheit_ID'],
        'Typ': unit['Typ'],
        'Anzahl_Bauteile': int(unit['Anzahl_Bauteile']),
        'Bauteile': unit['Bauteile'],
        'X_mm': round(x, 1),
        'Y_mm': round(y, 1),
        'Z_mm': round(z, 1),
        'Länge_mm': round(length, 1),
        'Breite_mm': round(width, 1),
        'Höhe_mm': round(height, 1),
        'Drehung': rotation,
        'Ebene': mode,
        'Gewicht_kg': round(float(unit['Gewicht_kg']), 2),
    }
    state['placements'].append(placement)

    state['current_x'] = x + length + state['gap_length']
    state['current_y'] = y
    state['row_max_width'] = max(state['row_max_width'], width)
    state['layer_max_height'] = max(state['layer_max_height'], height)
    state['used_length'] = max(state['used_length'], x + length)
    state['used_width'] = max(state['used_width'], y + width)
    state['used_height'] = max(state['used_height'], z + height)
    state['total_weight'] += float(unit['Gewicht_kg'])
    return placement


def try_place_unit(
    state: Dict[str, Any],
    unit: pd.Series,
    allow_beside: bool,
    allow_stack: bool,
    allow_rotation: bool,
) -> Optional[Dict[str, Any]]:
    length = float(unit['Länge_mm'])
    width = float(unit['Breite_mm'])
    height = float(unit['Höhe_mm'])
    weight = float(unit['Gewicht_kg'])

    rotation_allowed = bool(allow_rotation and state.get('allow_rotation_platform', False))
    orientations = [(length, width, 0)]
    if rotation_allowed and length != width:
        orientations.append((width, length, 90))

    for use_length, use_width, rotation in orientations:
        # 1. hintereinander in aktueller Reihe
        x = state['current_x']
        y = state['current_y']
        z = state['current_z']
        if can_place(state, x, y, z, use_length, use_width, height, weight):
            return commit_place(state, unit, x, y, z, use_length, use_width, height, rotation, 'hintereinander')

        # 2. neue Reihe daneben
        if allow_beside and state['row_max_width'] > 0:
            x = 0.0
            y = state['current_y'] + state['row_max_width']
            z = state['current_z']
            if can_place(state, x, y, z, use_length, use_width, height, weight):
                state['current_x'] = 0.0
                state['current_y'] = y
                state['row_max_width'] = 0.0
                return commit_place(state, unit, x, y, z, use_length, use_width, height, rotation, 'nebeneinander')

        # 3. neue Lage darüber
        if allow_stack and state['layer_max_height'] > 0:
            x = 0.0
            y = 0.0
            z = state['current_z'] + state['layer_max_height'] + state['layer_spacer_height']
            if can_place(state, x, y, z, use_length, use_width, height, weight):
                state['current_x'] = 0.0
                state['current_y'] = 0.0
                state['current_z'] = z
                state['row_max_width'] = 0.0
                state['layer_max_height'] = 0.0
                return commit_place(state, unit, x, y, z, use_length, use_width, height, rotation, 'übereinander')

    return None


def create_loading_plan(
    units: pd.DataFrame,
    platforms: pd.DataFrame,
    base_wood_height: float,
    layer_spacer_height: float,
    gap_length: float,
    allow_beside: bool,
    allow_stack: bool,
    allow_rotation: bool,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Greedy-Verladevorschlag für eine einzelne Fuhre."""
    if units.empty or platforms.empty:
        return pd.DataFrame(), pd.DataFrame()

    active_platforms = platforms[platforms['Freigabe'] == True].copy()
    states = [init_platform_state(row, base_wood_height, layer_spacer_height, gap_length) for _, row in active_platforms.iterrows()]
    not_loaded: List[Dict[str, Any]] = []

    for _, unit in units.iterrows():
        placed = False
        for state in states:
            result = try_place_unit(
                state,
                unit,
                allow_beside=allow_beside,
                allow_stack=allow_stack,
                allow_rotation=allow_rotation,
            )
            if result is not None:
                placed = True
                break
        if not placed:
            not_loaded.append({
                'Fuhre_Nr': None,
                'Fuhrenoption': '',
                'Pritschenname': '',
                'Pritsche': 'NICHT VERLADEN',
                'Einheit_ID': unit['Einheit_ID'],
                'Typ': unit['Typ'],
                'Anzahl_Bauteile': int(unit['Anzahl_Bauteile']),
                'Bauteile': unit['Bauteile'],
                'X_mm': None,
                'Y_mm': None,
                'Z_mm': None,
                'Länge_mm': unit['Länge_mm'],
                'Breite_mm': unit['Breite_mm'],
                'Höhe_mm': unit['Höhe_mm'],
                'Drehung': None,
                'Ebene': 'nicht passend',
                'Gewicht_kg': round(float(unit['Gewicht_kg']), 2),
            })

    placements = []
    summary = []
    for state in states:
        placements.extend(state['placements'])
        summary.append({
            'Fuhre_Nr': state['Fuhre_Nr'],
            'Fuhrenoption': state['Fuhrenoption'],
            'Pritschenname': state['Pritschenname'],
            'Pritsche': state['Pritsche'],
            'Länge genutzt_mm': round(state['used_length'], 1),
            'Breite genutzt_mm': round(state['used_width'], 1),
            'Höhe genutzt_mm': round(state['used_height'], 1),
            'Gewicht genutzt_kg': round(state['total_weight'], 2),
            'Max Länge effektiv_mm': round(state['Eff_Länge_mm'], 1),
            'Max Breite_mm': round(state['Breite_mm'], 1),
            'Max Höhe_mm': round(state['Max_Höhe_mm'], 1),
            'Max Gewicht_kg': round(state['Max_Gewicht_kg'], 1),
        })

    placements.extend(not_loaded)
    return pd.DataFrame(placements), pd.DataFrame(summary)


def build_trip_platforms(pritschen_df: pd.DataFrame, fuhrenoption: str, fuhre_nr: int) -> pd.DataFrame:
    rows = pritschen_df[
        (pritschen_df['Fuhrenoption'].astype(str) == str(fuhrenoption)) &
        (pritschen_df['Freigabe'] == True)
    ].copy()
    if rows.empty:
        return rows
    rows = rows.sort_values('Pritschen_Reihenfolge', kind='stable').reset_index(drop=True)
    rows['Fuhre_Nr'] = fuhre_nr
    rows['Pritschenname'] = rows['Pritschenname'].astype(str)
    rows['Pritsche'] = rows.apply(lambda r: f"F{fuhre_nr:02d} {r['Pritschenname']}", axis=1)
    return rows


def create_variant_a_loading_plan(
    units: pd.DataFrame,
    options_df: pd.DataFrame,
    pritschen_df: pd.DataFrame,
    standards: Dict[str, Any],
    allow_beside: bool,
    allow_stack: bool,
    allow_rotation: bool,
    max_fuhren: int = 50,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Variante A: erste freigegebene passende Fuhrenoption wird wiederholt, bis alles verladen ist."""
    if units.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    enabled_options = options_df[options_df['Freigegeben'] == True].copy()
    enabled_options = enabled_options.sort_values('Priorität', kind='stable').reset_index(drop=True)

    remaining = units.copy().reset_index(drop=True)
    all_placements: List[pd.DataFrame] = []
    all_summary: List[pd.DataFrame] = []
    all_platforms: List[pd.DataFrame] = []
    fuhren_log: List[Dict[str, Any]] = []

    base_default = safe_number(standards.get('Standard_Kantholz_erste_Lage'), 80.0)
    layer_default = safe_number(standards.get('Standard_Einlage_zwischen_Lagen'), 40.0)
    # Im Moment nutzen wir den Versatz als X-Abstand/Versatzwert. Der freie Abstand kann später separat geführt werden.
    gap_default = safe_number(standards.get('Längenversatz_je_Lage'), 100.0)

    fuhre_nr = 1
    if enabled_options.empty:
        not_loaded = remaining.copy()
        not_loaded['Fuhre_Nr'] = None
        not_loaded['Fuhrenoption'] = ''
        not_loaded['Pritschenname'] = ''
        not_loaded['Pritsche'] = 'NICHT VERLADEN'
        not_loaded['X_mm'] = None
        not_loaded['Y_mm'] = None
        not_loaded['Z_mm'] = None
        not_loaded['Drehung'] = None
        not_loaded['Ebene'] = 'keine Fuhrenoption freigegeben'
        return not_loaded, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    while not remaining.empty and fuhre_nr <= max_fuhren:
        progress = False

        for _, option_row in enabled_options.iterrows():
            option_name = str(option_row['Fuhrenoption'])
            trip_platforms = build_trip_platforms(pritschen_df, option_name, fuhre_nr)
            if trip_platforms.empty:
                continue

            placements_try, summary_try = create_loading_plan(
                remaining,
                trip_platforms,
                base_wood_height=base_default,
                layer_spacer_height=layer_default,
                gap_length=gap_default,
                allow_beside=allow_beside,
                allow_stack=allow_stack,
                allow_rotation=allow_rotation,
            )

            if placements_try.empty:
                continue

            loaded_try = placements_try[placements_try['Pritsche'] != 'NICHT VERLADEN'].copy()
            loaded_ids = loaded_try['Einheit_ID'].dropna().astype(str).unique().tolist() if not loaded_try.empty else []

            if loaded_ids:
                all_placements.append(loaded_try)
                all_summary.append(summary_try)
                all_platforms.append(trip_platforms)
                fuhren_log.append({
                    'Fuhre_Nr': fuhre_nr,
                    'Fuhrenoption': option_name,
                    'Verladeeinheiten': len(loaded_ids),
                    'Gewicht_kg': round(float(loaded_try['Gewicht_kg'].sum()), 2),
                    'Pritschen': ', '.join(trip_platforms['Pritschenname'].astype(str).tolist()),
                })
                remaining = remaining[~remaining['Einheit_ID'].astype(str).isin(loaded_ids)].copy().reset_index(drop=True)
                progress = True
                fuhre_nr += 1
                break

        if not progress:
            break

    if not remaining.empty:
        not_loaded_rows = []
        for _, unit in remaining.iterrows():
            not_loaded_rows.append({
                'Fuhre_Nr': None,
                'Fuhrenoption': '',
                'Pritschenname': '',
                'Pritsche': 'NICHT VERLADEN',
                'Einheit_ID': unit['Einheit_ID'],
                'Typ': unit['Typ'],
                'Anzahl_Bauteile': int(unit['Anzahl_Bauteile']),
                'Bauteile': unit['Bauteile'],
                'X_mm': None,
                'Y_mm': None,
                'Z_mm': None,
                'Länge_mm': unit['Länge_mm'],
                'Breite_mm': unit['Breite_mm'],
                'Höhe_mm': unit['Höhe_mm'],
                'Drehung': None,
                'Ebene': 'passt in keine freigegebene Fuhrenoption',
                'Gewicht_kg': round(float(unit['Gewicht_kg']), 2),
            })
        all_placements.append(pd.DataFrame(not_loaded_rows))

    placements_df = pd.concat(all_placements, ignore_index=True) if all_placements else pd.DataFrame()
    summary_df = pd.concat(all_summary, ignore_index=True) if all_summary else pd.DataFrame()
    platforms_used_df = pd.concat(all_platforms, ignore_index=True) if all_platforms else pd.DataFrame()
    fuhren_log_df = pd.DataFrame(fuhren_log)
    return placements_df, summary_df, platforms_used_df, fuhren_log_df


def create_loading_excel(
    parts_df: pd.DataFrame,
    units_df: pd.DataFrame,
    placements_df: pd.DataFrame,
    platforms_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    options_df: Optional[pd.DataFrame] = None,
    fuhren_log_df: Optional[pd.DataFrame] = None,
) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        parts_df.to_excel(writer, sheet_name='Bauteile', index=False)
        units_df.to_excel(writer, sheet_name='Verladeeinheiten', index=False)
        placements_df.to_excel(writer, sheet_name='Platzierung', index=False)
        platforms_df.to_excel(writer, sheet_name='Pritschen_verwendet', index=False)
        summary_df.to_excel(writer, sheet_name='Pritschen_Summary', index=False)
        if options_df is not None and not options_df.empty:
            options_df.to_excel(writer, sheet_name='Fuhrenoptionen', index=False)
        if fuhren_log_df is not None and not fuhren_log_df.empty:
            fuhren_log_df.to_excel(writer, sheet_name='Fuhrenübersicht', index=False)
    return output.getvalue()


def draw_loading_view(placements_df: pd.DataFrame, platforms_df: pd.DataFrame, platform_name: str, view: str) -> go.Figure:
    platform_row = platforms_df[platforms_df['Pritsche'] == platform_name].iloc[0]
    eff_length = float(platform_row['Länge_mm']) + float(platform_row['Überhang_vorne_mm']) + float(platform_row['Überhang_hinten_mm'])
    width = float(platform_row['Breite_mm'])
    max_height = float(platform_row['Max_Höhe_mm'])

    loaded = placements_df[placements_df['Pritsche'] == platform_name].copy()
    loaded = loaded[loaded['X_mm'].notna() & loaded['Y_mm'].notna() & loaded['Z_mm'].notna()].copy()
    fig = go.Figure()

    title_prefix = {
        'top': 'Draufsicht',
        'side': 'Seitenansicht',
        'back': 'Rückansicht',
    }.get(view, 'Ansicht')

    if view == 'top':
        fig.update_layout(title=f'{title_prefix} - {platform_name}', xaxis_title='Länge X (mm)', yaxis_title='Breite Y (mm)')
        fig.add_shape(type='rect', x0=0, y0=0, x1=eff_length, y1=width, line=dict(width=2, dash='dash'))
        for _, row in loaded.iterrows():
            x0, y0 = float(row['X_mm']), float(row['Y_mm'])
            x1, y1 = x0 + float(row['Länge_mm']), y0 + float(row['Breite_mm'])
            fig.add_shape(type='rect', x0=x0, y0=y0, x1=x1, y1=y1, line=dict(width=1), fillcolor='rgba(100,100,100,0.18)')
            fig.add_annotation(x=(x0+x1)/2, y=(y0+y1)/2, text=str(row['Einheit_ID']), showarrow=False, font=dict(size=10))
        fig.update_yaxes(scaleanchor='x', scaleratio=1)

    elif view == 'side':
        fig.update_layout(title=f'{title_prefix} - {platform_name}', xaxis_title='Länge X (mm)', yaxis_title='Höhe Z (mm)')
        fig.add_shape(type='rect', x0=0, y0=0, x1=eff_length, y1=max_height, line=dict(width=2, dash='dash'))
        fig.add_shape(type='line', x0=0, y0=float(platform_row.get('Kantholz_erste_Lage_mm', 0)), x1=eff_length, y1=float(platform_row.get('Kantholz_erste_Lage_mm', 0)), line=dict(width=1, dash='dot'))
        for _, row in loaded.iterrows():
            x0, z0 = float(row['X_mm']), float(row['Z_mm'])
            x1, z1 = x0 + float(row['Länge_mm']), z0 + float(row['Höhe_mm'])
            fig.add_shape(type='rect', x0=x0, y0=z0, x1=x1, y1=z1, line=dict(width=1), fillcolor='rgba(100,100,100,0.18)')
            fig.add_annotation(x=(x0+x1)/2, y=(z0+z1)/2, text=str(row['Einheit_ID']), showarrow=False, font=dict(size=10))

    else:
        fig.update_layout(title=f'{title_prefix} - {platform_name}', xaxis_title='Breite Y (mm)', yaxis_title='Höhe Z (mm)')
        fig.add_shape(type='rect', x0=0, y0=0, x1=width, y1=max_height, line=dict(width=2, dash='dash'))
        fig.add_shape(type='line', x0=0, y0=float(platform_row.get('Kantholz_erste_Lage_mm', 0)), x1=width, y1=float(platform_row.get('Kantholz_erste_Lage_mm', 0)), line=dict(width=1, dash='dot'))
        for _, row in loaded.iterrows():
            y0, z0 = float(row['Y_mm']), float(row['Z_mm'])
            y1, z1 = y0 + float(row['Breite_mm']), z0 + float(row['Höhe_mm'])
            fig.add_shape(type='rect', x0=y0, y0=z0, x1=y1, y1=z1, line=dict(width=1), fillcolor='rgba(100,100,100,0.18)')
            fig.add_annotation(x=(y0+y1)/2, y=(z0+z1)/2, text=str(row['Einheit_ID']), showarrow=False, font=dict(size=10))

    fig.update_layout(height=450, showlegend=False, margin=dict(l=20, r=20, t=50, b=20))
    return fig


# =============================================================================
# Streamlit Bereiche
# =============================================================================

def render_analysis_module(uploaded_file) -> None:
    if uploaded_file is None:
        st.info('Bitte laden Sie eine BVX-Datei in der Seitenleiste hoch.')
        col1, col2 = st.columns(2)
        with col1:
            st.markdown('''
            ### Unterstützte Formate
            - XML Format BVX
            - Text Format BVX
            ''')
        with col2:
            st.markdown('''
            ### Erkannte Operationen
            - Bohrungen
            - Fräsungen
            - Sägeschnitte
            - weitere Operationen
            ''')
        return

    content = read_uploaded_text(uploaded_file)
    parser = BVXParser()
    result = parser.parse(content, uploaded_file.name)

    st.header('Übersicht')
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(label='Bauteile', value=result.part_count)
    col2.metric(label='Operationstypen', value=result.operation_count, delta=f'{result.total_operation_count} gesamt')
    col3.metric(label='Bauteilvolumen', value=format_volume(result.total_volume))
    col4.metric(label='Bearbeitetes Volumen', value=format_volume(result.machined_volume))

    if result.part_dimensions:
        st.subheader('Bauteilabmessungen erstes Bauteil')
        dims = result.part_dimensions
        col1, col2, col3 = st.columns(3)
        col1.info(f"**Länge:** {dims['length']:.1f} mm")
        col2.info(f"**Breite:** {dims['width']:.1f} mm")
        col3.info(f"**Höhe:** {dims['height']:.1f} mm")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(['Bauteile', 'Operationstabelle', 'Diagramme', 'Positionsübersicht', 'Export'])

    with tab1:
        st.subheader('Bauteilliste')
        parts_df = parts_to_dataframe(result.parts, density_kg_m3=500)
        st.dataframe(parts_df, use_container_width=True, hide_index=True)

    with tab2:
        st.subheader('Bearbeitungen Details')
        col1, col2 = st.columns([1, 2])
        with col1:
            operation_types = sorted(set(op.op_type for op in result.operations))
            selected_type = st.selectbox('Nach Typ filtern', ['Alle'] + operation_types, key='filter_type')
        with col2:
            search_term = st.text_input('Suchen...', key='search', placeholder='Typ, Durchmesser oder Tiefe')

        filtered_ops = result.operations
        if selected_type != 'Alle':
            filtered_ops = [op for op in filtered_ops if op.op_type == selected_type]
        if search_term:
            search_lower = search_term.lower()
            filtered_ops = [op for op in filtered_ops if
                            search_lower in op.op_type.lower() or
                            (op.diameter and search_lower in str(op.diameter)) or
                            (op.depth and search_lower in str(op.depth))]

        df_data = []
        for op in filtered_ops:
            df_data.append({
                'Typ': op.op_type,
                'Anzahl': op.count,
                'Durchmesser (mm)': f'{op.diameter:.1f}' if op.diameter else '-',
                'Länge/Tiefe (mm)': f'{op.depth:.1f}' if op.depth else '-',
                'Volumen': format_volume(op.volume),
            })
        df = pd.DataFrame(df_data)
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
            total_ops = sum(op.count for op in filtered_ops)
            st.caption(f'Zeigt {len(filtered_ops)} Operationstypen ({total_ops} Operationen gesamt)')
        else:
            st.warning('Keine Operationen gefunden.')

    with tab3:
        st.subheader('Visualisierungen')
        col1, col2 = st.columns(2)
        with col1:
            type_counts = Counter(op.op_type for op in result.operations for _ in range(op.count))
            if type_counts:
                fig_pie = px.pie(values=list(type_counts.values()), names=list(type_counts.keys()), title='Operationen nach Typ', hole=0.4)
                st.plotly_chart(fig_pie, use_container_width=True)
        with col2:
            volume_by_type: Dict[str, float] = {}
            for op in result.operations:
                volume_by_type[op.op_type] = volume_by_type.get(op.op_type, 0) + op.volume
            if volume_by_type:
                fig_bar = px.bar(
                    x=list(volume_by_type.keys()),
                    y=[v * 1_000_000 for v in volume_by_type.values()],
                    title='Volumen nach Operationstyp (mm³)',
                    labels={'x': 'Operationstyp', 'y': 'Volumen (mm³)'},
                )
                st.plotly_chart(fig_bar, use_container_width=True)

        diameters = [op.diameter for op in result.operations if op.diameter and op.diameter > 0]
        if diameters:
            fig_hist = px.histogram(x=diameters, nbins=20, title='Verteilung der Durchmesser', labels={'x': 'Durchmesser (mm)', 'y': 'Anzahl'})
            st.plotly_chart(fig_hist, use_container_width=True)

    with tab4:
        st.subheader('2D Positionsübersicht')
        ops_with_pos = [op for op in result.operations if op.x is not None and op.y is not None]
        if ops_with_pos:
            fig_scatter = go.Figure()
            for op_type in set(op.op_type for op in ops_with_pos):
                type_ops = [op for op in ops_with_pos if op.op_type == op_type]
                fig_scatter.add_trace(go.Scatter(
                    x=[op.x for op in type_ops],
                    y=[op.y for op in type_ops],
                    mode='markers',
                    name=op_type,
                    marker=dict(size=10),
                    text=[f'{op.op_type}<br>D: {op.diameter or "-"} mm' for op in type_ops],
                    hovertemplate='<b>%{text}</b><br>X: %{x}<br>Y: %{y}<extra></extra>'
                ))
            if result.part_dimensions:
                dims = result.part_dimensions
                fig_scatter.add_shape(type='rect', x0=0, y0=0, x1=dims['length'], y1=dims['width'], line=dict(dash='dash'))
            fig_scatter.update_layout(title='Operationspositionen auf Bauteil', xaxis_title='X Position (mm)', yaxis_title='Y Position (mm)', showlegend=True, height=500)
            st.plotly_chart(fig_scatter, use_container_width=True)
        else:
            st.info('Keine Positionsdaten in der BVX-Datei vorhanden.')

    with tab5:
        st.subheader('Daten exportieren')
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
        parts_df = parts_to_dataframe(result.parts, density_kg_m3=500)

        col1, col2 = st.columns(2)
        with col1:
            csv = df_export.to_csv(index=False)
            st.download_button(
                label='CSV herunterladen',
                data=csv,
                file_name=f"{result.file_name.replace('.bvx', '').replace('.BVX', '')}_analyse.csv",
                mime='text/csv',
            )
        with col2:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                parts_df.to_excel(writer, sheet_name='Bauteile', index=False)
                df_export.to_excel(writer, sheet_name='Operationen', index=False)
                summary_data = {
                    'Eigenschaft': ['Dateiname', 'Anzahl Bauteile', 'Anzahl Operationstypen', 'Gesamtoperationen', 'Bauteilvolumen (m³)', 'Bearbeitetes Volumen (m³)'],
                    'Wert': [result.file_name, result.part_count, result.operation_count, result.total_operation_count, result.total_volume, result.machined_volume]
                }
                pd.DataFrame(summary_data).to_excel(writer, sheet_name='Zusammenfassung', index=False)
            st.download_button(
                label='Excel herunterladen',
                data=output.getvalue(),
                file_name=f"{result.file_name.replace('.bvx', '').replace('.BVX', '')}_analyse.xlsx",
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )


def render_loading_module(uploaded_file, transport_excel_file=None) -> None:
    st.header('Verladeplanung')

    if uploaded_file is None:
        st.info('Bitte laden Sie links eine BVX-Datei für die Verladeplanung hoch.')
        st.markdown('''
        Die Verladeplanung ist getrennt von der normalen BVX-Auswertung aufgebaut.
        Sie arbeitet mit Bauteilen, Verladeeinheiten, Bunden, Fuhrenoptionen, Pritschen und Positionen.
        ''')
        return

    options_df, pritschen_df, standards, config_messages = read_transport_config_excel(transport_excel_file)
    for msg in config_messages:
        st.warning(msg)

    if transport_excel_file is not None:
        st.success(f'Pritschen-/Fuhren-Stammdaten geladen: {transport_excel_file.name}')
    else:
        st.info('Noch keine Excel-Stammdaten geladen. Es werden nur Beispielwerte verwendet.')

    content = read_uploaded_text(uploaded_file)
    parser = BVXParser()
    result = parser.parse(content, uploaded_file.name)

    st.subheader('1. Grunddaten aus BVX und Excel')
    default_density = safe_number(standards.get('Holzdichte'), 500.0)
    default_bundle_weight = safe_number(standards.get('Max_Bundgewicht'), 1000.0)
    default_base_wood = safe_number(standards.get('Standard_Kantholz_erste_Lage'), 80.0)
    default_layer_spacer = safe_number(standards.get('Standard_Einlage_zwischen_Lagen'), 40.0)
    default_gap = safe_number(standards.get('Längenversatz_je_Lage'), 100.0)

    col1, col2, col3 = st.columns(3)
    density = col1.number_input('Holzdichte kg/m³', min_value=100.0, max_value=1000.0, value=float(default_density), step=10.0)
    max_bundle_weight = col2.number_input('Max. Bundgewicht kg', min_value=100.0, max_value=5000.0, value=float(default_bundle_weight), step=50.0)
    use_bundles = col3.checkbox('Bunde automatisch bilden', value=True)

    parts_df = parts_to_dataframe(result.parts, density_kg_m3=density)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric('Bauteile', len(parts_df))
    col2.metric('Gesamtvolumen', f"{parts_df['Volumen_m3'].sum():.3f} m³")
    col3.metric('Gesamtgewicht', f"{parts_df['Gewicht_kg'].sum():.0f} kg")
    col4.metric('Excel-Fuhrenoptionen', int(options_df['Freigegeben'].sum()) if not options_df.empty else 0)

    st.subheader('2. Sortierung')
    sort_options = [
        'Bauteilnummer', 'Pak/Unit', 'Name', 'PartId', 'Profil', 'Oberfläche', 'Qualität',
        'Länge_mm', 'Breite_mm', 'Höhe_mm', 'Gewicht_kg', 'Volumen_m3'
    ]
    col1, col2, col3, col4 = st.columns(4)
    main_attr = col1.selectbox('Hauptattribut', sort_options, index=0)
    main_direction = col2.selectbox('Richtung Hauptattribut', ['aufsteigend', 'absteigend'], index=0)
    second_attr = col3.selectbox('Nebenattribut', ['Keine'] + sort_options, index=0)
    second_direction = col4.selectbox('Richtung Nebenattribut', ['aufsteigend', 'absteigend'], index=0)

    sorted_parts = sort_parts_dataframe(
        parts_df,
        main_attr=main_attr,
        main_asc=(main_direction == 'aufsteigend'),
        second_attr=second_attr,
        second_asc=(second_direction == 'aufsteigend'),
    )

    with st.expander('Bauteile anzeigen', expanded=False):
        st.dataframe(sorted_parts, use_container_width=True, hide_index=True)

    st.subheader('3. Bund- und Unterlegholz-Einstellungen')
    col1, col2, col3 = st.columns(3)
    base_wood_height = col1.number_input('Standard Kantholz erste Lage mm', min_value=0.0, max_value=300.0, value=float(default_base_wood), step=5.0)
    bundle_spacer_height = col2.number_input('Standard Bundeinlage / Lagenholz mm', min_value=0.0, max_value=200.0, value=float(default_layer_spacer), step=5.0)
    gap_length = col3.number_input('Längenversatz je Lage mm', min_value=0.0, max_value=500.0, value=float(default_gap), step=10.0)

    # Standards werden für die Berechnung aktualisiert. Pritschenwerte aus Excel überschreiben diese Defaults pro Pritsche.
    standards['Holzdichte'] = density
    standards['Max_Bundgewicht'] = max_bundle_weight
    standards['Standard_Kantholz_erste_Lage'] = base_wood_height
    standards['Standard_Einlage_zwischen_Lagen'] = bundle_spacer_height
    standards['Längenversatz_je_Lage'] = gap_length

    col1, col2, col3, col4 = st.columns(4)
    same_height = col1.checkbox('Nur gleiche Höhe im Bund', value=True)
    same_width = col2.checkbox('Nur gleiche Breite im Bund', value=False)
    same_quality = col3.checkbox('Nur gleiche Qualität im Bund', value=False)
    same_profile = col4.checkbox('Nur gleiches Profil im Bund', value=False)

    units_df = build_loading_units(
        sorted_parts,
        use_bundles=use_bundles,
        max_bundle_weight=max_bundle_weight,
        bundle_spacer_height=bundle_spacer_height,
        same_height=same_height,
        same_width=same_width,
        same_quality=same_quality,
        same_profile=same_profile,
    )

    st.subheader('4. Fuhrenoptionen und Pritschen aus Excel')
    st.caption('Variante A: Die freigegebenen Fuhrenoptionen werden nach Priorität geprüft. Die erste passende Option wird wiederholt, bis alles verladen ist.')

    fcol1, fcol2 = st.columns([1, 2])
    with fcol1:
        options_edit = st.data_editor(
            options_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                'Freigegeben': st.column_config.CheckboxColumn('Freigegeben'),
                'Wiederholen_bis_alles_verladen': st.column_config.CheckboxColumn('Wiederholen'),
                'Priorität': st.column_config.NumberColumn('Priorität'),
            },
            key='fuhrenoptionen_editor',
        )
    with fcol2:
        pritschen_edit = st.data_editor(
            pritschen_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                'Freigabe': st.column_config.CheckboxColumn('Aktiv'),
                'Drehen_90_erlaubt': st.column_config.CheckboxColumn('Drehen 90°'),
                'Pritschen_Reihenfolge': st.column_config.NumberColumn('Reihenfolge'),
                'Länge_mm': st.column_config.NumberColumn('Länge mm'),
                'Breite_mm': st.column_config.NumberColumn('Breite mm'),
                'Max_Höhe_mm': st.column_config.NumberColumn('Max. Höhe mm'),
                'Max_Gewicht_kg': st.column_config.NumberColumn('Max. Gewicht kg'),
            },
            key='pritschen_editor_excel',
        )

    st.subheader('5. Platzierung / Automatik')
    col1, col2, col3, col4 = st.columns(4)
    allow_beside = col1.checkbox('Nebeneinander erlauben', value=True)
    allow_stack = col2.checkbox('Übereinander erlauben', value=True)
    allow_rotation = col3.checkbox('90° drehen erlauben, wenn Pritsche es erlaubt', value=False)
    max_fuhren = col4.number_input('Max. Fuhren Sicherheitslimit', min_value=1, max_value=200, value=50, step=1)

    placements_df, summary_df, platforms_used_df, fuhren_log_df = create_variant_a_loading_plan(
        units_df,
        options_edit,
        pritschen_edit,
        standards=standards,
        allow_beside=allow_beside,
        allow_stack=allow_stack,
        allow_rotation=allow_rotation,
        max_fuhren=int(max_fuhren),
    )

    loaded_count = int((placements_df['Pritsche'] != 'NICHT VERLADEN').sum()) if not placements_df.empty and 'Pritsche' in placements_df.columns else 0
    not_loaded_count = int((placements_df['Pritsche'] == 'NICHT VERLADEN').sum()) if not placements_df.empty and 'Pritsche' in placements_df.columns else 0
    fuhren_count = int(fuhren_log_df['Fuhre_Nr'].nunique()) if not fuhren_log_df.empty else 0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric('Verladeeinheiten', len(units_df))
    col2.metric('Fuhren erzeugt', fuhren_count)
    col3.metric('Verladen', loaded_count)
    col4.metric('Nicht verladen', not_loaded_count)
    col5.metric('Pritschen genutzt', len(platforms_used_df) if not platforms_used_df.empty else 0)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(['Verladeeinheiten', 'Fuhrenübersicht', 'Platzierung', 'Ansichten', 'Export'])

    with tab1:
        st.dataframe(units_df, use_container_width=True, hide_index=True)
        warnings_df = units_df[units_df['Warnung'] != ''] if not units_df.empty and 'Warnung' in units_df.columns else pd.DataFrame()
        if not warnings_df.empty:
            st.warning('Einige Verladeeinheiten überschreiten das definierte Bundgewicht.')
            st.dataframe(warnings_df, use_container_width=True, hide_index=True)

    with tab2:
        if not fuhren_log_df.empty:
            st.dataframe(fuhren_log_df, use_container_width=True, hide_index=True)
        else:
            st.warning('Es wurde keine Fuhre erzeugt.')
        st.markdown('**Pritschen-Zusammenfassung**')
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

    with tab3:
        st.markdown('**Platzierung der Verladeeinheiten**')
        st.dataframe(placements_df, use_container_width=True, hide_index=True)
        if not_loaded_count:
            st.error('Nicht alle Verladeeinheiten konnten automatisch platziert werden. Freigegebene Fuhrenoptionen, Pritschenmaße oder Bundbildung prüfen.')

    with tab4:
        if platforms_used_df.empty:
            st.warning('Keine Pritsche für die Ansicht vorhanden.')
        else:
            selected_platform = st.selectbox('Fuhre / Pritsche für Ansicht', platforms_used_df['Pritsche'].tolist())
            info_row = summary_df[summary_df['Pritsche'] == selected_platform]
            if not info_row.empty:
                row = info_row.iloc[0]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric('Länge genutzt', f"{row['Länge genutzt_mm']:.0f} mm")
                c2.metric('Breite genutzt', f"{row['Breite genutzt_mm']:.0f} mm")
                c3.metric('Höhe genutzt', f"{row['Höhe genutzt_mm']:.0f} mm")
                c4.metric('Gewicht', f"{row['Gewicht genutzt_kg']:.0f} kg")

            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(draw_loading_view(placements_df, platforms_used_df, selected_platform, 'side'), use_container_width=True)
            with col2:
                st.plotly_chart(draw_loading_view(placements_df, platforms_used_df, selected_platform, 'back'), use_container_width=True)
            st.plotly_chart(draw_loading_view(placements_df, platforms_used_df, selected_platform, 'top'), use_container_width=True)

    with tab5:
        excel_data = create_loading_excel(
            sorted_parts,
            units_df,
            placements_df,
            platforms_used_df,
            summary_df,
            options_df=options_edit,
            fuhren_log_df=fuhren_log_df,
        )
        st.download_button(
            label='Verladeplanung als Excel herunterladen',
            data=excel_data,
            file_name=f"{uploaded_file.name.replace('.bvx', '').replace('.BVX', '')}_verladeplanung.xlsx",
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        st.markdown('''
        **Hinweis:** Diese Version erstellt einen automatischen Grobvorschlag mit Variante A.
        Manuelles Umplatzieren per Tabelle/Drag-and-drop ist der nächste Ausbauschritt.
        ''')


def main():
    st.set_page_config(
        page_title='BVX Auswertung / Verladeplanung',
        page_icon='🔧',
        layout='wide',
        initial_sidebar_state='expanded'
    )

    st.markdown('''
        <style>
        .main-header {
            font-size: 2.2rem;
            font-weight: bold;
            color: #1a1a2e;
            margin-bottom: 1rem;
        }
        </style>
    ''', unsafe_allow_html=True)

    st.markdown('<p class="main-header">BVX Auswertung / Verladeplanung</p>', unsafe_allow_html=True)

    with st.sidebar:
        st.header('Modul')
        module = st.radio('Bereich wählen', ['BVX Auswertung', 'Verladeplanung'], index=0)

        st.divider()
        if module == 'BVX Auswertung':
            st.subheader('BVX Analyse Import')
            analysis_file = st.file_uploader(
                'BVX-Datei für Analyse hochladen',
                type=['bvx', 'BVX'],
                key='analysis_upload',
                help='Normale BVX-Auswertung mit Operationen und Export.'
            )
            loading_file = None
            if analysis_file:
                st.success(f'{analysis_file.name}')
        else:
            st.subheader('Verlade Import')
            loading_file = st.file_uploader(
                'BVX-Datei für Verladung hochladen',
                type=['bvx', 'BVX'],
                key='loading_upload',
                help='Eigenständiger Import für Verladeplanung.'
            )
            transport_excel_file = st.file_uploader(
                'Excel Pritschen/Fuhren laden',
                type=['xlsx'],
                key='transport_excel_upload',
                help='Stammdaten mit Fuhrenoptionen, Pritschen und Standards.'
            )
            analysis_file = None
            if loading_file:
                st.success(f'BVX: {loading_file.name}')
            if transport_excel_file:
                st.success(f'Excel: {transport_excel_file.name}')

    if module == 'BVX Auswertung':
        render_analysis_module(analysis_file)
    else:
        render_loading_module(loading_file, transport_excel_file)


if __name__ == '__main__':
    main()
