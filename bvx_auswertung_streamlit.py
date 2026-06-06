"""
BVX Auswertung + Verladeplanung - Streamlit Version

Installation:
    pip install streamlit pandas plotly openpyxl reportlab

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
from datetime import datetime


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


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Entfernt unsichtbare Leerzeichen aus Excel-Spaltennamen."""
    result = df.copy()
    result.columns = [str(col).strip().replace('\n', ' ') for col in result.columns]
    return result


def get_transport_presets() -> Dict[str, List[Dict[str, Any]]]:
    """Fallback-Stammdaten, falls keine Excel-Vorlage geladen wird."""
    return {
        'LKW solo': [
            {'Freigabe': True, 'Pritsche': 'LKW', 'Pritschenname': 'LKW', 'Fuhrenoption': 'LKW solo', 'Pritschen_Reihenfolge': 1,
             'Länge_mm': 9300, 'Breite_mm': 2450, 'Max_Höhe_mm': 2600, 'Überhang_vorne_mm': 0,
             'Überhang_hinten_mm': 300, 'Max_Gewicht_kg': 15000, 'Kantholz_erste_Lage_mm': 80,
             'Einlage_zwischen_Lagen_mm': 40, 'Einlage_allgemein_mm': 0, 'Drehen_90_erlaubt': False},
        ],
        'LKW mit Anhänger': [
            {'Freigabe': True, 'Pritsche': 'LKW', 'Pritschenname': 'LKW', 'Fuhrenoption': 'LKW mit Anhänger', 'Pritschen_Reihenfolge': 1,
             'Länge_mm': 9300, 'Breite_mm': 2450, 'Max_Höhe_mm': 2600, 'Überhang_vorne_mm': 0,
             'Überhang_hinten_mm': 300, 'Max_Gewicht_kg': 15000, 'Kantholz_erste_Lage_mm': 80,
             'Einlage_zwischen_Lagen_mm': 40, 'Einlage_allgemein_mm': 0, 'Drehen_90_erlaubt': False},
            {'Freigabe': True, 'Pritsche': 'Anhänger', 'Pritschenname': 'Anhänger', 'Fuhrenoption': 'LKW mit Anhänger', 'Pritschen_Reihenfolge': 2,
             'Länge_mm': 8200, 'Breite_mm': 2450, 'Max_Höhe_mm': 2600, 'Überhang_vorne_mm': 0,
             'Überhang_hinten_mm': 300, 'Max_Gewicht_kg': 12000, 'Kantholz_erste_Lage_mm': 80,
             'Einlage_zwischen_Lagen_mm': 40, 'Einlage_allgemein_mm': 0, 'Drehen_90_erlaubt': False},
        ],
        'Anhängerzug': [
            {'Freigabe': True, 'Pritsche': 'LKW', 'Pritschenname': 'LKW', 'Fuhrenoption': 'Anhängerzug', 'Pritschen_Reihenfolge': 1,
             'Länge_mm': 7600, 'Breite_mm': 2450, 'Max_Höhe_mm': 2600, 'Überhang_vorne_mm': 0,
             'Überhang_hinten_mm': 300, 'Max_Gewicht_kg': 12000, 'Kantholz_erste_Lage_mm': 80,
             'Einlage_zwischen_Lagen_mm': 40, 'Einlage_allgemein_mm': 0, 'Drehen_90_erlaubt': False},
            {'Freigabe': True, 'Pritsche': 'Anhänger', 'Pritschenname': 'Anhänger', 'Fuhrenoption': 'Anhängerzug', 'Pritschen_Reihenfolge': 2,
             'Länge_mm': 8200, 'Breite_mm': 2450, 'Max_Höhe_mm': 2600, 'Überhang_vorne_mm': 0,
             'Überhang_hinten_mm': 300, 'Max_Gewicht_kg': 12000, 'Kantholz_erste_Lage_mm': 80,
             'Einlage_zwischen_Lagen_mm': 40, 'Einlage_allgemein_mm': 0, 'Drehen_90_erlaubt': False},
        ],
        'Tiefbettauflieger': [
            {'Freigabe': True, 'Pritsche': 'Tiefbett', 'Pritschenname': 'Tiefbett', 'Fuhrenoption': 'Tiefbettauflieger', 'Pritschen_Reihenfolge': 1,
             'Länge_mm': 13000, 'Breite_mm': 2550, 'Max_Höhe_mm': 3200, 'Überhang_vorne_mm': 500,
             'Überhang_hinten_mm': 1000, 'Max_Gewicht_kg': 24000, 'Kantholz_erste_Lage_mm': 100,
             'Einlage_zwischen_Lagen_mm': 40, 'Einlage_allgemein_mm': 0, 'Drehen_90_erlaubt': True},
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
        'Standard_Einlage_allgemein': 0.0,
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
        options_raw = normalize_columns(pd.read_excel(xls, sheet_name='Fuhrenoptionen'))
        pritschen_raw = normalize_columns(pd.read_excel(xls, sheet_name='Pritschen'))
        standards_raw = normalize_columns(pd.read_excel(xls, sheet_name='Standards'))
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
        'Kantholz_erste_Lage_mm', 'Einlage_zwischen_Lagen_mm', 'Einlage_allgemein_mm', 'Drehen_90_erlaubt'
    ]
    for col in required_cols:
        if col not in p.columns:
            p[col] = ''

    p = p[p['Fuhrenoption'].notna() & (p['Fuhrenoption'].astype(str).str.strip() != '')].copy()
    p['Freigabe'] = p['Freigabe'].apply(yes_no_to_bool)
    p['Drehen_90_erlaubt'] = p['Drehen_90_erlaubt'].apply(yes_no_to_bool)
    p['Pritschen_Reihenfolge'] = p['Pritschen_Reihenfolge'].apply(lambda v: int(safe_number(v, 999)))
    for col in ['Länge_mm', 'Breite_mm', 'Max_Höhe_mm', 'Max_Gewicht_kg', 'Überhang_vorne_mm', 'Überhang_hinten_mm', 'Kantholz_erste_Lage_mm', 'Einlage_zwischen_Lagen_mm', 'Einlage_allgemein_mm']:
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


def _format_label_value(value: Any) -> str:
    """Formatiert Werte für die Anzeige in Ansichten und Pritschenplan."""
    if value is None:
        return ''
    try:
        if pd.isna(value):
            return ''
    except Exception:
        pass
    if isinstance(value, (int, float)):
        val = float(value)
        if abs(val - round(val)) < 0.001:
            return str(int(round(val)))
        return f'{val:.2f}'.rstrip('0').rstrip('.')
    text = str(value).strip()
    if text.lower() == 'nan':
        return ''
    return text


def _part_display_label(row: pd.Series, label_attr: str) -> str:
    """Liefert den Wert des ausgewählten Hauptattributes für die visuelle Ansicht."""
    label = _format_label_value(row.get(label_attr)) if label_attr else ''
    if not label:
        label = _format_label_value(row.get('Bauteilnummer'))
    if not label:
        label = _format_label_value(row.get('Name'))
    return label or 'Bauteil'


def build_loading_units(
    sorted_parts: pd.DataFrame,
    use_bundles: bool,
    max_bundle_weight: float,
    bundle_spacer_height: float,
    general_spacer_height: float,
    same_height: bool,
    same_width: bool,
    same_quality: bool,
    same_profile: bool,
    label_attr: str = 'Bauteilnummer',
) -> pd.DataFrame:
    """Erzeugt Verladeeinheiten: einzelnes Bauteil oder Bund."""
    if sorted_parts.empty:
        return pd.DataFrame()

    units: List[Dict[str, Any]] = []

    if not use_bundles:
        for idx, row in sorted_parts.iterrows():
            default_label = str(row.get('Bauteilnummer') or row.get('Name'))
            view_label = _part_display_label(row, label_attr)
            units.append({
                'Einheit_ID': f'E{idx + 1:03d}',
                'Typ': 'Bauteil',
                'Anzahl_Bauteile': 1,
                'Bauteile': default_label,
                'Bauteile_Liste': default_label,
                'Ansicht_Attribut': label_attr,
                'Ansicht_Label': view_label,
                'Ansicht_Liste': view_label,
                'Einzellängen_mm': str(row['Länge_mm']),
                'Einzelbreiten_mm': str(row['Breite_mm']),
                'Einzelhöhen_mm': str(row['Höhe_mm']),
                'Einlage_allgemein_mm': float(general_spacer_height),
                'Bundeinlage_mm': float(bundle_spacer_height),
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
        internal_spacer = general_spacer_height if general_spacer_height > 0 else bundle_spacer_height
        height = sum(float(r['Höhe_mm']) for r in current_rows) + max(0, count - 1) * internal_spacer
        volume = sum(float(r['Volumen_m3']) for r in current_rows)
        weight = sum(float(r['Gewicht_kg']) for r in current_rows)
        part_labels = [str(r.get('Bauteilnummer') or r.get('Name')) for r in current_rows]
        view_labels = [_part_display_label(r, label_attr) for r in current_rows]
        view_list = '|'.join(view_labels)
        if len(view_labels) <= 3:
            view_label = ', '.join(view_labels)
        else:
            view_label = ', '.join(view_labels[:3]) + ' ...'
        part_lengths = [str(float(r['Länge_mm'])) for r in current_rows]
        part_widths = [str(float(r['Breite_mm'])) for r in current_rows]
        part_heights = [str(float(r['Höhe_mm'])) for r in current_rows]
        units.append({
            'Einheit_ID': f'B{len(units) + 1:03d}',
            'Typ': 'Bund' if count > 1 else 'Bauteil',
            'Anzahl_Bauteile': count,
            'Bauteile': ', '.join(part_labels),
            'Bauteile_Liste': '|'.join(part_labels),
            'Ansicht_Attribut': label_attr,
            'Ansicht_Label': view_label,
            'Ansicht_Liste': view_list,
            'Einzellängen_mm': '|'.join(part_lengths),
            'Einzelbreiten_mm': '|'.join(part_widths),
            'Einzelhöhen_mm': '|'.join(part_heights),
            'Einlage_allgemein_mm': float(general_spacer_height),
            'Bundeinlage_mm': float(bundle_spacer_height),
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
        'general_spacer_height': float(row.get('Einlage_allgemein_mm', 0.0) or 0.0),
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
        'Bauteile_Liste': unit.get('Bauteile_Liste', unit.get('Bauteile', '')),
        'Ansicht_Attribut': unit.get('Ansicht_Attribut', ''),
        'Ansicht_Label': unit.get('Ansicht_Label', unit.get('Einheit_ID', '')),
        'Ansicht_Liste': unit.get('Ansicht_Liste', unit.get('Ansicht_Label', '')),
        'Einzellängen_mm': unit.get('Einzellängen_mm', ''),
        'Einzelbreiten_mm': unit.get('Einzelbreiten_mm', ''),
        'Einzelhöhen_mm': unit.get('Einzelhöhen_mm', ''),
        'Einlage_allgemein_mm': safe_number(unit.get('Einlage_allgemein_mm'), 0.0),
        'Bundeinlage_mm': safe_number(unit.get('Bundeinlage_mm'), 0.0),
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
            effective_layer_spacer = max(float(state.get('layer_spacer_height', 0.0)), float(state.get('general_spacer_height', 0.0)))
            z = state['current_z'] + state['layer_max_height'] + effective_layer_spacer
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
                'Bauteile_Liste': unit.get('Bauteile_Liste', unit.get('Bauteile', '')),
                'Ansicht_Attribut': unit.get('Ansicht_Attribut', ''),
                'Ansicht_Label': unit.get('Ansicht_Label', unit.get('Einheit_ID', '')),
                'Ansicht_Liste': unit.get('Ansicht_Liste', unit.get('Ansicht_Label', '')),
                'Einzellängen_mm': unit.get('Einzellängen_mm', ''),
                'Einzelbreiten_mm': unit.get('Einzelbreiten_mm', ''),
                'Einzelhöhen_mm': unit.get('Einzelhöhen_mm', ''),
                'Einlage_allgemein_mm': safe_number(unit.get('Einlage_allgemein_mm'), 0.0),
                'Bundeinlage_mm': safe_number(unit.get('Bundeinlage_mm'), 0.0),
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


def center_placements_geometrically(placements_df: pd.DataFrame, platforms_df: pd.DataFrame) -> pd.DataFrame:
    """Richtet platzierte Einheiten geometrisch mittig auf der Pritsche aus.

    Wichtig: Das ist bewusst keine Gewichts- oder Schwerpunktoptimierung.
    Die bestehende Reihenfolge und Stapellogik bleibt erhalten. Es wird nur die
    fertige Platzierung je Lage in X- und Y-Richtung in die Mitte der jeweiligen
    Pritsche verschoben.
    """
    if placements_df.empty or platforms_df.empty:
        return placements_df

    result = placements_df.copy()
    if 'Pritsche' not in result.columns:
        return result

    # Nur sauber platzierte Zeilen ausrichten. Nicht-verladene Zeilen bleiben unverändert.
    numeric_cols = ['X_mm', 'Y_mm', 'Z_mm', 'Länge_mm', 'Breite_mm', 'Höhe_mm']
    for col in numeric_cols:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors='coerce')

    platform_lookup = {
        str(row.get('Pritsche', '')): row
        for _, row in platforms_df.iterrows()
    }

    for platform_name, platform_row in platform_lookup.items():
        if not platform_name or platform_name == 'NICHT VERLADEN':
            continue

        eff_length = (
            safe_number(platform_row.get('Länge_mm'))
            + safe_number(platform_row.get('Überhang_vorne_mm'))
            + safe_number(platform_row.get('Überhang_hinten_mm'))
        )
        platform_width = safe_number(platform_row.get('Breite_mm'))
        if eff_length <= 0 or platform_width <= 0:
            continue

        mask_platform = (
            result['Pritsche'].astype(str).eq(platform_name)
            & result['X_mm'].notna()
            & result['Y_mm'].notna()
            & result['Z_mm'].notna()
            & result['Länge_mm'].notna()
            & result['Breite_mm'].notna()
        )
        if not mask_platform.any():
            continue

        # Je Lage mittig ausrichten. Eine Lage ist hier die gleiche Z-Position.
        layer_keys = result.loc[mask_platform, 'Z_mm'].round(1).unique().tolist()
        for layer_key in layer_keys:
            layer_mask = mask_platform & result['Z_mm'].round(1).eq(layer_key)
            if not layer_mask.any():
                continue

            x0 = result.loc[layer_mask, 'X_mm'].min()
            x1 = (result.loc[layer_mask, 'X_mm'] + result.loc[layer_mask, 'Länge_mm']).max()
            y0 = result.loc[layer_mask, 'Y_mm'].min()
            y1 = (result.loc[layer_mask, 'Y_mm'] + result.loc[layer_mask, 'Breite_mm']).max()

            span_x = x1 - x0
            span_y = y1 - y0

            if 0 < span_x <= eff_length:
                shift_x = (eff_length - span_x) / 2 - x0
                result.loc[layer_mask, 'X_mm'] = (result.loc[layer_mask, 'X_mm'] + shift_x).round(1)

            if 0 < span_y <= platform_width:
                shift_y = (platform_width - span_y) / 2 - y0
                result.loc[layer_mask, 'Y_mm'] = (result.loc[layer_mask, 'Y_mm'] + shift_y).round(1)

            if 'Ebene' in result.columns:
                result.loc[layer_mask, 'Ebene'] = result.loc[layer_mask, 'Ebene'].astype(str).apply(
                    lambda v: v if 'mittig' in v.lower() else f'{v} / geometrisch mittig'
                )

    return result


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
    center_geometric: bool = True,
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
    general_default = safe_number(standards.get('Standard_Einlage_allgemein'), 0.0)
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
            trip_platforms = trip_platforms.copy()
            # Die aktuellen App-Einstellungen sind führend. Damit erscheinen keine alten
            # Einlagewerte aus einer Excel-Stammdatendatei im Pritschenzettel.
            trip_platforms['Kantholz_erste_Lage_mm'] = base_default
            trip_platforms['Einlage_zwischen_Lagen_mm'] = layer_default
            trip_platforms['Einlage_allgemein_mm'] = general_default

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
                'Bauteile_Liste': unit.get('Bauteile_Liste', unit.get('Bauteile', '')),
                'Ansicht_Attribut': unit.get('Ansicht_Attribut', ''),
                'Ansicht_Label': unit.get('Ansicht_Label', unit.get('Einheit_ID', '')),
                'Ansicht_Liste': unit.get('Ansicht_Liste', unit.get('Ansicht_Label', '')),
                'Einzellängen_mm': unit.get('Einzellängen_mm', ''),
                'Einzelbreiten_mm': unit.get('Einzelbreiten_mm', ''),
                'Einzelhöhen_mm': unit.get('Einzelhöhen_mm', ''),
                'Einlage_allgemein_mm': safe_number(unit.get('Einlage_allgemein_mm'), 0.0),
                'Bundeinlage_mm': safe_number(unit.get('Bundeinlage_mm'), 0.0),
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

    if center_geometric and not placements_df.empty and not platforms_used_df.empty:
        placements_df = center_placements_geometrically(placements_df, platforms_used_df)
        summary_df = recompute_summary_from_placements(placements_df, platforms_used_df)

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
    warnings_df: Optional[pd.DataFrame] = None,
    bsd_header_df: Optional[pd.DataFrame] = None,
    bsd_matrix_df: Optional[pd.DataFrame] = None,
) -> bytes:
    """Erstellt den Excel-Export.

    Neben den Rohdaten wird pro belegter Pritsche ein optischer Ladeplan-BSD
    als eigenes Excel-Blatt erzeugt. Dieses Blatt ist bewusst an die gelieferte
    PB6-Vorlage angelehnt: Kopfbereich, Kontrolle, Ladeplan-Matrix,
    Ladehöhe, Material/Bemerkungen und Gewichts-Etikette.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Rohdatenblätter bleiben erhalten.
        parts_df.to_excel(writer, sheet_name='Bauteile', index=False)
        units_df.to_excel(writer, sheet_name='Verladeeinheiten', index=False)
        placements_df.to_excel(writer, sheet_name='Platzierung', index=False)
        platforms_df.to_excel(writer, sheet_name='Pritschen_verwendet', index=False)
        summary_df.to_excel(writer, sheet_name='Pritschen_Summary', index=False)
        if options_df is not None and not options_df.empty:
            options_df.to_excel(writer, sheet_name='Fuhrenoptionen', index=False)
        if fuhren_log_df is not None and not fuhren_log_df.empty:
            fuhren_log_df.to_excel(writer, sheet_name='Fuhrenübersicht', index=False)
        if bsd_header_df is not None and not bsd_header_df.empty:
            bsd_header_df.to_excel(writer, sheet_name='Ladeplan_BSD_Kopf', index=False)
        if bsd_matrix_df is not None and not bsd_matrix_df.empty:
            bsd_matrix_df.to_excel(writer, sheet_name='Ladeplan_BSD_Daten', index=False)
        if warnings_df is not None and not warnings_df.empty:
            warnings_df.to_excel(writer, sheet_name='Warnungen', index=False)

        # Optische Ladeplan-BSD-Blätter erzeugen.
        try:
            from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
            from openpyxl.utils import get_column_letter
        except Exception:
            # Falls openpyxl lokal nicht verfügbar ist, bleiben zumindest die Rohdaten erhalten.
            return output.getvalue()

        wb = writer.book

        def sheet_safe_name(value: str) -> str:
            cleaned = re.sub(r'[\\/*?:\[\]]', '_', str(value or 'Pritsche')).strip()
            cleaned = cleaned.replace(' ', '_')
            return cleaned[:31] or 'Pritsche'

        def unique_sheet_name(base: str) -> str:
            base = sheet_safe_name(base)
            if base not in wb.sheetnames:
                return base
            for i in range(2, 100):
                suffix = f'_{i}'
                candidate = f'{base[:31-len(suffix)]}{suffix}'
                if candidate not in wb.sheetnames:
                    return candidate
            return base[:28] + '_x'

        def val(row: pd.Series, key: str, default: Any = '') -> Any:
            try:
                v = row.get(key, default)
                if pd.isna(v):
                    return default
                return v
            except Exception:
                return default

        def fmt_mm(value: Any) -> str:
            try:
                return f'{float(value):.0f}'
            except Exception:
                return '0'

        def fmt_t(value_kg: Any) -> str:
            try:
                return f'{float(value_kg) / 1000:.2f}'
            except Exception:
                return '0.00'

        # Farben ähnlich der Vorlage.
        fill_cyan = PatternFill('solid', fgColor='CCFFFF')
        fill_yellow = PatternFill('solid', fgColor='FFFF99')
        fill_gray = PatternFill('solid', fgColor='C0C0C0')
        fill_lightgray = PatternFill('solid', fgColor='E7E6E6')
        fill_white = PatternFill('solid', fgColor='FFFFFF')
        fill_hatch = PatternFill('darkTrellis', fgColor='999999', bgColor='FFFFFF')
        thin = Side(style='thin', color='000000')
        dotted = Side(style='dotted', color='000000')
        border_thin = Border(left=thin, right=thin, top=thin, bottom=thin)
        border_dotted = Border(left=dotted, right=dotted, top=dotted, bottom=dotted)
        font_title = Font(name='Arial', size=14, bold=True)
        font_head = Font(name='Arial', size=10, bold=True)
        font_body = Font(name='Arial', size=9)
        font_small = Font(name='Arial', size=8)

        def style_range(ws, cell_range: str, fill=None, border=None, font=None, align=None):
            for row_cells in ws[cell_range]:
                for cell in row_cells:
                    if fill is not None:
                        cell.fill = fill
                    if border is not None:
                        cell.border = border
                    if font is not None:
                        cell.font = font
                    if align is not None:
                        cell.alignment = align

        def set_box(ws, cell_range: str, fill=None):
            style_range(
                ws,
                cell_range,
                fill=fill,
                border=border_thin,
                font=font_body,
                align=Alignment(horizontal='left', vertical='center', wrap_text=True),
            )

        def write_label(ws, cell: str, label: str, bold: bool = True):
            ws[cell] = label
            ws[cell].font = font_head if bold else font_body
            ws[cell].alignment = Alignment(horizontal='left', vertical='center')

        def add_styled_bsd_sheet(header: pd.Series, matrix: pd.DataFrame):
            pname = str(val(header, 'Pritsche', 'Pritsche'))
            ws = wb.create_sheet(unique_sheet_name(f'BSD_{pname}'))
            ws.sheet_view.showGridLines = True
            ws.freeze_panes = 'A13'

            # Spaltenbreiten wie breiter Excel-Ladeplan.
            widths = {
                'A': 10, 'B': 10, 'C': 10, 'D': 10,
                'E': 12, 'F': 12, 'G': 12, 'H': 12,
                'I': 11, 'J': 11, 'K': 12,
                'L': 2, 'M': 14, 'N': 14, 'O': 14, 'P': 14,
            }
            for col, width in widths.items():
                ws.column_dimensions[col].width = width
            for r in range(1, 45):
                ws.row_dimensions[r].height = 18

            # Kopf links.
            ws.merge_cells('A2:B2')
            ws.merge_cells('C2:D2')
            ws.merge_cells('C3:D3')
            set_box(ws, 'A2:D8')
            write_label(ws, 'A2', 'Pritsche:')
            ws['C2'] = pname
            ws['C2'].font = font_title
            ws['C2'].fill = fill_cyan
            ws['C3'] = str(val(header, 'Pritschenname', '') or val(header, 'Fuhrenoption', ''))
            ws['C3'].font = font_title
            ws['C3'].fill = fill_yellow
            write_label(ws, 'A6', 'Decke:')
            ws['C6'] = ''
            ws['C6'].fill = fill_cyan
            write_label(ws, 'A7', 'Bauabschnitt:')
            ws['C7'] = ''
            ws['C7'].fill = fill_cyan
            write_label(ws, 'A9', 'Sachbearbeiter:')
            ws['C9'] = ''
            write_label(ws, 'A10', 'Datum:')
            ws['C10'] = datetime.now().strftime('%d.%m.%Y')
            set_box(ws, 'A9:D10')

            # Kopf Mitte.
            set_box(ws, 'F2:K10')
            write_label(ws, 'F2', 'Unternehmer:')
            ws.merge_cells('I2:K2')
            ws['I2'] = ''
            ws['I2'].fill = fill_yellow
            write_label(ws, 'F4', 'Pritschenhöhe:')
            ws['I4'] = fmt_mm(val(header, 'Pritschenhöhe_mm', 0))
            ws['I4'].fill = fill_cyan
            ws['J4'] = 'mm'
            write_label(ws, 'F5', 'Pritschenbreite:')
            ws['I5'] = fmt_mm(val(header, 'Pritschenbreite_mm', 0))
            ws['I5'].fill = fill_cyan
            ws['J5'] = 'mm'
            write_label(ws, 'F7', 'Frachthöhe:')
            ws['I7'] = fmt_mm(val(header, 'Frachthöhe_mm', 0)); ws['J7'] = 'mm'
            write_label(ws, 'F8', 'Höhe (gesamt):')
            ws['I8'] = fmt_mm(val(header, 'Höhe_gesamt_mm', 0)); ws['J8'] = 'mm'
            write_label(ws, 'F9', 'Länge (gesamt):')
            ws['I9'] = fmt_mm(val(header, 'Länge_gesamt_mm', 0)); ws['J9'] = 'mm'
            write_label(ws, 'F10', 'Breite (gesamt):')
            ws['I10'] = fmt_mm(val(header, 'Breite_gesamt_mm', 0)); ws['J10'] = 'mm'
            write_label(ws, 'F11', 'Ladegewicht (gesamt):')
            ws['I11'] = fmt_t(val(header, 'Ladegewicht_kg', 0)); ws['J11'] = 'to'
            set_box(ws, 'F11:K11')

            # Kontrolle rechts.
            set_box(ws, 'M2:P10')
            ws.merge_cells('M2:P2')
            ws['M2'] = 'Kontrolle Root'
            ws['M2'].font = font_title
            write_label(ws, 'M4', 'Datum / Visum:')
            write_label(ws, 'M7', 'Frachthöhe:')
            write_label(ws, 'M8', 'Überhang vorne:')
            write_label(ws, 'M9', 'Länge (gesamt):')
            write_label(ws, 'M10', 'Überhang hinten:')
            write_label(ws, 'M11', 'Überbreite:')
            set_box(ws, 'M11:P11')
            for r in range(7, 12):
                ws[f'P{r}'] = 'mm'

            # Matrix Kopf.
            start_row = 14
            ws.merge_cells(start_row=13, start_column=1, end_row=13, end_column=4)
            ws.cell(13, 1).value = 'Je 2 Elemente nebeneinander angeordnet'
            ws.cell(13, 1).font = font_head
            ws.cell(13, 1).alignment = Alignment(horizontal='center')

            headers = [
                'Vorne links', 'Vorne rechts', 'Hinten links', 'Hinten rechts',
                'Bemerkung\nVorne links', 'Bemerkung\nVorne rechts', 'Bemerkung\nHinten links', 'Bemerkung\nHinten rechts',
                'Höhe (mm)', 'Breite (mm)', 'Gesamtlänge'
            ]
            for idx, h in enumerate(headers, start=1):
                c = ws.cell(start_row, idx)
                c.value = h
                c.font = font_small if idx <= 8 else font_head
                c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
                c.border = border_thin
                c.fill = fill_yellow if idx in [1, 2, 3, 4, 9] else fill_white
            ws.row_dimensions[start_row].height = 28

            # Etwas leere Rasterfläche oberhalb der tatsächlichen Lagen wie in Vorlage.
            data_row = start_row + 1
            max_rows = max(18, len(matrix) + 8)
            for r in range(data_row, data_row + max_rows):
                for c in range(1, 12):
                    ws.cell(r, c).border = border_dotted
                    ws.cell(r, c).font = font_small
                    ws.cell(r, c).alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
                    if c <= 4:
                        ws.cell(r, c).fill = fill_yellow
                    elif c <= 8:
                        ws.cell(r, c).fill = fill_white
                    else:
                        ws.cell(r, c).fill = fill_white

            # Matrixdaten an den unteren Teil setzen, dadurch ähnelt es dem Beispiel optisch.
            write_start = data_row + max(0, max_rows - len(matrix) - 1)
            if matrix is not None and not matrix.empty:
                for i, (_, mrow) in enumerate(matrix.iterrows(), start=write_start):
                    row_values = [
                        mrow.get('Vorne links', ''), mrow.get('Vorne rechts', ''),
                        mrow.get('Hinten links', ''), mrow.get('Hinten rechts', ''),
                        mrow.get('Bemerkung vorne links', ''), mrow.get('Bemerkung vorne rechts', ''),
                        mrow.get('Bemerkung hinten links', ''), mrow.get('Bemerkung hinten rechts', ''),
                        fmt_mm(mrow.get('Höhe_mm', 0)), fmt_mm(mrow.get('Breite_mm', 0)), fmt_mm(mrow.get('Gesamtlänge_mm', 0)),
                    ]
                    for c, value in enumerate(row_values, start=1):
                        cell = ws.cell(i, c)
                        cell.value = value
                        cell.font = Font(name='Arial', size=8, bold=(c <= 4))
                        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
                        cell.border = border_dotted
                    ws.row_dimensions[i].height = 22

            # Ladehöhe/Statuszeile.
            footer_row = data_row + max_rows
            ws.cell(footer_row, 1).value = 'Ladehöhe:'
            ws.cell(footer_row, 1).font = font_head
            for c in range(2, 5):
                ws.cell(footer_row, c).value = fmt_mm(val(header, 'Frachthöhe_mm', 0))
            ws.merge_cells(start_row=footer_row, start_column=5, end_row=footer_row, end_column=8)
            ws.cell(footer_row, 5).value = f"Gesamtgewicht ca.: {fmt_t(val(header, 'Ladegewicht_kg', 0))} Tonnen"
            ws.cell(footer_row, 5).font = font_head
            ws.cell(footer_row, 9).value = fmt_mm(val(header, 'Höhe_gesamt_mm', 0))
            ws.cell(footer_row, 10).value = fmt_mm(val(header, 'Breite_gesamt_mm', 0))
            ws.cell(footer_row, 11).value = fmt_mm(val(header, 'Länge_gesamt_mm', 0))
            style_range(ws, f'A{footer_row}:K{footer_row}', fill=fill_gray, border=border_thin, font=font_small, align=Alignment(horizontal='center'))

            # Graue Ladehöhen-Kästchen.
            box_top = footer_row + 1
            for c1, c2 in [(2, 2), (9, 9)]:
                ws.merge_cells(start_row=box_top, start_column=c1, end_row=box_top + 2, end_column=c2)
                cell = ws.cell(box_top, c1)
                cell.value = fmt_mm(val(header, 'Frachthöhe_mm', 0))
                cell.fill = fill_gray
                cell.border = border_thin
                cell.alignment = Alignment(horizontal='center', vertical='top')

            # Untere Bereiche.
            lower_top = footer_row + 4
            ws.merge_cells(start_row=lower_top, start_column=1, end_row=lower_top, end_column=4)
            ws.cell(lower_top, 1).value = 'Zusätzliches Verlade-Material:'
            ws.cell(lower_top, 1).font = font_head
            ws.merge_cells(start_row=lower_top, start_column=6, end_row=lower_top, end_column=11)
            ws.cell(lower_top, 6).value = 'Bemerkungen:'
            ws.cell(lower_top, 6).font = font_head
            for r in range(lower_top, lower_top + 7):
                for c in range(1, 12):
                    ws.cell(r, c).border = border_thin if r == lower_top else border_dotted

            # Gewichtsetikette rechts unten.
            ws.merge_cells(start_row=15, start_column=13, end_row=footer_row + 3, end_column=16)
            ws.cell(15, 13).fill = fill_hatch
            ws.cell(15, 13).border = border_thin
            ws.merge_cells(start_row=footer_row + 4, start_column=13, end_row=footer_row + 4, end_column=16)
            ws.cell(footer_row + 4, 13).value = 'Gewichts-Etikette:'
            ws.cell(footer_row + 4, 13).font = font_head
            ws.cell(footer_row + 4, 13).alignment = Alignment(horizontal='center')
            ws.merge_cells(start_row=footer_row + 5, start_column=13, end_row=lower_top + 6, end_column=16)
            ws.cell(footer_row + 5, 13).fill = fill_hatch
            ws.cell(footer_row + 5, 13).border = border_thin

            # Rahmen / allgemeine Formatierung.
            for row in ws.iter_rows(min_row=1, max_row=lower_top + 6, min_col=1, max_col=16):
                for cell in row:
                    if cell.font == Font():
                        cell.font = font_body
            ws.page_setup.orientation = 'landscape'
            ws.page_setup.paperSize = ws.PAPERSIZE_A3
            ws.page_margins.left = 0.25
            ws.page_margins.right = 0.25
            ws.page_margins.top = 0.25
            ws.page_margins.bottom = 0.25
            ws.print_area = f'A1:P{lower_top + 6}'
            ws.sheet_properties.pageSetUpPr.fitToPage = True
            ws.page_setup.fitToWidth = 1
            ws.page_setup.fitToHeight = 1

        if bsd_header_df is not None and not bsd_header_df.empty and bsd_matrix_df is not None and not bsd_matrix_df.empty:
            for _, header in bsd_header_df.iterrows():
                pname = str(val(header, 'Pritsche', ''))
                matrix = bsd_matrix_df[bsd_matrix_df['Pritsche'].astype(str) == pname].copy()
                add_styled_bsd_sheet(header, matrix)

        # Rohdatenblätter etwas lesbarer machen.
        for ws in wb.worksheets:
            if ws.title.startswith('BSD_'):
                continue
            for col in ws.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col[:50]:
                    try:
                        max_len = max(max_len, len(str(cell.value)) if cell.value is not None else 0)
                    except Exception:
                        pass
                ws.column_dimensions[col_letter].width = min(max(max_len + 2, 10), 40)
            if ws.max_row >= 1:
                for cell in ws[1]:
                    cell.font = font_head
                    cell.fill = fill_lightgray
                    cell.border = border_thin

    return output.getvalue()


def _view_label(row: pd.Series) -> str:
    label = _format_label_value(row.get('Ansicht_Label'))
    if not label:
        label = _format_label_value(row.get('Bauteile'))
    if not label:
        label = _format_label_value(row.get('Einheit_ID'))
    if str(row.get('Typ', '')).strip() == 'Bund':
        liste = _split_bsd_text_list(row.get('Ansicht_Liste', ''), label)
        if len(liste) > 3:
            label = ', '.join(liste[:3]) + ' ...'
        elif liste:
            label = ', '.join(liste)
        # Plotly-Zeilenumbruch
        return str(label).replace(', ', '<br>')
    return str(label)


def draw_loading_view(placements_df: pd.DataFrame, platforms_df: pd.DataFrame, platform_name: str, view: str) -> go.Figure:
    """Zeichnet Draufsicht, Seitenansicht oder Rückansicht der ausgewählten Pritsche.

    Wichtig: Plotly skaliert Achsen nicht zuverlässig nur anhand von Shapes.
    Deshalb werden die Achsbereiche hier fest gesetzt, damit die Rechtecke sichtbar sind.
    """
    platform_match = platforms_df[platforms_df['Pritsche'].astype(str) == str(platform_name)]
    fig = go.Figure()

    title_prefix = {
        'top': 'Draufsicht',
        'side': 'Seitenansicht',
        'back': 'Rückansicht',
    }.get(view, 'Ansicht')

    if platform_match.empty:
        fig.update_layout(
            title=f'{title_prefix} - keine Pritsche gefunden',
            height=450,
            margin=dict(l=20, r=20, t=50, b=20),
        )
        fig.add_annotation(text='Keine Pritschendaten vorhanden', x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False)
        return fig

    platform_row = platform_match.iloc[0]
    eff_length = float(platform_row['Länge_mm']) + float(platform_row['Überhang_vorne_mm']) + float(platform_row['Überhang_hinten_mm'])
    width = float(platform_row['Breite_mm'])
    max_height = float(platform_row['Max_Höhe_mm'])
    base_wood = float(platform_row.get('Kantholz_erste_Lage_mm', 0) or 0)

    loaded = placements_df[placements_df['Pritsche'].astype(str) == str(platform_name)].copy()
    loaded = loaded[loaded['X_mm'].notna() & loaded['Y_mm'].notna() & loaded['Z_mm'].notna()].copy()

    # Unsichtbarer Punkt erzwingt, dass Plotly die Grafikfläche überhaupt aufspannt.
    fig.add_trace(go.Scatter(x=[0], y=[0], mode='markers', marker=dict(size=1, opacity=0), hoverinfo='skip', showlegend=False))

    if view == 'top':
        fig.update_layout(
            title=f'{title_prefix} - {platform_name}',
            xaxis_title='Länge X (mm)',
            yaxis_title='Breite Y (mm)',
        )
        fig.add_shape(type='rect', x0=0, y0=0, x1=eff_length, y1=width, line=dict(width=2, dash='dash'))
        for _, row in loaded.iterrows():
            x0, y0 = float(row['X_mm']), float(row['Y_mm'])
            x1, y1 = x0 + float(row['Länge_mm']), y0 + float(row['Breite_mm'])
            fig.add_shape(type='rect', x0=x0, y0=y0, x1=x1, y1=y1, line=dict(width=1), fillcolor='rgba(100,100,100,0.28)')
            fig.add_annotation(x=(x0 + x1) / 2, y=(y0 + y1) / 2, text=_view_label(row), showarrow=False, font=dict(size=10))
        fig.update_xaxes(range=[0, max(eff_length, 1)], constrain='domain')
        fig.update_yaxes(range=[0, max(width, 1)], scaleanchor='x', scaleratio=1)

    elif view == 'side':
        fig.update_layout(
            title=f'{title_prefix} - {platform_name}',
            xaxis_title='Länge X (mm)',
            yaxis_title='Höhe Z (mm)',
        )
        fig.add_shape(type='rect', x0=0, y0=0, x1=eff_length, y1=max_height, line=dict(width=2, dash='dash'))
        if base_wood > 0:
            fig.add_shape(type='line', x0=0, y0=base_wood, x1=eff_length, y1=base_wood, line=dict(width=1, dash='dot'))
        for _, row in loaded.iterrows():
            x0, z0 = float(row['X_mm']), float(row['Z_mm'])
            x1, z1 = x0 + float(row['Länge_mm']), z0 + float(row['Höhe_mm'])
            fig.add_shape(type='rect', x0=x0, y0=z0, x1=x1, y1=z1, line=dict(width=1), fillcolor='rgba(100,100,100,0.28)')
            fig.add_annotation(x=(x0 + x1) / 2, y=(z0 + z1) / 2, text=_view_label(row), showarrow=False, font=dict(size=10))
        fig.update_xaxes(range=[0, max(eff_length, 1)], constrain='domain')
        fig.update_yaxes(range=[0, max(max_height, 1)])

    else:
        fig.update_layout(
            title=f'{title_prefix} - {platform_name}',
            xaxis_title='Breite Y (mm)',
            yaxis_title='Höhe Z (mm)',
        )
        fig.add_shape(type='rect', x0=0, y0=0, x1=width, y1=max_height, line=dict(width=2, dash='dash'))
        if base_wood > 0:
            fig.add_shape(type='line', x0=0, y0=base_wood, x1=width, y1=base_wood, line=dict(width=1, dash='dot'))
        for _, row in loaded.iterrows():
            y0, z0 = float(row['Y_mm']), float(row['Z_mm'])
            y1, z1 = y0 + float(row['Breite_mm']), z0 + float(row['Höhe_mm'])
            fig.add_shape(type='rect', x0=y0, y0=z0, x1=y1, y1=z1, line=dict(width=1), fillcolor='rgba(100,100,100,0.28)')
            fig.add_annotation(x=(y0 + y1) / 2, y=(z0 + z1) / 2, text=_view_label(row), showarrow=False, font=dict(size=10))
        fig.update_xaxes(range=[0, max(width, 1)], constrain='domain')
        fig.update_yaxes(range=[0, max(max_height, 1)])

    if loaded.empty:
        fig.add_annotation(
            text='Auf dieser Pritsche sind keine Einheiten platziert',
            x=0.5,
            y=0.5,
            xref='paper',
            yref='paper',
            showarrow=False,
            font=dict(size=14),
        )

    fig.update_layout(height=450, showlegend=False, margin=dict(l=20, r=20, t=50, b=20))
    return fig



def clean_placements_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Konvertiert manuell bearbeitete Platzierungswerte wieder in saubere Zahlen."""
    result = df.copy()
    numeric_cols = ['Fuhre_Nr', 'Anzahl_Bauteile', 'X_mm', 'Y_mm', 'Z_mm', 'Länge_mm', 'Breite_mm', 'Höhe_mm', 'Drehung', 'Gewicht_kg']
    for col in numeric_cols:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors='coerce')
    if 'Pritsche' in result.columns:
        result['Pritsche'] = result['Pritsche'].fillna('').astype(str)
    if 'Einheit_ID' in result.columns:
        result['Einheit_ID'] = result['Einheit_ID'].fillna('').astype(str)
    return result


def compute_loading_warnings(placements_df: pd.DataFrame, platforms_df: pd.DataFrame) -> pd.DataFrame:
    """Prüft Länge, Breite, Höhe, Gewicht, negative Positionen und nicht verladen."""
    warnings: List[Dict[str, Any]] = []
    if placements_df is None or placements_df.empty:
        return pd.DataFrame([{'Typ': 'Info', 'Pritsche': '', 'Einheit_ID': '', 'Warnung': 'Keine Platzierung vorhanden', 'Details': ''}])

    platform_lookup: Dict[str, Dict[str, float]] = {}
    if platforms_df is not None and not platforms_df.empty:
        for _, row in platforms_df.iterrows():
            name = str(row.get('Pritsche', ''))
            platform_lookup[name] = {
                'eff_length': safe_number(row.get('Länge_mm')) + safe_number(row.get('Überhang_vorne_mm')) + safe_number(row.get('Überhang_hinten_mm')),
                'width': safe_number(row.get('Breite_mm')),
                'max_height': safe_number(row.get('Max_Höhe_mm')),
                'max_weight': safe_number(row.get('Max_Gewicht_kg')),
                'base_height': safe_number(row.get('Kantholz_erste_Lage_mm')),
            }

    for _, row in placements_df.iterrows():
        pritsche = str(row.get('Pritsche', ''))
        einheit = str(row.get('Einheit_ID', ''))

        if pritsche == 'NICHT VERLADEN':
            warnings.append({'Typ': 'Nicht verladen', 'Pritsche': pritsche, 'Einheit_ID': einheit, 'Warnung': 'Einheit wurde nicht platziert', 'Details': str(row.get('Ebene', ''))})
            continue

        if pritsche not in platform_lookup:
            warnings.append({'Typ': 'Pritsche', 'Pritsche': pritsche, 'Einheit_ID': einheit, 'Warnung': 'Pritsche nicht in Stammdaten gefunden', 'Details': 'Name der Pritsche prüfen'})
            continue

        limits = platform_lookup[pritsche]
        x = safe_number(row.get('X_mm'), 0.0)
        y = safe_number(row.get('Y_mm'), 0.0)
        z = safe_number(row.get('Z_mm'), 0.0)
        length = safe_number(row.get('Länge_mm'), 0.0)
        width = safe_number(row.get('Breite_mm'), 0.0)
        height = safe_number(row.get('Höhe_mm'), 0.0)

        if x < 0 or y < 0 or z < 0:
            warnings.append({'Typ': 'Position', 'Pritsche': pritsche, 'Einheit_ID': einheit, 'Warnung': 'Negative Position', 'Details': f'X={x:.0f}, Y={y:.0f}, Z={z:.0f}'})
        if x + length > limits['eff_length']:
            warnings.append({'Typ': 'Länge', 'Pritsche': pritsche, 'Einheit_ID': einheit, 'Warnung': 'Länge / Überhang überschritten', 'Details': f'{x + length:.0f} mm > {limits["eff_length"]:.0f} mm'})
        if y + width > limits['width']:
            warnings.append({'Typ': 'Breite', 'Pritsche': pritsche, 'Einheit_ID': einheit, 'Warnung': 'Breite überschritten', 'Details': f'{y + width:.0f} mm > {limits["width"]:.0f} mm'})
        check_height = z + height if z >= limits.get('base_height', 0.0) - 0.1 else z + height + limits.get('base_height', 0.0)
        if check_height > limits['max_height']:
            warnings.append({'Typ': 'Höhe', 'Pritsche': pritsche, 'Einheit_ID': einheit, 'Warnung': 'Höhe überschritten', 'Details': f'{check_height:.0f} mm > {limits["max_height"]:.0f} mm'})

    if platforms_df is not None and not platforms_df.empty:
        for platform_name, group in placements_df[placements_df['Pritsche'] != 'NICHT VERLADEN'].groupby('Pritsche'):
            name = str(platform_name)
            if name not in platform_lookup:
                continue
            total_weight = pd.to_numeric(group.get('Gewicht_kg'), errors='coerce').fillna(0).sum()
            max_weight = platform_lookup[name]['max_weight']
            if total_weight > max_weight:
                warnings.append({'Typ': 'Gewicht', 'Pritsche': name, 'Einheit_ID': '', 'Warnung': 'Max. Gewicht überschritten', 'Details': f'{total_weight:.0f} kg > {max_weight:.0f} kg'})

    return pd.DataFrame(warnings)


def recompute_summary_from_placements(placements_df: pd.DataFrame, platforms_df: pd.DataFrame) -> pd.DataFrame:
    """Erstellt die Pritschen-Zusammenfassung neu, damit manuelle Änderungen berücksichtigt werden."""
    rows: List[Dict[str, Any]] = []
    if platforms_df is None or platforms_df.empty:
        return pd.DataFrame()

    for _, prow in platforms_df.iterrows():
        pname = str(prow.get('Pritsche', ''))
        group = placements_df[placements_df.get('Pritsche', pd.Series(dtype=str)).astype(str) == pname] if not placements_df.empty else pd.DataFrame()
        group = group[group.get('X_mm', pd.Series(dtype=float)).notna()] if not group.empty else group
        used_length = float((group['X_mm'] + group['Länge_mm']).max()) if not group.empty else 0.0
        used_width = float((group['Y_mm'] + group['Breite_mm']).max()) if not group.empty else 0.0
        base_height = safe_number(prow.get('Kantholz_erste_Lage_mm'), 0.0)
        if not group.empty:
            raw_height = float((group['Z_mm'] + group['Höhe_mm']).max())
            min_z = float(group['Z_mm'].min())
            # Normal startet die Platzierung bereits auf dem Kantholz. Falls manuell ab Z=0 gesetzt wird,
            # wird das Kantholz trotzdem zur Frachthöhe addiert.
            used_height = raw_height if min_z >= base_height - 0.1 else raw_height + base_height
        else:
            used_height = base_height
        used_weight = float(pd.to_numeric(group.get('Gewicht_kg'), errors='coerce').fillna(0).sum()) if not group.empty else 0.0
        rows.append({
            'Fuhre_Nr': prow.get('Fuhre_Nr'),
            'Fuhrenoption': prow.get('Fuhrenoption'),
            'Pritschenname': prow.get('Pritschenname'),
            'Pritsche': pname,
            'Länge genutzt_mm': round(used_length, 1),
            'Breite genutzt_mm': round(used_width, 1),
            'Höhe genutzt_mm': round(used_height, 1),
            'Gewicht genutzt_kg': round(used_weight, 2),
            'Max Länge effektiv_mm': round(safe_number(prow.get('Länge_mm')) + safe_number(prow.get('Überhang_vorne_mm')) + safe_number(prow.get('Überhang_hinten_mm')), 1),
            'Max Breite_mm': round(safe_number(prow.get('Breite_mm')), 1),
            'Max Höhe_mm': round(safe_number(prow.get('Max_Höhe_mm')), 1),
            'Max Gewicht_kg': round(safe_number(prow.get('Max_Gewicht_kg')), 1),
        })
    return pd.DataFrame(rows)



def _format_bsd_cell(row: pd.Series) -> str:
    """Beschriftung für die Ladeplan-BSD-Matrix."""
    bauteile = str(row.get('Bauteile', '') or '').strip()
    einheit = str(row.get('Einheit_ID', '') or '').strip()
    typ = str(row.get('Typ', '') or '').strip()
    anzahl = int(safe_number(row.get('Anzahl_Bauteile'), 1))

    if bauteile and bauteile.lower() != 'nan':
        label = bauteile
    else:
        label = einheit

    if typ == 'Bund' and einheit:
        return f'{einheit} ({anzahl} Stk.)\n{label}'
    return label or einheit


def _position_slot_for_bsd(row: pd.Series, eff_length: float, platform_width: float) -> str:
    """Ordnet eine Einheit anhand ihres geometrischen Mittelpunktes einer BSD-Position zu."""
    x_mid = safe_number(row.get('X_mm')) + safe_number(row.get('Länge_mm')) / 2
    y_mid = safe_number(row.get('Y_mm')) + safe_number(row.get('Breite_mm')) / 2

    # X: vorderer / hinterer Bereich der Pritsche. Y: links / rechts.
    front_back = 'Vorne' if x_mid <= eff_length / 2 else 'Hinten'
    left_right = 'links' if y_mid <= platform_width / 2 else 'rechts'
    return f'{front_back} {left_right}'


def create_bsd_header_for_platform(
    platform: pd.Series,
    summary_df: pd.DataFrame,
    warnings_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Kopfdaten je Pritsche ähnlich Ladeplan BSD."""
    pname = str(platform.get('Pritsche', ''))
    srow = summary_df[summary_df['Pritsche'].astype(str) == pname] if summary_df is not None and not summary_df.empty else pd.DataFrame()
    srow = srow.iloc[0] if not srow.empty else pd.Series(dtype=object)
    warn_count = 0
    if warnings_df is not None and not warnings_df.empty and 'Pritsche' in warnings_df.columns:
        warn_count = int((warnings_df['Pritsche'].astype(str) == pname).sum())

    return {
        'Pritsche': pname,
        'Fuhre_Nr': platform.get('Fuhre_Nr', ''),
        'Fuhrenoption': platform.get('Fuhrenoption', ''),
        'Pritschenname': platform.get('Pritschenname', ''),
        'Pritschenhöhe_mm': safe_number(platform.get('Max_Höhe_mm')),
        'Pritschenbreite_mm': safe_number(platform.get('Breite_mm')),
        'Pritschenlänge_effektiv_mm': safe_number(platform.get('Länge_mm')) + safe_number(platform.get('Überhang_vorne_mm')) + safe_number(platform.get('Überhang_hinten_mm')),
        'Frachthöhe_mm': safe_number(srow.get('Höhe genutzt_mm')),
        'Höhe_gesamt_mm': safe_number(srow.get('Höhe genutzt_mm')),
        'Länge_gesamt_mm': safe_number(srow.get('Länge genutzt_mm')),
        'Breite_gesamt_mm': safe_number(srow.get('Breite genutzt_mm')),
        'Ladegewicht_kg': safe_number(srow.get('Gewicht genutzt_kg')),
        'Warnungen': warn_count,
    }



def _split_bsd_text_list(value: Any, fallback: str = '') -> List[str]:
    """Zerlegt Bauteillisten aus Verladeeinheiten robust."""
    text = str(value or '').strip()
    if not text or text.lower() == 'nan':
        text = str(fallback or '').strip()
    if not text:
        return []
    if '|' in text:
        items = [item.strip() for item in text.split('|')]
    else:
        items = [item.strip() for item in re.split(r'\s*,\s*', text)]
    return [item for item in items if item and item.lower() != 'nan']


def _split_bsd_number_list(value: Any, count: int, fallback_total: float, spacer_height: float) -> List[float]:
    """Zerlegt Einzelhöhen/Längen/Breiten. Fehlen Werte, wird sinnvoll aufgefüllt."""
    text = str(value or '').strip()
    values: List[float] = []
    if text and text.lower() != 'nan':
        raw_items = text.split('|') if '|' in text else re.split(r'[;,]', text)
        for item in raw_items:
            if str(item).strip():
                values.append(safe_number(item, 0.0))
    if count <= 0:
        return values
    if len(values) < count:
        # Wenn keine Einzelhöhen bekannt sind, wird aus der Gesamthöhe abzüglich Einlagen verteilt.
        if not values:
            remaining = max(0.0, fallback_total - max(0, count - 1) * spacer_height)
            default_each = remaining / count if count else fallback_total
        else:
            default_each = values[-1]
        values.extend([default_each] * (count - len(values)))
    return values[:count]


def _fmt_bsd_mm_label(prefix: str, value: float) -> str:
    v = safe_number(value)
    if abs(v - round(v)) < 0.001:
        text = f'{v:.0f}'
    else:
        text = f'{v:.2f}'.rstrip('0').rstrip('.')
    return f'{prefix} {text}'.strip()


def create_bsd_matrix_for_platform(
    placements_df: pd.DataFrame,
    platform: pd.Series,
    top_first: bool = True,
) -> pd.DataFrame:
    """Erstellt eine Ladeplan-BSD-Matrix je Pritsche.

    Neu:
    - Kantholz erste Lage wird als eigene unterste Zeile angezeigt.
    - Bundeinlagen/Lagenholz werden als eigene Einlage-Zeilen angezeigt.
    - Einlage allgemein wird zwischen einzelnen gestapelten Bauteilen und innerhalb eines Bundes angezeigt, falls > 0.
    - Bei Bund-Verladung werden die einzelnen Bauteile des Bundes separat angezeigt.

    Die Matrix teilt die Pritsche in vier Bereiche auf:
    Vorne links, Vorne rechts, Hinten links, Hinten rechts.
    Grundlage ist die vorhandene X/Y/Z-Platzierung. Es wird keine neue
    Verladeoptimierung gerechnet.
    """
    columns = [
        'Pritsche', 'Fuhre_Nr', 'Lage', 'Z_mm',
        'Vorne links', 'Vorne rechts', 'Hinten links', 'Hinten rechts',
        'Bemerkung vorne links', 'Bemerkung vorne rechts', 'Bemerkung hinten links', 'Bemerkung hinten rechts',
        'Höhe_mm', 'Breite_mm', 'Gesamtlänge_mm', 'Gewicht_kg', 'Anzahl_Einheiten', 'Zeilentyp'
    ]
    if placements_df is None or placements_df.empty:
        return pd.DataFrame(columns=columns)

    pname = str(platform.get('Pritsche', ''))
    eff_length = safe_number(platform.get('Länge_mm')) + safe_number(platform.get('Überhang_vorne_mm')) + safe_number(platform.get('Überhang_hinten_mm'))
    platform_width = safe_number(platform.get('Breite_mm'))
    base_height = safe_number(platform.get('Kantholz_erste_Lage_mm'), 0.0)
    spacer_height = safe_number(platform.get('Einlage_zwischen_Lagen_mm'), 0.0)
    platform_general_spacer = safe_number(platform.get('Einlage_allgemein_mm'), 0.0)

    rows = placements_df[placements_df['Pritsche'].astype(str) == pname].copy()
    rows = rows[rows['X_mm'].notna() & rows['Y_mm'].notna() & rows['Z_mm'].notna()].copy()
    if rows.empty:
        return pd.DataFrame(columns=columns)

    for col in ['X_mm', 'Y_mm', 'Z_mm', 'Länge_mm', 'Breite_mm', 'Höhe_mm', 'Gewicht_kg']:
        rows[col] = pd.to_numeric(rows[col], errors='coerce').fillna(0.0)

    slots = ['Vorne links', 'Vorne rechts', 'Hinten links', 'Hinten rechts']
    slot_has_load = {slot: False for slot in slots}
    entries: List[Dict[str, Any]] = []

    def add_entry(z: float, slot: str, label: str, kind: str, height: float = 0.0, length: float = 0.0, width: float = 0.0, weight: float = 0.0, remark: str = '') -> None:
        if not slot or slot not in slots:
            return
        entries.append({
            'z': round(float(z), 1),
            'slot': slot,
            'label': str(label or '').strip(),
            'kind': kind,
            'height': safe_number(height, 0.0),
            'length': safe_number(length, 0.0),
            'width': safe_number(width, 0.0),
            'weight': safe_number(weight, 0.0),
            'remark': str(remark or '').strip(),
        })

    # Bauteile/Bunde in einzelne sichtbare Zeilen zerlegen.
    for _, row in rows.sort_values(['Z_mm', 'X_mm', 'Y_mm'], kind='stable').iterrows():
        slot = _position_slot_for_bsd(row, eff_length, platform_width)
        slot_has_load[slot] = True
        typ = str(row.get('Typ', '') or '').strip()
        count = max(1, int(safe_number(row.get('Anzahl_Bauteile'), 1)))
        labels = _split_bsd_text_list(row.get('Bauteile_Liste', ''), row.get('Bauteile', row.get('Einheit_ID', '')))
        if not labels:
            labels = [_format_bsd_cell(row)]
        if typ != 'Bund' or count <= 1:
            label = labels[0] if labels else _format_bsd_cell(row)
            remark = ''
            add_entry(row['Z_mm'], slot, label, 'Bauteil', row['Höhe_mm'], row['Länge_mm'], row['Breite_mm'], row['Gewicht_kg'], remark)
            continue

        # Bund: jedes enthaltene Bauteil als eigene BSD-Zeile, Einlagen dazwischen.
        labels = (labels + [labels[-1]] * count)[:count]
        internal_spacer = safe_number(row.get('Einlage_allgemein_mm'), platform_general_spacer)
        if internal_spacer <= 0:
            internal_spacer = safe_number(row.get('Bundeinlage_mm'), spacer_height)
        part_heights = _split_bsd_number_list(row.get('Einzelhöhen_mm', ''), count, row['Höhe_mm'], internal_spacer)
        part_lengths = _split_bsd_number_list(row.get('Einzellängen_mm', ''), count, row['Länge_mm'], 0.0)
        part_widths = _split_bsd_number_list(row.get('Einzelbreiten_mm', ''), count, row['Breite_mm'], 0.0)
        part_weight = safe_number(row.get('Gewicht_kg')) / count if count else safe_number(row.get('Gewicht_kg'))
        z_cursor = safe_number(row.get('Z_mm'))
        for i, label in enumerate(labels):
            ph = safe_number(part_heights[i] if i < len(part_heights) else row['Höhe_mm'])
            pl = safe_number(part_lengths[i] if i < len(part_lengths) else row['Länge_mm'])
            pw = safe_number(part_widths[i] if i < len(part_widths) else row['Breite_mm'])
            remark = ''
            add_entry(z_cursor, slot, label, 'Bund-Bauteil', ph, pl, pw, part_weight, remark)
            z_cursor += ph
            if i < count - 1 and internal_spacer > 0:
                spacer_label = 'Einlage allgemein' if safe_number(row.get('Einlage_allgemein_mm'), platform_general_spacer) > 0 else 'Einlage'
                spacer_kind = 'Einlage allgemein' if spacer_label == 'Einlage allgemein' else 'Bund-Einlage'
                spacer_remark = ''
                add_entry(z_cursor, slot, _fmt_bsd_mm_label(spacer_label, internal_spacer), spacer_kind, internal_spacer, row['Länge_mm'], row['Breite_mm'], 0.0, spacer_remark)
                z_cursor += internal_spacer

    # Kantholz erste Lage als eigene unterste Zeile anzeigen.
    if base_height > 0:
        for slot, has_load in slot_has_load.items():
            if has_load:
                add_entry(0.0, slot, _fmt_bsd_mm_label('Kantholz', base_height), 'Kantholz erste Lage', base_height, eff_length, platform_width, 0.0, '')

    # Zusätzliche Einlage-Zeilen zwischen separaten Lagen anzeigen.
    effective_layer_spacer = spacer_height if spacer_height > 0 else platform_general_spacer
    if effective_layer_spacer > 0:
        layer_z_values = sorted({round(float(v), 1) for v in rows['Z_mm'].tolist() if float(v) > base_height + 0.1})
        existing_spacer_keys = {(round(e['z'], 1), e['slot']) for e in entries if 'Einlage' in e['kind']}
        spacer_label = 'Einlage' if spacer_height > 0 else 'Einlage allgemein'
        spacer_kind = 'Lagenholz' if spacer_height > 0 else 'Einlage allgemein'
        for z_val in layer_z_values:
            layer_rows = rows[rows['Z_mm'].round(1) == z_val].copy()
            for _, lrow in layer_rows.iterrows():
                slot = _position_slot_for_bsd(lrow, eff_length, platform_width)
                z_spacer = round(max(0.0, z_val - effective_layer_spacer), 1)
                if (z_spacer, slot) not in existing_spacer_keys:
                    add_entry(z_spacer, slot, _fmt_bsd_mm_label(spacer_label, effective_layer_spacer), spacer_kind, effective_layer_spacer, lrow['Länge_mm'], lrow['Breite_mm'], 0.0, '')

    if not entries:
        return pd.DataFrame(columns=columns)

    # Gesamt belegte Grundfläche für Unterlagen/Einlagen.
    used_width_all = round(float((rows['Y_mm'] + rows['Breite_mm']).max() - rows['Y_mm'].min()), 1)
    used_length_all = round(float((rows['X_mm'] + rows['Länge_mm']).max() - rows['X_mm'].min()), 1)

    z_levels = sorted({round(e['z'], 1) for e in entries})
    display_levels = list(reversed(z_levels)) if top_first else z_levels
    # Lage 1 = unten, nur für Orientierung. Auch Einlage/Kantholz bekommen eine Lage nach Höhe.
    layer_no_lookup = {z: i + 1 for i, z in enumerate(z_levels)}

    matrix_rows: List[Dict[str, Any]] = []
    for z_key in display_levels:
        level_entries = [e for e in entries if round(e['z'], 1) == z_key]
        if not level_entries:
            continue

        out: Dict[str, Any] = {
            'Pritsche': pname,
            'Fuhre_Nr': platform.get('Fuhre_Nr', ''),
            'Lage': layer_no_lookup[z_key],
            'Z_mm': round(float(z_key), 1),
            'Vorne links': '',
            'Vorne rechts': '',
            'Hinten links': '',
            'Hinten rechts': '',
            'Bemerkung vorne links': '',
            'Bemerkung vorne rechts': '',
            'Bemerkung hinten links': '',
            'Bemerkung hinten rechts': '',
            'Höhe_mm': round(max((e['height'] for e in level_entries), default=0.0), 1),
            'Breite_mm': 0.0,
            'Gesamtlänge_mm': 0.0,
            'Gewicht_kg': round(sum(e['weight'] for e in level_entries), 2),
            'Anzahl_Einheiten': int(sum(1 for e in level_entries if 'Bauteil' in e['kind'])),
            'Zeilentyp': ', '.join(sorted({e['kind'] for e in level_entries})),
        }

        part_like = [e for e in level_entries if 'Bauteil' in e['kind']]
        if part_like:
            out['Breite_mm'] = round(max((e['width'] for e in part_like), default=0.0), 1)
            out['Gesamtlänge_mm'] = round(max((e['length'] for e in part_like), default=0.0), 1)
        else:
            out['Breite_mm'] = used_width_all
            out['Gesamtlänge_mm'] = used_length_all

        for slot in slots:
            slot_entries = [e for e in level_entries if e['slot'] == slot]
            out[slot] = '\n'.join([e['label'] for e in slot_entries if e['label']])
            remarks = [e['remark'] for e in slot_entries if e['remark']]
            out[f'Bemerkung {slot.lower()}'] = '\n'.join(remarks)

        matrix_rows.append(out)

    return pd.DataFrame(matrix_rows, columns=columns)

def create_all_bsd_matrices(
    placements_df: pd.DataFrame,
    platforms_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    warnings_df: Optional[pd.DataFrame] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Erstellt Kopfdaten und Ladeplan-BSD-Matrix für jede verwendete Pritsche."""
    if platforms_df is None or platforms_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    header_rows: List[Dict[str, Any]] = []
    matrix_frames: List[pd.DataFrame] = []
    for _, platform in platforms_df.iterrows():
        pname = str(platform.get('Pritsche', ''))
        has_load = placements_df is not None and not placements_df.empty and (placements_df['Pritsche'].astype(str) == pname).any()
        if not has_load:
            # Leere Pritschen nicht als Ladeplan ausgeben.
            continue
        header_rows.append(create_bsd_header_for_platform(platform, summary_df, warnings_df))
        matrix = create_bsd_matrix_for_platform(placements_df, platform)
        if not matrix.empty:
            matrix_frames.append(matrix)

    header_df = pd.DataFrame(header_rows)
    matrix_df = pd.concat(matrix_frames, ignore_index=True) if matrix_frames else pd.DataFrame()
    return header_df, matrix_df


def _pdf_draw_view(c, placements: pd.DataFrame, platform: pd.Series, x: float, y: float, w: float, h: float, view: str, title: str) -> None:
    """Einfache PDF-Zeichnung ohne zusätzliche Plotly/Kaleido-Abhängigkeit."""
    from reportlab.lib import colors

    eff_length = safe_number(platform.get('Länge_mm')) + safe_number(platform.get('Überhang_vorne_mm')) + safe_number(platform.get('Überhang_hinten_mm'))
    width = safe_number(platform.get('Breite_mm'))
    max_height = safe_number(platform.get('Max_Höhe_mm'))

    c.setStrokeColor(colors.black)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(x, y + h + 10, title)

    if view == 'top':
        data_w, data_h = max(eff_length, 1), max(width, 1)
        x_label, y_label = 'X Länge', 'Y Breite'
    elif view == 'side':
        data_w, data_h = max(eff_length, 1), max(max_height, 1)
        x_label, y_label = 'X Länge', 'Z Höhe'
    else:
        data_w, data_h = max(width, 1), max(max_height, 1)
        x_label, y_label = 'Y Breite', 'Z Höhe'

    scale = min(w / data_w, h / data_h)
    draw_w = data_w * scale
    draw_h = data_h * scale
    ox = x
    oy = y

    c.setStrokeColor(colors.black)
    c.rect(ox, oy, draw_w, draw_h, stroke=1, fill=0)
    c.setFont('Helvetica', 6)
    c.drawString(ox, oy - 10, x_label)
    c.saveState()
    c.translate(ox - 12, oy)
    c.rotate(90)
    c.drawString(0, 0, y_label)
    c.restoreState()

    rows = placements[placements['Pritsche'].astype(str) == str(platform.get('Pritsche', ''))].copy()
    rows = rows[rows['X_mm'].notna() & rows['Y_mm'].notna() & rows['Z_mm'].notna()].copy()
    c.setFillColor(colors.lightgrey)
    c.setStrokeColor(colors.darkgrey)
    for _, row in rows.iterrows():
        if view == 'top':
            rx = ox + safe_number(row.get('X_mm')) * scale
            ry = oy + safe_number(row.get('Y_mm')) * scale
            rw = safe_number(row.get('Länge_mm')) * scale
            rh = safe_number(row.get('Breite_mm')) * scale
        elif view == 'side':
            rx = ox + safe_number(row.get('X_mm')) * scale
            ry = oy + safe_number(row.get('Z_mm')) * scale
            rw = safe_number(row.get('Länge_mm')) * scale
            rh = safe_number(row.get('Höhe_mm')) * scale
        else:
            rx = ox + safe_number(row.get('Y_mm')) * scale
            ry = oy + safe_number(row.get('Z_mm')) * scale
            rw = safe_number(row.get('Breite_mm')) * scale
            rh = safe_number(row.get('Höhe_mm')) * scale
        if rw <= 0 or rh <= 0:
            continue
        c.setFillColor(colors.lightgrey)
        c.rect(rx, ry, rw, rh, stroke=1, fill=1)
        c.setFillColor(colors.black)
        c.setFont('Helvetica', 5)
        label = str(_view_label(row)).replace('<br>', ' ')[:24]
        c.drawCentredString(rx + rw / 2, ry + rh / 2, label)


def _pdf_draw_bsd_matrix_page(c, page_w: float, page_h: float, margin: float, platform: pd.Series, matrix_df: pd.DataFrame, header: Dict[str, Any], project_name: str) -> None:
    """Zeichnet eine zweite PDF-Seite pro Pritsche mit Ladeplan-BSD-Matrix."""
    from reportlab.lib import colors

    pname = str(platform.get('Pritsche', 'Pritsche'))
    c.setFont('Helvetica-Bold', 16)
    c.drawString(margin, page_h - 36, f'Ladeplan BSD - {pname}')
    c.setFont('Helvetica', 9)
    c.drawString(margin, page_h - 54, f'Projekt / Datei: {project_name}')
    c.drawString(margin, page_h - 70, f'Erstellt: {datetime.now().strftime("%d.%m.%Y %H:%M")}')

    # Kopfbereich links/rechts ähnlich Tabellen-Ladeplan.
    left_x = margin
    right_x = page_w / 2 + 20
    top_y = page_h - 100
    c.setStrokeColor(colors.black)
    c.rect(left_x, top_y - 105, page_w / 2 - margin - 35, 105, stroke=1, fill=0)
    c.rect(right_x, top_y - 105, page_w / 2 - margin - 20, 105, stroke=1, fill=0)

    c.setFont('Helvetica-Bold', 10)
    c.drawString(left_x + 8, top_y - 18, 'Pritsche:')
    c.drawString(right_x + 8, top_y - 18, 'Pritschen- / Frachtdaten')
    c.setFont('Helvetica', 8)
    left_lines = [
        f'Fuhre: {header.get("Fuhre_Nr", "")}',
        f'Fuhrenoption: {header.get("Fuhrenoption", "")}',
        f'Pritschenname: {header.get("Pritschenname", "")}',
        f'Datum: {datetime.now().strftime("%d.%m.%Y")}',
    ]
    right_lines = [
        f'Pritschenhöhe: {safe_number(header.get("Pritschenhöhe_mm")):.0f} mm',
        f'Pritschenbreite: {safe_number(header.get("Pritschenbreite_mm")):.0f} mm',
        f'Frachthöhe: {safe_number(header.get("Frachthöhe_mm")):.0f} mm',
        f'Höhe gesamt: {safe_number(header.get("Höhe_gesamt_mm")):.0f} mm',
        f'Länge gesamt: {safe_number(header.get("Länge_gesamt_mm")):.0f} mm',
        f'Breite gesamt: {safe_number(header.get("Breite_gesamt_mm")):.0f} mm',
        f'Ladegewicht: {safe_number(header.get("Ladegewicht_kg")):.0f} kg',
    ]
    for i, line in enumerate(left_lines):
        c.drawString(left_x + 8, top_y - 38 - i * 14, line)
    for i, line in enumerate(right_lines):
        c.drawString(right_x + 8, top_y - 38 - i * 12, line)

    table_y = top_y - 135
    table_x = margin
    row_h = 20
    # A3 quer: kompakte Spaltenbreiten.
    col_defs = [
        ('Lage', 38),
        ('Vorne links', 128),
        ('Vorne rechts', 128),
        ('Hinten links', 128),
        ('Hinten rechts', 128),
        ('Höhe_mm', 56),
        ('Breite_mm', 62),
        ('Gesamtlänge_mm', 78),
        ('Gewicht_kg', 64),
    ]
    total_w = sum(w for _, w in col_defs)

    c.setFillColor(colors.lightgrey)
    c.rect(table_x, table_y, total_w, row_h, stroke=1, fill=1)
    c.setFillColor(colors.black)
    c.setFont('Helvetica-Bold', 7)
    cx = table_x
    for col, w in col_defs:
        c.rect(cx, table_y, w, row_h, stroke=1, fill=0)
        c.drawString(cx + 3, table_y + 7, col.replace('_mm', ' mm').replace('_kg', ' kg'))
        cx += w

    c.setFont('Helvetica', 6)
    y = table_y - row_h
    max_rows = int((table_y - 35) / row_h)
    rows = matrix_df.head(max_rows).copy() if matrix_df is not None and not matrix_df.empty else pd.DataFrame()
    if rows.empty:
        c.drawString(table_x, y + 6, 'Keine Ladeplan-BSD-Daten vorhanden')
        return

    for _, row in rows.iterrows():
        cx = table_x
        for col, w in col_defs:
            c.rect(cx, y, w, row_h, stroke=1, fill=0)
            value = row.get(col, '')
            if col in ['Höhe_mm', 'Breite_mm', 'Gesamtlänge_mm']:
                text = f'{safe_number(value):.0f}' if safe_number(value) else ''
            elif col == 'Gewicht_kg':
                text = f'{safe_number(value):.0f}' if safe_number(value) else ''
            else:
                text = str(value).replace('\n', ' / ')
            text = text[:35] if w >= 100 else text[:12]
            c.drawString(cx + 3, y + 7, text)
            cx += w
        y -= row_h
        if y < 30:
            break


def create_loading_pdf(
    placements_df: pd.DataFrame,
    platforms_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    warnings_df: pd.DataFrame,
    project_name: str = 'BVX Verladeplanung',
) -> bytes:
    """Erstellt einen einfachen A3-Pritschenplan als PDF pro Pritsche."""
    try:
        from reportlab.lib.pagesizes import A3, landscape
        from reportlab.pdfgen import canvas
        from reportlab.lib import colors
    except ImportError as exc:
        raise RuntimeError('Für den PDF-Export muss reportlab installiert sein: pip install reportlab') from exc

    output = io.BytesIO()
    c = canvas.Canvas(output, pagesize=landscape(A3))
    page_w, page_h = landscape(A3)
    margin = 24

    if platforms_df is None or platforms_df.empty:
        c.drawString(margin, page_h - margin, 'Keine Pritschen vorhanden')
        c.save()
        return output.getvalue()

    for _, platform in platforms_df.iterrows():
        pname = str(platform.get('Pritsche', 'Pritsche'))
        srow = summary_df[summary_df['Pritsche'].astype(str) == pname]
        srow = srow.iloc[0] if not srow.empty else pd.Series(dtype=object)

        c.setFont('Helvetica-Bold', 16)
        c.drawString(margin, page_h - 36, f'Pritschenplan - {pname}')
        c.setFont('Helvetica', 9)
        c.drawString(margin, page_h - 54, f'Projekt / Datei: {project_name}')
        c.drawString(margin, page_h - 70, f'Erstellt: {datetime.now().strftime("%d.%m.%Y %H:%M")}')

        info_x = page_w - 290
        info_y = page_h - 40
        c.setFont('Helvetica-Bold', 10)
        c.drawString(info_x, info_y, 'Info Pritsche')
        c.setFont('Helvetica', 8)
        info_lines = [
            f'Fuhrenoption: {platform.get("Fuhrenoption", "")}',
            f'Länge genutzt: {safe_number(srow.get("Länge genutzt_mm")):.0f} / {safe_number(srow.get("Max Länge effektiv_mm")):.0f} mm',
            f'Breite genutzt: {safe_number(srow.get("Breite genutzt_mm")):.0f} / {safe_number(srow.get("Max Breite_mm")):.0f} mm',
            f'Höhe genutzt: {safe_number(srow.get("Höhe genutzt_mm")):.0f} / {safe_number(srow.get("Max Höhe_mm")):.0f} mm',
            f'Gewicht: {safe_number(srow.get("Gewicht genutzt_kg")):.0f} / {safe_number(srow.get("Max Gewicht_kg")):.0f} kg',
        ]
        for i, line in enumerate(info_lines):
            c.drawString(info_x, info_y - 16 - i * 13, line)

        hint_x = margin
        hint_y = page_h - 105
        c.setFont('Helvetica-Bold', 9)
        c.drawString(hint_x, hint_y, 'Infos zur Verladung')
        c.setFont('Helvetica', 8)
        hints = [
            '- Unterleghölzer gemäss Einstellung einlegen',
            '- Bunde / Bauteile gemäss Plan laden',
            '- Sichtseite / Schutz gemäss Projektvorgabe beachten',
            '- Ladung sichern und Verladereihenfolge prüfen',
        ]
        for i, line in enumerate(hints):
            c.drawString(hint_x, hint_y - 14 - i * 12, line)

        # Zeichnungsbereiche
        top_y = 205
        _pdf_draw_view(c, placements_df, platform, margin, top_y, 520, 280, 'side', 'Seitenansicht')
        _pdf_draw_view(c, placements_df, platform, margin + 550, top_y, 210, 280, 'back', 'Rückansicht')
        _pdf_draw_view(c, placements_df, platform, margin, 35, 760, 135, 'top', 'Draufsicht')

        # Warnungen
        pwarnings = warnings_df[warnings_df['Pritsche'].astype(str) == pname] if warnings_df is not None and not warnings_df.empty else pd.DataFrame()
        c.setFont('Helvetica-Bold', 8)
        c.drawString(page_w - 290, 150, 'Warnungen')
        c.setFont('Helvetica', 7)
        if pwarnings.empty:
            c.drawString(page_w - 290, 136, 'Keine Warnungen')
        else:
            for i, (_, wrn) in enumerate(pwarnings.head(8).iterrows()):
                c.drawString(page_w - 290, 136 - i * 11, f"- {wrn.get('Einheit_ID','')}: {wrn.get('Warnung','')}")

        # QS Feld
        c.setStrokeColor(colors.black)
        c.rect(page_w - 290, 35, 250, 60, stroke=1, fill=0)
        c.setFont('Helvetica', 8)
        c.drawString(page_w - 280, 78, 'Qualitätssicherung')
        c.drawString(page_w - 280, 58, 'Datum: __________________')
        c.drawString(page_w - 140, 58, 'Unterschrift: __________________')

        c.showPage()

        # Zweite Seite: Ladeplan BSD Matrix je Pritsche, ähnlich Excel-Beispiel PB 6.
        matrix = create_bsd_matrix_for_platform(placements_df, platform)
        if not matrix.empty:
            header = create_bsd_header_for_platform(platform, summary_df, warnings_df)
            _pdf_draw_bsd_matrix_page(c, page_w, page_h, margin, platform, matrix, header, project_name)
            c.showPage()

    c.save()
    return output.getvalue()


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
    default_general_spacer = safe_number(standards.get('Standard_Einlage_allgemein'), 0.0)
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
    st.caption('Kantholz = liegt direkt auf der Pritsche und zählt zur Frachthöhe. Bundeinlage/Lagenholz = Einlage zwischen Bunden/Lagen. Einlage allgemein = Einlage zwischen einzelnen Bauteilen; sie wird auch bei gestapelten Einzelbauteilen berücksichtigt.')
    col1, col2, col3, col4 = st.columns(4)
    base_wood_height = col1.number_input('Standard Kantholz erste Lage mm', min_value=0.0, max_value=300.0, value=float(default_base_wood), step=5.0)
    bundle_spacer_height = col2.number_input('Standard Bundeinlage / Lagenholz mm', min_value=0.0, max_value=200.0, value=float(default_layer_spacer), step=5.0)
    general_spacer_height = col3.number_input('Einlage allgemein zwischen jedem Bauteil mm', min_value=0.0, max_value=200.0, value=float(default_general_spacer), step=5.0, help='0 = aus. Wenn grösser 0, wird die Einlage zwischen gestapelten Einzelbauteilen und innerhalb eines Bundes eingezeichnet und in der Höhe berücksichtigt.')
    gap_length = col4.number_input('Längenversatz je Lage mm', min_value=0.0, max_value=500.0, value=float(default_gap), step=10.0)

    # Standards werden für die Berechnung aktualisiert. Pritschenwerte aus Excel überschreiben diese Defaults pro Pritsche.
    standards['Holzdichte'] = density
    standards['Max_Bundgewicht'] = max_bundle_weight
    standards['Standard_Kantholz_erste_Lage'] = base_wood_height
    standards['Standard_Einlage_zwischen_Lagen'] = bundle_spacer_height
    standards['Standard_Einlage_allgemein'] = general_spacer_height
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
        general_spacer_height=general_spacer_height,
        same_height=same_height,
        same_width=same_width,
        same_quality=same_quality,
        same_profile=same_profile,
        label_attr=main_attr,
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
                'Kantholz_erste_Lage_mm': st.column_config.NumberColumn('Kantholz erste Lage mm'),
                'Einlage_zwischen_Lagen_mm': st.column_config.NumberColumn('Bundeinlage / Lagenholz mm'),
                'Einlage_allgemein_mm': st.column_config.NumberColumn('Einlage allgemein mm'),
            },
            key='pritschen_editor_excel',
        )

    # Aktuelle Unterlegholz-Einstellungen global auf alle Pritschen anwenden.
    # Damit überschreiben die Eingabefelder veraltete Werte aus der Excel-Stammdatendatei.
    if not pritschen_edit.empty:
        pritschen_edit = pritschen_edit.copy()
        pritschen_edit['Kantholz_erste_Lage_mm'] = float(base_wood_height)
        pritschen_edit['Einlage_zwischen_Lagen_mm'] = float(bundle_spacer_height)
        pritschen_edit['Einlage_allgemein_mm'] = float(general_spacer_height)

    st.subheader('5. Platzierung / Automatik')
    st.caption('Geometrisch mittige Ausrichtung ist fest aktiv. Die fertige Lage wird in X/Y mittig auf der Pritsche verschoben. Keine Gewichts-/Schwerpunktoptimierung.')
    col1, col2, col3, col4 = st.columns(4)
    allow_beside = col1.checkbox('Nebeneinander erlauben', value=True)
    allow_stack = col2.checkbox('Übereinander erlauben', value=True)
    allow_rotation = col3.checkbox('90° drehen erlauben, wenn Pritsche es erlaubt', value=False)
    center_geometric = True
    max_fuhren = col4.number_input('Max. Fuhren Sicherheitslimit', min_value=1, max_value=200, value=50, step=1)

    placements_df, summary_df, platforms_used_df, fuhren_log_df = create_variant_a_loading_plan(
        units_df,
        options_edit,
        pritschen_edit,
        standards=standards,
        allow_beside=allow_beside,
        allow_stack=allow_stack,
        allow_rotation=allow_rotation,
        center_geometric=center_geometric,
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

    edited_placements_df = clean_placements_dataframe(placements_df)
    edited_summary_df = recompute_summary_from_placements(edited_placements_df, platforms_used_df) if not platforms_used_df.empty else summary_df
    warnings_plan_df = compute_loading_warnings(edited_placements_df, platforms_used_df)

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(['Verladeeinheiten', 'Fuhrenübersicht', 'Platzierung / manuell', 'Ladeplan BSD', 'Warnungen', 'Ansichten', 'Export'])

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
        st.dataframe(edited_summary_df, use_container_width=True, hide_index=True)

    with tab3:
        st.markdown('**Platzierung der Verladeeinheiten**')
        st.caption('Hier können Positionen manuell angepasst werden. Für die Ansicht und den Export werden die geänderten Werte verwendet.')
        edited_placements_df = st.data_editor(
            edited_placements_df,
            use_container_width=True,
            hide_index=True,
            num_rows='fixed',
            column_config={
                'Fuhre_Nr': st.column_config.NumberColumn('Fuhre'),
                'X_mm': st.column_config.NumberColumn('X mm'),
                'Y_mm': st.column_config.NumberColumn('Y mm'),
                'Z_mm': st.column_config.NumberColumn('Z mm'),
                'Länge_mm': st.column_config.NumberColumn('Länge mm'),
                'Breite_mm': st.column_config.NumberColumn('Breite mm'),
                'Höhe_mm': st.column_config.NumberColumn('Höhe mm'),
                'Drehung': st.column_config.NumberColumn('Drehung'),
                'Gewicht_kg': st.column_config.NumberColumn('Gewicht kg'),
            },
            key='placements_manual_editor',
        )
        edited_placements_df = clean_placements_dataframe(edited_placements_df)
        edited_summary_df = recompute_summary_from_placements(edited_placements_df, platforms_used_df) if not platforms_used_df.empty else summary_df
        warnings_plan_df = compute_loading_warnings(edited_placements_df, platforms_used_df)
        if not_loaded_count:
            st.error('Nicht alle Verladeeinheiten konnten automatisch platziert werden. Freigegebene Fuhrenoptionen, Pritschenmaße oder Bundbildung prüfen.')

    with tab4:
        bsd_header_df, bsd_matrix_df = create_all_bsd_matrices(
            edited_placements_df,
            platforms_used_df,
            edited_summary_df,
            warnings_plan_df,
        )
        st.markdown('**Ladeplan BSD je Pritsche**')
        st.caption('Die Tabelle wird automatisch für jede belegte Pritsche erstellt. Grundlage ist die vorhandene Platzierung: vorne/hinten wird über X, links/rechts über Y bestimmt.')

        if bsd_header_df.empty or bsd_matrix_df.empty:
            st.warning('Für die aktuelle Verladung wurde kein Ladeplan BSD erzeugt.')
        else:
            selected_bsd_platform = st.selectbox('Pritsche für Ladeplan BSD', bsd_header_df['Pritsche'].astype(str).tolist(), key='bsd_platform_select')
            bsd_info = bsd_header_df[bsd_header_df['Pritsche'].astype(str) == selected_bsd_platform]
            if not bsd_info.empty:
                hrow = bsd_info.iloc[0]
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric('Ladegewicht', f"{safe_number(hrow.get('Ladegewicht_kg')):.0f} kg")
                c2.metric('Frachthöhe', f"{safe_number(hrow.get('Frachthöhe_mm')):.0f} mm")
                c3.metric('Länge gesamt', f"{safe_number(hrow.get('Länge_gesamt_mm')):.0f} mm")
                c4.metric('Breite gesamt', f"{safe_number(hrow.get('Breite_gesamt_mm')):.0f} mm")
                c5.metric('Warnungen', int(safe_number(hrow.get('Warnungen'))))

            selected_matrix = bsd_matrix_df[bsd_matrix_df['Pritsche'].astype(str) == selected_bsd_platform].copy()
            display_cols = [
                'Lage', 'Vorne links', 'Vorne rechts', 'Hinten links', 'Hinten rechts',
                'Höhe_mm', 'Breite_mm', 'Gesamtlänge_mm', 'Gewicht_kg', 'Anzahl_Einheiten'
            ]
            st.dataframe(selected_matrix[display_cols], use_container_width=True, hide_index=True)

            with st.expander('Alle Ladeplan-BSD-Kopfdaten und Matrizen anzeigen', expanded=False):
                st.markdown('**Kopfdaten**')
                st.dataframe(bsd_header_df, use_container_width=True, hide_index=True)
                st.markdown('**Matrix alle Pritschen**')
                st.dataframe(bsd_matrix_df, use_container_width=True, hide_index=True)

    with tab5:
        if warnings_plan_df.empty:
            st.success('Keine Warnungen gefunden.')
        else:
            severe_count = len(warnings_plan_df)
            st.warning(f'{severe_count} Warnung(en) gefunden.')
            st.dataframe(warnings_plan_df, use_container_width=True, hide_index=True)

    with tab6:
        if platforms_used_df.empty:
            st.warning('Keine Pritsche für die Ansicht vorhanden.')
        else:
            selected_platform = st.selectbox('Fuhre / Pritsche für Ansicht', platforms_used_df['Pritsche'].tolist())
            info_row = edited_summary_df[edited_summary_df['Pritsche'] == selected_platform]
            if not info_row.empty:
                row = info_row.iloc[0]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric('Länge genutzt', f"{row['Länge genutzt_mm']:.0f} mm")
                c2.metric('Breite genutzt', f"{row['Breite genutzt_mm']:.0f} mm")
                c3.metric('Höhe genutzt', f"{row['Höhe genutzt_mm']:.0f} mm")
                c4.metric('Gewicht', f"{row['Gewicht genutzt_kg']:.0f} kg")

            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(draw_loading_view(edited_placements_df, platforms_used_df, selected_platform, 'side'), use_container_width=True)
            with col2:
                st.plotly_chart(draw_loading_view(edited_placements_df, platforms_used_df, selected_platform, 'back'), use_container_width=True)
            st.plotly_chart(draw_loading_view(edited_placements_df, platforms_used_df, selected_platform, 'top'), use_container_width=True)

    with tab7:
        # Falls der Ladeplan-BSD-Tab nicht angezeigt wurde, trotzdem für den Export erstellen.
        if 'bsd_header_df' not in locals() or 'bsd_matrix_df' not in locals():
            bsd_header_df, bsd_matrix_df = create_all_bsd_matrices(edited_placements_df, platforms_used_df, edited_summary_df, warnings_plan_df)

        excel_data = create_loading_excel(
            sorted_parts,
            units_df,
            edited_placements_df,
            platforms_used_df,
            edited_summary_df,
            options_df=options_edit,
            fuhren_log_df=fuhren_log_df,
            warnings_df=warnings_plan_df,
            bsd_header_df=bsd_header_df,
            bsd_matrix_df=bsd_matrix_df,
        )
        st.download_button(
            label='Verladeplanung als Excel herunterladen',
            data=excel_data,
            file_name=f"{uploaded_file.name.replace('.bvx', '').replace('.BVX', '')}_verladeplanung.xlsx",
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        try:
            pdf_data = create_loading_pdf(
                edited_placements_df,
                platforms_used_df,
                edited_summary_df,
                warnings_plan_df,
                project_name=uploaded_file.name,
            )
            st.download_button(
                label='A3-Pritschenplan als PDF herunterladen',
                data=pdf_data,
                file_name=f"{uploaded_file.name.replace('.bvx', '').replace('.BVX', '')}_pritschenplan.pdf",
                mime='application/pdf',
            )
        except RuntimeError as exc:
            st.warning(str(exc))

        st.markdown('''
        **Hinweis:** Diese Version erstellt einen automatischen Grobvorschlag mit Variante A.
        Manuelles Umplatzieren erfolgt über die Platzierungstabelle. Drag-and-drop ist nicht enthalten.
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
