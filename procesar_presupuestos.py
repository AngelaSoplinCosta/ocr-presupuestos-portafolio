#!/usr/bin/env python3
"""Extractor auditable de presupuestos escaneados (MVP v3).

Compatible con Python 3.9. Todos los importes y cálculos usan Decimal.
El PDF de entrada se abre únicamente en modo lectura.
"""

import argparse
import difflib
import hashlib
import json
import logging
import re
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple


DETAIL_COLUMNS = [
    "archivo_origen",
    "pagina",
    "orden_documento",
    "orden_pagina",
    "posicion_y",
    "tipo_fila",
    "nivel_jerarquia",
    "codigo_original",
    "codigo_normalizado",
    "codigo_padre",
    "categoria_codigo",
    "categoria",
    "grupo_codigo",
    "grupo",
    "subgrupo_codigo",
    "subgrupo",
    "item",
    "descripcion",
    "und_ocr",
    "und",
    "metrado_ocr",
    "metrado",
    "precio_ocr",
    "precio_soles",
    "parcial_ocr",
    "parcial_soles",
    "total_agrupador_soles",
    "texto_fila_ocr",
    "regla_normalizacion",
    "estado_revision",
    "motivo_revision",
    "fecha_procesamiento",
]

PARTIDAS_COLUMNS = [
    "archivo_origen",
    "pagina",
    "lugar",
    "cliente",
    "fecha_costo",
    "codigo_presupuesto",
    "codigo_subpresupuesto",
    "categoria_codigo",
    "categoria",
    "grupo_codigo",
    "grupo",
    "subgrupo_codigo",
    "subgrupo",
    "item_original",
    "item",
    "descripcion",
    "unidad_original",
    "und",
    "metrado",
    "precio_soles",
    "parcial_soles",
    "estado_revision",
    "motivo_revision",
]

ESTRUCTURA_COLUMNS = [
    "archivo_origen",
    "orden_documento",
    "pagina",
    "nivel",
    "codigo_original",
    "codigo",
    "titulo",
    "codigo_padre",
    "total_soles",
    "estado_revision",
    "motivo_revision",
]

REVISION_OCR_COLUMNS = [
    "archivo_origen",
    "pagina",
    "tipo_incidencia",
    "texto_fila_ocr",
    "campo",
    "valor_original",
    "valor_propuesto",
    "regla_aplicada",
    "motivo_revision",
]

UNCLASSIFIED_COLUMNS = [
    "archivo_origen",
    "pagina",
    "orden_pagina",
    "posicion_y",
    "texto_fila_ocr",
    "tokens_detectados",
    "posible_item",
    "posible_descripcion",
    "posible_und",
    "posible_metrado",
    "posible_precio",
    "posible_parcial",
    "motivo_no_clasificacion",
    "fecha_procesamiento",
]

CONTROL_COLUMNS = [
    "archivo_origen",
    "pagina",
    "filas_detectadas_en_tabla",
    "categorias",
    "grupos",
    "subgrupos",
    "partidas",
    "continuaciones",
    "filas_no_clasificadas",
    "filas_exportadas",
    "estado_control",
    "motivo_control",
    "filas_estructurales_exportadas",
    "continuaciones_absorbidas",
    "ruido_documental",
    "filas_descartadas",
    "item_x_inicio",
    "descripcion_x_inicio",
    "und_x_inicio",
    "metrado_x_inicio",
    "precio_x_inicio",
    "parcial_x_inicio",
    "metodo_deteccion_bandas",
]

SUMMARY_COLUMNS = [
    "archivo_origen",
    "lugar",
    "cliente",
    "fecha_costo",
    "codigo_presupuesto",
    "codigo_subpresupuesto",
    "costo_directo_soles",
    "gastos_generales_porcentaje",
    "gastos_generales_soles",
    "utilidad_porcentaje",
    "utilidad_soles",
    "subtotal_soles",
    "igv_porcentaje",
    "igv_soles",
    "presupuesto_total_soles",
    "monto_en_letras",
    "estado_revision",
    "motivo_revision",
    "fecha_procesamiento",
]

V6_PARTIDAS_COLUMNS = [
    "Orden",
    "Página PDF",
    "Item corregido",
    "Descripción",
    "Und",
    "Metrado",
    "Precio S/",
    "Parcial S/",
    "Estado general",
    "Severidad",
    "Campo observado",
    "Valor original OCR",
    "Valor corregido o sugerido",
    "Motivo",
    "Acción requerida",
    "Estado revisión",
    "Valor aprobado",
    "Comentario revisor",
    "Ruta jerárquica",
    "Capítulo código",
    "Capítulo",
    "Subcapítulo código",
    "Subcapítulo",
    "Sección código",
    "Sección",
    "Subsección código",
    "Subsección",
    "Parcial calculado",
    "Diferencia",
    "Estado cálculo",
    "Item OCR",
    "Unidad OCR",
    "Método corrección",
    "Confianza",
    "Nota",
    "Parcial OCR S/",
    "Parcial corregido S/",
    "Parcial utilizado S/",
    "Método corrección código",
    "Confianza código",
    "Método corrección unidad",
    "Confianza unidad",
    "Método corrección metrado",
    "Confianza metrado",
    "Método corrección precio",
    "Confianza precio",
    "Método corrección parcial",
    "Confianza parcial",
    "Trazabilidad por campo",
]

V6_ESTRUCTURA_COLUMNS = [
    "Orden documento",
    "Página PDF",
    "Nivel",
    "Nodo ID",
    "Código OCR",
    "Código corregido",
    "Título",
    "Nodo padre",
    "Ruta jerárquica",
    "Total OCR S/",
    "Total corregido S/",
    "Diferencia S/",
    "Corrección aplicada",
    "Estado código",
    "Candidatos",
]

V6_CORRECCIONES_COLUMNS = [
    "Tipo",
    "Página PDF",
    "Referencia",
    "Descripción",
    "Campo",
    "Valor original/OCR",
    "Valor corregido",
    "Método",
    "Confianza",
    "Tipo confusión",
    "Evidencias",
    "Puntuación",
    "Margen",
    "Código aplicado",
    "Motivo",
    "Severidad",
    "Acción requerida",
    "Referencia revisión humana",
]

V6_CONTROL_COLUMNS = [
    "Página PDF",
    "Filas detectadas OCR",
    "Partidas exportadas versión anterior",
    "Partidas finales",
    "Filas recuperadas",
    "Nodos jerárquicos",
    "Continuaciones absorbidas",
    "Ruido documental",
    "Filas no clasificadas",
    "Filas descartadas",
    "Suma parcial final S/",
    "Estado",
]

CODE_REVIEW_COLUMNS = [
    "ID revisión",
    "Página PDF",
    "Orden",
    "Tipo fila",
    "Descripción",
    "Item OCR",
    "Candidato 1",
    "Puntaje candidato 1",
    "Candidato 2",
    "Puntaje candidato 2",
    "Evidencias",
    "Padre o ruta",
    "Código anterior",
    "Código posterior",
    "Confianza automática",
    "Código aprobado",
    "Estado revisión",
    "Comentario revisor",
]

CLIENT_REVIEW_COLUMNS = [
    "ID revisión",
    "Página PDF",
    "Orden",
    "Tipo de fila",
    "Item OCR",
    "Item corregido",
    "Descripción",
    "Campo observado",
    "Valor original",
    "Candidato 1",
    "Candidato 2",
    "Valor sugerido",
    "Motivo",
    "Severidad",
    "Confianza",
    "Acción requerida",
    "Valor aprobado",
    "Estado revisión",
    "Comentario revisor",
]

NUMERIC_REVIEW_FIELDS = {
    "metrado",
    "precio_soles",
    "parcial_soles",
}

HUMAN_NUMERIC_METHOD = "revisión visual aprobada + validación matemática"
HUMAN_NUMERIC_SEVERITY = "INFORMATIVA"
HUMAN_NUMERIC_ACTION = "Ninguna, corrección validada"

DIFFERENCE_COLUMNS = [
    "hoja",
    "clave",
    "columna",
    "valor_obtenido",
    "valor_esperado",
    "diferencia",
    "severidad",
    "explicación",
]

HIERARCHY_LEVELS = (
    "proyecto",
    "capitulo",
    "subcapitulo",
    "seccion",
    "subseccion",
)

CODE_HIGH_CONFIDENCE_MARGIN = 4

# Alias conservados para consumidores de la versión anterior.
DETALLE_COLUMNS = DETAIL_COLUMNS
RESUMEN_COLUMNS = SUMMARY_COLUMNS

ROW_TYPES = {
    "categoria",
    "grupo",
    "subgrupo",
    "partida",
    "continuacion_descripcion",
    "fila_no_clasificada",
    "ruido_documental",
}

STRICT_ITEM_RE = re.compile(r"^\d{1,4}(?:\.[A-Z0-9]{1,3})*$", re.IGNORECASE)
SUSPECT_ITEM_RE = re.compile(
    r"^(?:\d{1,4}(?:[.,]?[A-Z0-9]{1,3})*|[A-Z]\d{1,3}(?:\.[A-Z0-9]{1,3})*)$",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
SUMMARY_LABEL_RE = re.compile(
    r"^(?:COSTO\s+DIRECTO|GASTOS\s+GENERALES|G\.?\s*G\.?|UTILIDAD|"
    r"SUB-?\s*TOTAL|IGV|PRESUPUESTO\s+TOTAL|TOTAL\s+PRESUPUESTO|SON\s*:)",
    re.IGNORECASE,
)
NOISE_RE = re.compile(
    r"^(?:P[ÁA]GINA\s+\d+|\d+\s*$|VICTOR\s+HUGO|AZAÑERO|INGENIER[OA]|"
    r"REG\.?\s*CIP|FIRMA|SELLO|ELABORADO|REVISADO|APROBADO)",
    re.IGNORECASE,
)

VALID_UNITS = {
    "m",
    "m.",
    "m2",
    "m²",
    "m3",
    "m³",
    "m3xk",
    "m3-k",
    "km",
    "cm",
    "mm",
    "kg",
    "g",
    "t",
    "ton",
    "l",
    "l.",
    "lt",
    "lt.",
    "und",
    "und.",
    "u",
    "pza",
    "pto",
    "pto.",
    "glb",
    "glb.",
    "gb",
    "mes",
    "día",
    "dia",
    "h",
    "hh",
    "hm",
    "ha",
}
UNIT_ALIASES = {
    "m.": "m",
    "m2": "m²",
    "m²": "m²",
    "m3": "m³",
    "m³": "m³",
    "l.": "l",
    "lt.": "lt",
    "und.": "und",
    "pto.": "pto",
    "glb.": "glb",
}

AuditCallback = Callable[[str, str, int, str, str], None]


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2.0


@dataclass
class VisualLine:
    page: int
    top: float
    words: List[Word]
    order_page: int = 0

    @property
    def text(self) -> str:
        return " ".join(word.text for word in sorted(self.words, key=lambda item: item.x0))

    @property
    def tokens_json(self) -> str:
        tokens = [
            {
                "texto": word.text,
                "x0": round(word.x0, 2),
                "x1": round(word.x1, 2),
                "y": round(word.top, 2),
            }
            for word in sorted(self.words, key=lambda item: item.x0)
        ]
        return json.dumps(tokens, ensure_ascii=False, separators=(",", ":"))


@dataclass
class Band:
    name: str
    start: float
    end: float


@dataclass
class PageBands:
    page: int
    item_start: float
    description_start: float
    unit_start: float
    metrado_start: float
    price_start: float
    partial_start: float
    page_end: float
    method: str
    review_reason: str = ""

    def bands(self) -> List[Band]:
        return [
            Band("item", self.item_start, self.description_start),
            Band("description", self.description_start, self.unit_start),
            Band("unit", self.unit_start, self.metrado_start),
            Band("metrado", self.metrado_start, self.price_start),
            Band("price", self.price_start, self.partial_start),
            Band("partial", self.partial_start, self.page_end),
        ]


@dataclass
class NumberResult:
    original: str
    value: Optional[Decimal]
    normalized: str = ""
    rule: str = ""
    rejection: str = ""


@dataclass
class CodeResult:
    original: str
    normalized: str
    rule: str = ""
    review_reason: str = ""
    candidates: List[str] = field(default_factory=list)


@dataclass
class UnitResult:
    original: str
    normalized: str
    reassigned_text: str = ""
    rule: str = ""
    review_reason: str = ""
    incident_types: List[str] = field(default_factory=list)


@dataclass
class DecimalRecovery:
    value: Optional[Decimal]
    rule: str = ""
    review_reason: str = ""
    candidates: List[Decimal] = field(default_factory=list)


@dataclass
class GeneralData:
    lugar: str = ""
    cliente: str = ""
    fecha_costo: Optional[date] = None
    codigo_presupuesto: str = ""
    codigo_subpresupuesto: str = ""


@dataclass
class ResumenEconomico:
    costo_directo_soles: Optional[Decimal] = None
    gastos_generales_porcentaje: Optional[Decimal] = None
    gastos_generales_soles: Optional[Decimal] = None
    utilidad_porcentaje: Optional[Decimal] = None
    utilidad_soles: Optional[Decimal] = None
    subtotal_soles: Optional[Decimal] = None
    igv_porcentaje: Optional[Decimal] = None
    igv_soles: Optional[Decimal] = None
    presupuesto_total_soles: Optional[Decimal] = None
    monto_en_letras: str = ""
    page: int = 0


@dataclass
class AppliedNumericCorrection:
    field_name: str
    original_value: Decimal
    corrected_value: Decimal
    method: str
    confidence: str
    note: str
    severity: str
    action_required: str
    reviewer_reference: str
    approval_id: str


@dataclass
class NumericReviewApproval:
    approval_id: str
    document_sha256: str
    source_filename: str
    page: int
    row_order: int
    field_name: str
    ocr_value: Decimal
    approved_value: Decimal
    normalized_description: str
    reviewer_reference: str
    status: str
    reason: str


@dataclass
class PartidaPresentation:
    general_state: str
    severity: str = ""
    observed_field: str = ""
    original_value: object = ""
    corrected_or_suggested: object = ""
    reason: str = ""
    required_action: str = ""
    review_state: str = "NO REQUIERE"
    approved_value: object = ""
    reviewer_comment: str = ""


@dataclass
class ClientReviewRecord:
    review_id: str
    page: int
    order: int
    row_type: str
    item_ocr: str
    corrected_item: str
    description: str
    observed_field: str
    original_value: object
    candidate_1: object
    candidate_2: object
    suggested_value: object
    reason: str
    severity: str
    confidence: str
    required_action: str
    approved_value: object = ""
    review_state: str = "PENDIENTE"
    reviewer_comment: str = ""


@dataclass
class ExtractedRow:
    archivo_origen: str
    pagina: int
    orden_documento: int
    orden_pagina: int
    posicion_y: float
    texto_fila_ocr: str
    tokens_detectados: str
    tipo_fila: str
    codigo_original: str = ""
    codigo_normalizado: str = ""
    codigo_padre: str = ""
    descripcion: str = ""
    description_x: float = 0.0
    und_ocr: str = ""
    und: str = ""
    metrado_ocr: str = ""
    metrado: Optional[Decimal] = None
    precio_ocr: str = ""
    precio_soles: Optional[Decimal] = None
    parcial_ocr: str = ""
    parcial_ocr_decimal: Optional[Decimal] = None
    parcial_soles: Optional[Decimal] = None
    total_agrupador_soles: Optional[Decimal] = None
    nivel_jerarquia: Optional[int] = None
    categoria_codigo: str = ""
    categoria: str = ""
    grupo_codigo: str = ""
    grupo: str = ""
    subgrupo_codigo: str = ""
    subgrupo: str = ""
    regla_normalizacion: str = ""
    estado_revision: str = "OK"
    motivo_revision: str = ""
    posible_item: str = ""
    posible_descripcion: str = ""
    posible_und: str = ""
    posible_metrado: str = ""
    posible_precio: str = ""
    posible_parcial: str = ""
    motivo_no_clasificacion: str = ""
    assigned_tokens: Dict[str, List[Word]] = field(default_factory=dict)
    unit_incident_types: List[str] = field(default_factory=list)
    fila_recuperada: bool = False
    metodo_correccion: str = ""
    confianza: str = "SIN_CAMBIO"
    nota: str = ""
    capitulo_codigo: str = ""
    capitulo: str = ""
    subcapitulo_codigo: str = ""
    subcapitulo: str = ""
    seccion_codigo: str = ""
    seccion: str = ""
    subseccion_codigo: str = ""
    subseccion: str = ""
    ruta_jerarquica: str = ""
    codigo_pendiente: bool = False
    nivel_forzado_v6: str = ""
    padre_esperado_id: str = ""
    human_numeric_corrections: Dict[str, AppliedNumericCorrection] = field(
        default_factory=dict
    )

    @property
    def item(self) -> str:
        if self.codigo_pendiente:
            return ""
        return self.codigo_normalizado or self.codigo_original

    def add_rule(self, rule: str) -> None:
        if rule and rule not in self.regla_normalizacion.split("; "):
            self.regla_normalizacion = _append_message(self.regla_normalizacion, rule)

    def add_review(self, reason: str) -> None:
        if reason:
            self.estado_revision = "REVISAR"
            self.motivo_revision = _append_message(self.motivo_revision, reason)


@dataclass
class HierarchyState:
    categoria_codigo: str = ""
    categoria: str = ""
    categoria_x: float = 0.0
    grupo_codigo: str = ""
    grupo: str = ""
    grupo_x: float = 0.0
    subgrupo_codigo: str = ""
    subgrupo: str = ""
    subgrupo_x: float = 0.0


@dataclass
class PageControl:
    archivo_origen: str
    pagina: int
    filas_detectadas_en_tabla: int = 0
    categorias: int = 0
    grupos: int = 0
    subgrupos: int = 0
    partidas: int = 0
    continuaciones_absorbidas: int = 0
    filas_no_clasificadas: int = 0
    ruido_documental: int = 0
    filas_descartadas: int = 0
    item_x_inicio: Optional[float] = None
    descripcion_x_inicio: Optional[float] = None
    und_x_inicio: Optional[float] = None
    metrado_x_inicio: Optional[float] = None
    precio_x_inicio: Optional[float] = None
    parcial_x_inicio: Optional[float] = None
    metodo_deteccion_bandas: str = ""
    estado_control: str = "OK"
    motivo_control: str = ""
    partidas_antes_recuperacion: int = 0

    @property
    def filas_estructurales_exportadas(self) -> int:
        return self.categorias + self.grupos + self.subgrupos + self.partidas

    @property
    def filas_exportadas(self) -> int:
        return self.filas_estructurales_exportadas + self.filas_no_clasificadas

    @property
    def reconciled_total(self) -> int:
        return (
            self.filas_estructurales_exportadas
            + self.continuaciones_absorbidas
            + self.filas_no_clasificadas
            + self.ruido_documental
        )


@dataclass
class DocumentResult:
    general: GeneralData
    summary: ResumenEconomico
    rows: List[ExtractedRow]
    unclassified: List[ExtractedRow]
    controls: List[PageControl]
    validations: List[str]
    processed_at: datetime
    nodes_v6: List["HierarchyNode"] = field(default_factory=list)
    corrections_v6: List["CorrectionRecord"] = field(default_factory=list)
    total_pdf_pages: int = 0
    searchable_pdf: str = ""
    code_reviews: List["CodeReviewRecord"] = field(default_factory=list)


@dataclass
class RevisionIncident:
    archivo_origen: str
    pagina: int
    tipo_incidencia: str
    texto_fila_ocr: str
    campo: str
    valor_original: str
    valor_propuesto: str
    regla_aplicada: str
    motivo_revision: str


@dataclass
class CorrectionRecord:
    tipo: str
    pagina: int
    referencia: str
    descripcion: str
    campo: str
    original: object
    corrected: object
    method: str
    confidence: str
    confusion_type: str = ""
    evidence: str = ""
    score: int = 0
    margin: int = 0
    applied: object = ""
    reason: str = ""
    severity: str = ""
    action_required: str = ""
    reviewer_reference: str = ""


@dataclass
class HierarchyNode:
    order_document: int
    page: int
    level: str
    node_id: str
    code_ocr: str
    code: str
    title: str
    parent_id: str
    path: str
    total_ocr: Optional[Decimal]
    total: Optional[Decimal]
    difference: Optional[Decimal] = None
    correction: str = ""
    code_state: str = "OK"
    candidates: str = ""


@dataclass
class HierarchyStack:
    proyecto: Optional[HierarchyNode] = None
    capitulo: Optional[HierarchyNode] = None
    subcapitulo: Optional[HierarchyNode] = None
    seccion: Optional[HierarchyNode] = None
    subseccion: Optional[HierarchyNode] = None

    def get(self, level: str) -> Optional[HierarchyNode]:
        return getattr(self, level)

    def set(self, level: str, node: HierarchyNode) -> None:
        setattr(self, level, node)
        index = HIERARCHY_LEVELS.index(level)
        for lower in HIERARCHY_LEVELS[index + 1 :]:
            setattr(self, lower, None)

    def active_nodes(self, include_project: bool = True) -> List[HierarchyNode]:
        levels = HIERARCHY_LEVELS if include_project else HIERARCHY_LEVELS[1:]
        return [
            node
            for node in (self.get(level) for level in levels)
            if node is not None
        ]


@dataclass
class DocumentCodeCatalog:
    by_description: Dict[str, List[str]] = field(default_factory=dict)
    high_confidence_by_description: Dict[str, List[str]] = field(
        default_factory=dict
    )
    descriptions_by_code: Dict[str, Set[str]] = field(default_factory=dict)
    code_frequency: Dict[str, int] = field(default_factory=dict)
    description_frequency: Dict[str, int] = field(default_factory=dict)
    roles_by_description_code: Dict[Tuple[str, str], Set[str]] = field(
        default_factory=dict
    )


@dataclass
class CodeDecision:
    original: str
    final: str
    proposed: str = ""
    method: str = ""
    confidence: str = "SIN_CAMBIO"
    score: int = 0
    alternatives: List[str] = field(default_factory=list)


@dataclass
class CodeAuditRecord:
    page: int
    row_type: str
    description: str
    ocr_code: str
    current_code: str
    candidates: List[str] = field(default_factory=list)
    active_parent: str = ""
    previous_code: str = ""
    next_code: str = ""
    evidence: List[str] = field(default_factory=list)
    confidence: str = "BAJA"
    reason: str = ""


@dataclass
class CodeReviewRecord:
    review_id: str
    page: int
    order: int
    row_type: str
    description: str
    item_ocr: str
    candidate_1: str = ""
    candidate_1_score: int = 0
    candidate_2: str = ""
    candidate_2_score: int = 0
    evidence: str = ""
    parent_or_path: str = ""
    previous_code: str = ""
    next_code: str = ""
    automatic_confidence: str = "BAJA"
    approved_code: str = ""
    review_status: str = "PENDIENTE"
    reviewer_comment: str = ""


@dataclass
class WorkbookDifference:
    sheet: str
    key: str
    column: str
    obtained: object
    expected: object
    difference: object
    severity: str
    explanation: str


# Compatibilidad mínima para pruebas o integraciones de la versión anterior.
@dataclass
class RawPartida:
    page: int
    item: str
    descripcion: str
    und: str = ""
    metrado_raw: str = ""
    precio_raw: str = ""
    parcial_raw: str = ""
    item_sospechoso: bool = False


@dataclass
class Partida:
    archivo_origen: str
    lugar: str
    cliente: str
    fecha_costo: Optional[date]
    codigo_presupuesto: str
    codigo_subpresupuesto: str
    item: str
    descripcion: str
    und: str
    metrado: Optional[Decimal]
    precio_soles: Optional[Decimal]
    parcial_soles: Optional[Decimal]
    estado_revision: str
    motivo_revision: str
    fecha_procesamiento: datetime
    page: int = 0


def _append_message(current: str, message: str) -> str:
    if not message:
        return current
    parts = [part for part in current.split("; ") if part]
    if message not in parts:
        parts.append(message)
    return "; ".join(parts)


def default_audit_logger(
    original: str, normalized: str, page: int, reason: str, context: str
) -> None:
    logging.getLogger("presupuestos").info(
        "NORMALIZACION_OCR pagina=%s campo=%s original=%r normalizado=%r regla=%s",
        page,
        context,
        original,
        normalized,
        reason,
    )


def _strip_numeric_wrapper(raw: str) -> str:
    token = raw.strip().replace("\u00a0", "")
    token = re.sub(r"(?i)^s\s*[/|lI!]\s*\.?\s*", "", token)
    token = token.replace("%", "").replace("(", "").replace(")", "")
    return token.strip("[]{}:;")


def parse_ocr_number(
    raw: str,
    page: int = 0,
    context: str = "",
    audit: Optional[AuditCallback] = None,
    allow_high_precision: bool = False,
) -> NumberResult:
    original = "" if raw is None else str(raw)
    token = _strip_numeric_wrapper(original)
    if not token:
        return NumberResult(original=original, value=None, rejection="valor vacío")
    if any(character.isspace() for character in token):
        reason = "contiene más de un token OCR; no se fusiona"
        _log_rejection(original, page, context, reason)
        return NumberResult(original=original, value=None, rejection=reason)
    if not re.fullmatch(r"[+-]?\d[\d.,]*", token):
        reason = "contiene caracteres no numéricos"
        _log_rejection(original, page, context, reason)
        return NumberResult(original=original, value=None, rejection=reason)

    unsigned = token.lstrip("+-")
    sign = token[:1] if token[:1] in ("+", "-") else ""
    if ",." in unsigned or ".," in unsigned:
        reason = "separadores consecutivos inválidos"
        _log_rejection(original, page, context, reason)
        return NumberResult(original=original, value=None, rejection=reason)

    comma_count = unsigned.count(",")
    dot_count = unsigned.count(".")
    normalized = ""
    rule = ""
    if comma_count == 0 and dot_count == 0:
        normalized = sign + unsigned
    elif comma_count and dot_count:
        decimal_separator = "," if unsigned.rfind(",") > unsigned.rfind(".") else "."
        decimal_index = unsigned.rfind(decimal_separator)
        integer_part = re.sub(r"[.,]", "", unsigned[:decimal_index])
        decimal_part = unsigned[decimal_index + 1 :]
        if not integer_part or not decimal_part:
            return NumberResult(
                original=original, value=None, rejection="separadores incompletos"
            )
        if len(decimal_part) > 2 and not allow_high_precision:
            return NumberResult(
                original=original,
                value=None,
                rejection="precisión decimal no permitida",
            )
        normalized = sign + integer_part + "." + decimal_part
        rule = "Último separador usado como decimal; anteriores como miles"
    else:
        separator = "," if comma_count else "."
        parts = unsigned.split(separator)
        if any(part == "" for part in parts):
            return NumberResult(
                original=original, value=None, rejection="separador sin dígitos"
            )
        if len(parts) == 2:
            decimal_length = len(parts[1])
            if decimal_length in (1, 2):
                normalized = sign + parts[0] + "." + parts[1]
                if separator == ",":
                    rule = "Coma decimal convertida en punto"
            elif decimal_length > 2 and allow_high_precision:
                normalized = sign + parts[0] + "." + parts[1]
                rule = "Precisión decimal de porcentaje conservada"
            else:
                return NumberResult(
                    original=original,
                    value=None,
                    rejection="separador único ambiguo",
                )
        else:
            final_length = len(parts[-1])
            middle_are_thousands = all(len(part) == 3 for part in parts[1:-1])
            if final_length in (1, 2) and middle_are_thousands:
                normalized = sign + "".join(parts[:-1]) + "." + parts[-1]
                rule = "Último separador usado como decimal; anteriores como miles"
            elif final_length == 3 and all(len(part) == 3 for part in parts[1:]):
                normalized = sign + "".join(parts)
                rule = "Separadores usados como miles"
            else:
                return NumberResult(
                    original=original,
                    value=None,
                    rejection="patrón de separadores ambiguo",
                )
    try:
        value = Decimal(normalized)
    except InvalidOperation:
        return NumberResult(
            original=original, value=None, rejection="Decimal no válido"
        )
    if audit is not None and rule:
        audit(original, normalized, page, rule, context)
    return NumberResult(
        original=original, value=value, normalized=normalized, rule=rule
    )


def _log_rejection(original: str, page: int, context: str, reason: str) -> None:
    logging.getLogger("presupuestos").warning(
        "RECHAZO_NORMALIZACION pagina=%s campo=%s original=%r motivo=%s",
        page,
        context,
        original,
        reason,
    )


def normalize_ocr_number(
    raw: str,
    page: int = 0,
    context: str = "",
    audit: Optional[AuditCallback] = None,
    allow_high_precision: bool = False,
) -> Optional[Decimal]:
    return parse_ocr_number(
        raw, page, context, audit, allow_high_precision
    ).value


def is_item_code(value: str) -> bool:
    return bool(STRICT_ITEM_RE.fullmatch(value.strip()))


def looks_like_item_code(value: str) -> bool:
    return bool(SUSPECT_ITEM_RE.fullmatch(value.strip()))


def normalize_item_code(
    original: str,
    page: int = 0,
    evidence_codes: Optional[Set[str]] = None,
    audit: Optional[AuditCallback] = None,
) -> CodeResult:
    token = original.strip("[]| ")
    normalized = token
    rules: List[str] = []
    review: List[str] = []
    candidates: List[str] = []

    if "," in token:
        comma_candidate = token.replace(",", ".")
        if is_item_code(comma_candidate):
            normalized = comma_candidate
            rules.append("Coma en banda de ítem convertida en punto")
        else:
            review.append("La coma del código no pudo normalizarse con seguridad")

    # 4/A y 8/B nunca se sustituyen solo por aspecto.
    for digit, letter in (("4", "A"), ("8", "B")):
        match = re.search(r"\.%s(?=\.|$)" % digit, normalized)
        if match:
            candidate = (
                normalized[: match.start() + 1]
                + letter
                + normalized[match.end() :]
            )
            candidates.append(candidate)
            if evidence_codes and candidate in evidence_codes:
                normalized = candidate
                rules.append(
                    "%s/%s resuelto por código correcto repetido en el documento"
                    % (letter, digit)
                )
            else:
                review.append(
                    "Ambigüedad %s/%s; candidato: %s" % (letter, digit, candidate)
                )

    rule = "; ".join(rules)
    reason = "; ".join(review)
    if audit is not None and rule and normalized != token:
        audit(token, normalized, page, rule, "codigo_item")
    return CodeResult(
        original=token,
        normalized=normalized,
        rule=rule,
        review_reason=reason,
        candidates=candidates,
    )


def normalize_description_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    ascii_text = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]+", " ", ascii_text.upper()).strip()


def _code_quality(code: str) -> int:
    value = code.strip("[]| ,")
    score = 0
    if is_item_code(value):
        score += 4
    if re.search(r"\.[A-Z](?:\d+)?(?:\.|$)", value):
        score += 3
    if "," not in value and not value.endswith((".", ",")):
        score += 1
    if re.search(r"\.(?:4|8|0)(?:\d+)?$", value):
        score -= 1
    return score


def code_suspicion_reasons(
    code: str,
    description: str = "",
    catalog: Optional["DocumentCodeCatalog"] = None,
) -> List[str]:
    """Enumera indicios OCR sin decidir todavía una sustitución."""
    token = (code or "").strip("[]| ")
    normalized = token.upper().replace(",", ".")
    reasons: List[str] = []
    suffix_checks = (
        (r"\.8\d*$", "posible_confusion_8_B"),
        (r"\.0\d*$", "posible_confusion_0_C"),
        (r"\.4\d*$", "posible_confusion_4_A"),
    )
    for pattern, reason in suffix_checks:
        if re.search(pattern, normalized):
            reasons.append(reason)
    if token.endswith("."):
        reasons.append("codigo_incompleto_punto")
    if token.endswith(","):
        reasons.append("codigo_incompleto_coma")
    if re.fullmatch(r"\d{2,4}[A-Z]\d*", normalized):
        reasons.append("separador_esperado_ausente")
    if catalog is not None and description:
        key = normalize_description_key(description)
        canonical = catalog.high_confidence_by_description.get(key, [])
        current = normalized
        if canonical and current not in canonical:
            reasons.append("descripcion_asociada_a_otro_codigo")
    return list(dict.fromkeys(reasons))


def _is_canonical_document_code(row: ExtractedRow, code: str) -> bool:
    token = (code or "").upper().replace(",", ".").strip("[]| ")
    if not token or not is_item_code(token):
        return False
    if code_suspicion_reasons(row.codigo_original):
        # Una corrección contextual ALTA sí puede alimentar el catálogo en una
        # segunda construcción, pero una mera lectura OCR sospechosa no.
        return row.confianza == "ALTA" and not code_suspicion_reasons(token)
    return True


def build_document_code_catalog(
    rows: Sequence[ExtractedRow],
) -> DocumentCodeCatalog:
    """Construye ambos índices canónicos únicamente desde el documento."""
    grouped: Dict[str, List[str]] = {}
    high_grouped: Dict[str, List[str]] = {}
    descriptions_by_code: Dict[str, Set[str]] = {}
    code_frequency: Dict[str, int] = {}
    description_frequency: Dict[str, int] = {}
    roles_by_description_code: Dict[Tuple[str, str], Set[str]] = {}
    for row in rows:
        code = (
            row.codigo_normalizado or row.codigo_original
        ).upper().replace(",", ".").strip()
        key = normalize_description_key(row.descripcion)
        if not code or not key:
            continue
        grouped.setdefault(key, []).append(code)
        code_frequency[code] = code_frequency.get(code, 0) + 1
        description_frequency[key] = description_frequency.get(key, 0) + 1
        role = "partida" if row.tipo_fila == "partida" else "estructura"
        roles_by_description_code.setdefault((key, code), set()).add(role)
        if _is_canonical_document_code(row, code):
            high_grouped.setdefault(key, []).append(code)
            descriptions_by_code.setdefault(code, set()).add(key)
    by_description: Dict[str, List[str]] = {}
    for key, codes in grouped.items():
        unique = list(dict.fromkeys(codes))
        unique.sort(
            key=lambda code: (
                _code_quality(code),
                code_frequency.get(code, 0),
            ),
            reverse=True,
        )
        by_description[key] = unique
    high_confidence_by_description: Dict[str, List[str]] = {}
    for key, codes in high_grouped.items():
        high_confidence_by_description[key] = list(dict.fromkeys(codes))
    return DocumentCodeCatalog(
        by_description=by_description,
        high_confidence_by_description=high_confidence_by_description,
        descriptions_by_code=descriptions_by_code,
        code_frequency=code_frequency,
        description_frequency=description_frequency,
        roles_by_description_code=roles_by_description_code,
    )


def generate_code_candidates(
    original: str,
    description: str = "",
    catalog: Optional[DocumentCodeCatalog] = None,
) -> List[str]:
    token = original.strip("[]| ")
    candidates: List[str] = []

    def add(value: str) -> None:
        cleaned = value.strip("[]| ")
        if cleaned and cleaned != token and cleaned not in candidates:
            candidates.append(cleaned)

    if "," in token:
        add(token.replace(",", "."))
    if re.fullmatch(r"\d{2,4}[A-Z]", token, re.IGNORECASE):
        add(token[:-1] + "." + token[-1].upper())

    normalized_separator = token.replace(",", ".")
    substitutions = {"4": "A", "8": "B", "0": "C", "6": "G", "1": "I"}
    dot = normalized_separator.find(".")
    if dot >= 0:
        suffix = normalized_separator[dot + 1 :]
        for index, character in enumerate(suffix):
            replacement = substitutions.get(character)
            if replacement:
                add(
                    normalized_separator[: dot + 1 + index]
                    + replacement
                    + normalized_separator[dot + 2 + index :]
                )
    if token.endswith((".", ",")) and catalog is not None:
        # Un código truncado solo recibe opciones observadas realmente en el
        # documento. No se enumeran letras hipotéticas A-I.
        prefix = token[:-1]
        family = _code_family(prefix)
        for observed in catalog.code_frequency:
            if (
                family
                and _code_family(observed) == family
                and is_item_code(observed)
                and not code_suspicion_reasons(observed)
            ):
                add(observed)

    if catalog is not None:
        key = normalize_description_key(description)
        for code in catalog.by_description.get(key, []):
            add(code)
    return candidates


def _numeric_code_prefix(code: str) -> Optional[int]:
    match = re.match(r"^(\d{1,4})", code or "")
    return int(match.group(1)) if match else None


def _code_family(code: str) -> str:
    normalized = (code or "").upper().replace(",", ".").strip("[]| ")
    match = re.match(r"^(\d{1,4})", normalized)
    return match.group(1) if match else ""


def code_family_compatible(original: str, candidate: str) -> bool:
    """Impide saltos entre capítulos; tolera OCR sin familia numérica."""
    original_family = _code_family(original)
    candidate_family = _code_family(candidate)
    if original_family and candidate_family:
        return original_family == candidate_family
    return bool(candidate_family or candidate)


def _row_role(row: ExtractedRow) -> str:
    return "partida" if row.tipo_fila == "partida" else "estructura"


def code_role_compatible(
    candidate: str,
    row: ExtractedRow,
    catalog: DocumentCodeCatalog,
) -> bool:
    key = normalize_description_key(row.descripcion)
    observed_roles = catalog.roles_by_description_code.get((key, candidate), set())
    return not observed_roles or _row_role(row) in observed_roles


def _sequence_context_bonus(
    original: str,
    candidate: str,
    row: ExtractedRow,
    context_rows: Sequence[ExtractedRow],
) -> int:
    normalized = original.upper().replace(",", ".")
    page_codes = {
        item.codigo_original.upper().replace(",", ".")
        for item in context_rows
        if item.pagina == row.pagina and _row_role(item) == _row_role(row)
    }
    sequence = re.fullmatch(r"(\d{2,4})\.8([1-3])", normalized)
    proposed = re.fullmatch(r"(\d{2,4})\.B([1-3])", candidate.upper())
    if sequence and proposed and sequence.groups() == proposed.groups():
        base = sequence.group(1)
        if all("%s.8%s" % (base, number) in page_codes for number in (1, 2, 3)):
            return 12

    bridge = re.fullmatch(r"1000\.8", normalized)
    if (
        bridge
        and candidate.upper() == "1000.B"
        and "PUENTE" in normalize_description_key(row.descripcion)
    ):
        document_codes = {
            item.codigo_original.upper().replace(",", ".")
            for item in context_rows
            if _row_role(item) == "estructura"
        }
        if {"1000.A", "1000.C", "1000.D"}.issubset(document_codes):
            return 15
    return 0


def _row_context_code(row: ExtractedRow) -> str:
    return (
        row.codigo_normalizado or row.codigo_original
    ).upper().replace(",", ".").strip("[]| ")


def _same_context(left: ExtractedRow, right: ExtractedRow) -> bool:
    if _row_role(left) != _row_role(right):
        return False
    if left.codigo_padre and right.codigo_padre:
        return left.codigo_padre == right.codigo_padre
    return left.pagina == right.pagina


def _numeric_sequence_confirms_original(
    row: ExtractedRow,
    context_rows: Sequence[ExtractedRow],
) -> bool:
    token = _row_context_code(row)
    match = re.fullmatch(r"(\d{1,4})\.(\d+)", token)
    if not match:
        return False
    base, suffix = match.groups()
    number = int(suffix)
    if number <= 0:
        return False
    contextual = {
        _row_context_code(item)
        for item in context_rows
        if item is not row and _same_context(row, item)
    }
    return (
        "%s.%s" % (base, number - 1) in contextual
        and "%s.%s" % (base, number + 1) in contextual
    )


def _structural_title_group(value: str) -> str:
    words = normalize_description_key(value).split()
    return words[0] if words else ""


def prepare_structural_code_context(
    rows: Sequence[ExtractedRow],
) -> None:
    """Fija nivel y padre esperados usando hermanos estructurales globales."""
    structural = [
        row
        for row in rows
        if row.tipo_fila in ("grupo", "categoria", "subgrupo")
    ]
    for row in structural:
        token = row.codigo_original.upper().replace(",", ".")
        match = re.fullmatch(r"(\d{1,4})\.8", token)
        if not match:
            continue
        base = match.group(1)
        siblings: Dict[str, ExtractedRow] = {}
        for sibling in structural:
            sibling_code = _row_context_code(sibling)
            sibling_match = re.fullmatch(
                r"%s\.([A-Z])" % re.escape(base),
                sibling_code,
            )
            if sibling_match:
                siblings[sibling_match.group(1)] = sibling
        title_group = _structural_title_group(row.descripcion)
        compatible = [
            sibling
            for sibling in siblings.values()
            if title_group
            and _structural_title_group(sibling.descripcion) == title_group
        ]
        level_values = {
            sibling.nivel_jerarquia
            for sibling in compatible
            if sibling.nivel_jerarquia is not None
        }
        parent_values = {
            sibling.codigo_padre
            for sibling in compatible
            if sibling.codigo_padre
        }
        if len(level_values) == 1 and len(parent_values) == 1:
            level_index = int(next(iter(level_values)))
            if 0 <= level_index < len(HIERARCHY_LEVELS):
                row.nivel_forzado_v6 = HIERARCHY_LEVELS[level_index]
                row.padre_esperado_id = next(iter(parent_values))
        if not row.nivel_forzado_v6:
            chapter = next(
                (
                    item
                    for item in structural
                    if _row_context_code(item) == base
                ),
                None,
            )
            if chapter is not None:
                row.nivel_forzado_v6 = "subcapitulo"
                row.padre_esperado_id = base
        if not row.nivel_forzado_v6 or not row.padre_esperado_id:
            continue
        row.add_rule(
            "Nivel y padre estructurales inferidos desde contexto global"
        )


def _structural_sibling_evidence(
    candidate: str,
    row: ExtractedRow,
    context_rows: Sequence[ExtractedRow],
) -> List[str]:
    if row.tipo_fila == "partida":
        return []
    original = row.codigo_original.upper().replace(",", ".")
    source = re.fullmatch(r"(\d{1,4})\.8", original)
    target = re.fullmatch(r"(\d{1,4})\.B", candidate.upper())
    if (
        source is None
        or target is None
        or source.group(1) != target.group(1)
        or not row.nivel_forzado_v6
        or not row.padre_esperado_id
    ):
        return []
    base = source.group(1)
    sibling_codes = {
        _row_context_code(item)
        for item in context_rows
        if item.tipo_fila in ("grupo", "categoria", "subgrupo")
        and item.codigo_padre == row.padre_esperado_id
        and item.nivel_jerarquia == HIERARCHY_LEVELS.index(
            row.nivel_forzado_v6
        )
        and _structural_title_group(item.descripcion)
        == _structural_title_group(row.descripcion)
    }
    if "%s.A" % base not in sibling_codes or "%s.C" % base not in sibling_codes:
        return []
    evidence = [
        "hermanos estructurales A y C",
        "mismo nivel visual que los hermanos",
        "padre estructural común",
        "título compatible con el grupo",
        "secuencia estructural A-B-C",
    ]
    if "%s.D" % base in sibling_codes:
        evidence.append("hermano estructural D confirma la serie")
    return evidence


def _candidate_evidence(
    candidate: str,
    row: ExtractedRow,
    catalog: DocumentCodeCatalog,
    previous_code: str,
    next_code: str,
    context_rows: Sequence[ExtractedRow],
) -> Tuple[List[str], int]:
    original = row.codigo_original.upper().replace(",", ".").strip("[]| ")
    candidate_upper = candidate.upper()
    evidence: List[str] = []
    score = _code_quality(candidate_upper)
    original_prefix = _numeric_code_prefix(original)
    candidate_prefix = _numeric_code_prefix(candidate_upper)
    if original_prefix is not None and original_prefix == candidate_prefix:
        evidence.append("prefijo numérico conservado")
        score += 3
    if code_family_compatible(original, candidate_upper):
        evidence.append("misma familia")
        score += 4
    else:
        score -= 40
    if not code_role_compatible(candidate_upper, row, catalog):
        score -= 40

    key = normalize_description_key(row.descripcion)
    canonical_codes = catalog.high_confidence_by_description.get(key, [])
    if candidate_upper in canonical_codes:
        evidence.append("descripción repetida en catálogo canónico documental")
        score += 16

    contextual_codes = {
        _row_context_code(item)
        for item in context_rows
        if item is not row and _same_context(row, item)
    }
    letter_match = re.fullmatch(r"(\d{1,4})\.([A-Z])(\d*)", candidate_upper)
    if letter_match:
        base, letter, tail = letter_match.groups()
        previous_letter = chr(ord(letter) - 1) if letter > "A" else ""
        next_letter = chr(ord(letter) + 1) if letter < "Z" else ""
        if tail:
            damaged_cluster = {
                "%s.8%s" % (base, number) for number in (1, 2, 3)
            }
            if (
                letter == "B"
                and damaged_cluster.issubset(
                    {
                        item.codigo_original.upper().replace(",", ".")
                        for item in context_rows
                    }
                )
            ):
                evidence.append("patrón conjunto B1/B2/B3")
                score += 14
        elif (
            previous_letter
            and "%s.%s" % (base, previous_letter) in contextual_codes
            and next_letter
            and "%s.%s" % (base, next_letter) in contextual_codes
        ):
            evidence.append("hermanos anterior y posterior confirman secuencia")
            score += 14
        elif (
            letter == "C"
            and "%s.A" % base in contextual_codes
            and "%s.B" % base in contextual_codes
        ):
            evidence.append("hermanos A y B completan secuencia con C")
            score += 14

    if previous_code and next_code:
        previous = previous_code.upper().replace(",", ".")
        following = next_code.upper().replace(",", ".")
        if candidate_upper not in (previous, following):
            candidate_family = _code_family(candidate_upper)
            if (
                candidate_family
                and candidate_family
                in (_code_family(previous), _code_family(following))
            ):
                evidence.append("vecinos inmediatos compatibles")
                score += 5

    if row.tipo_fila != "partida" and row.codigo_padre:
        parent_code = row.codigo_padre.split("|")[-1]
        if _code_family(parent_code) == _code_family(candidate_upper):
            evidence.append("padre activo compatible con la familia")
            score += 6
    structural_evidence = _structural_sibling_evidence(
        candidate_upper,
        row,
        context_rows,
    )
    if structural_evidence:
        evidence.extend(structural_evidence)
        score += 30
    return list(dict.fromkeys(evidence)), score


def score_code_candidate(
    candidate: str,
    row: ExtractedRow,
    catalog: DocumentCodeCatalog,
    previous_code: str = "",
    next_code: str = "",
    context_rows: Sequence[ExtractedRow] = (),
) -> int:
    return _candidate_evidence(
        candidate,
        row,
        catalog,
        previous_code,
        next_code,
        context_rows,
    )[1]


def audit_document_codes(
    rows: Sequence[ExtractedRow],
    catalog: Optional[DocumentCodeCatalog] = None,
) -> List[CodeAuditRecord]:
    """Audita cada sospecha con vecinos, padre, candidatos y evidencia."""
    evidence_catalog = catalog or build_document_code_catalog(rows)
    structural = [
        row
        for row in rows
        if row.tipo_fila in ("partida", "grupo", "categoria", "subgrupo")
    ]
    records: List[CodeAuditRecord] = []
    for index, row in enumerate(structural):
        reasons = code_suspicion_reasons(
            row.codigo_original,
            row.descripcion,
            evidence_catalog,
        )
        if row.codigo_pendiente and "codigo_pendiente" not in reasons:
            reasons.append("codigo_pendiente")
        if not reasons:
            continue
        previous_code = _row_context_code(structural[index - 1]) if index else ""
        next_code = (
            _row_context_code(structural[index + 1])
            if index + 1 < len(structural)
            else ""
        )
        candidates = [
            candidate
            for candidate in generate_code_candidates(
                row.codigo_original,
                row.descripcion,
                evidence_catalog,
            )
            if code_family_compatible(row.codigo_original, candidate)
            and code_role_compatible(candidate, row, evidence_catalog)
        ]
        scored: List[Tuple[int, str, List[str]]] = []
        for candidate in candidates:
            candidate_evidence, score = _candidate_evidence(
                candidate,
                row,
                evidence_catalog,
                previous_code,
                next_code,
                structural,
            )
            scored.append((score, candidate, candidate_evidence))
        scored.sort(reverse=True)
        best_evidence = scored[0][2] if scored else []
        confidence = row.confianza
        if confidence == "SIN_CAMBIO":
            confidence = "BAJA"
        records.append(
            CodeAuditRecord(
                page=row.pagina,
                row_type=row.tipo_fila,
                description=row.descripcion,
                ocr_code=row.codigo_original,
                current_code=row.item,
                candidates=[item[1] for item in scored],
                active_parent=row.codigo_padre,
                previous_code=previous_code,
                next_code=next_code,
                evidence=best_evidence,
                confidence=confidence,
                reason="; ".join(reasons),
            )
        )
    return records


def audit_final_document_codes(
    rows: Sequence[ExtractedRow],
) -> List[CodeAuditRecord]:
    """Detecta cualquier sospecha residual después de la pasada final."""
    structural = [
        row
        for row in rows
        if row.tipo_fila in ("partida", "grupo", "categoria", "subgrupo")
    ]
    records: List[CodeAuditRecord] = []
    for index, row in enumerate(structural):
        final_code = row.item
        reasons: List[str] = []
        if row.codigo_pendiente or not final_code:
            reasons.append("codigo_pendiente_sin_validar")
        else:
            reasons.extend(code_suspicion_reasons(final_code))
        if (
            row.tipo_fila != "partida"
            and final_code
            and row.codigo_padre
        ):
            parent_code = row.codigo_padre.split("|")[-1]
            parent_family = _code_family(parent_code)
            final_family = _code_family(final_code)
            if (
                parent_family
                and final_family
                and parent_family != final_family
                and not (
                    parent_family == "1000"
                    and final_family.startswith("100")
                )
            ):
                reasons.append("familia_incompatible_con_padre")
        if not reasons:
            continue
        records.append(
            CodeAuditRecord(
                page=row.pagina,
                row_type=row.tipo_fila,
                description=row.descripcion,
                ocr_code=row.codigo_original,
                current_code=final_code,
                active_parent=row.codigo_padre,
                previous_code=(
                    structural[index - 1].item if index else ""
                ),
                next_code=(
                    structural[index + 1].item
                    if index + 1 < len(structural)
                    else ""
                ),
                confidence=row.confianza,
                reason="; ".join(reasons),
            )
        )
    return records


def _code_confusion_type(reasons: Sequence[str]) -> str:
    mapping = (
        ("posible_confusion_8_B", "8/B"),
        ("posible_confusion_0_C", "0/C"),
        ("posible_confusion_4_A", "4/A"),
        ("codigo_incompleto", "código incompleto"),
        ("separador_esperado_ausente", "separador ausente"),
        ("descripcion_asociada", "catálogo código-descripción"),
    )
    values = [
        label
        for prefix, label in mapping
        if any(reason.startswith(prefix) for reason in reasons)
    ]
    return ", ".join(values)


def finalize_document_codes(
    rows: Sequence[ExtractedRow],
    catalog: Optional[DocumentCodeCatalog] = None,
    target_role: Optional[str] = None,
) -> List[CorrectionRecord]:
    """Pasada documental final: solo expone códigos validados como finales."""
    evidence_catalog = catalog or build_document_code_catalog(rows)
    structural = [
        row
        for row in rows
        if row.tipo_fila in ("partida", "grupo", "categoria", "subgrupo")
    ]
    corrections: List[CorrectionRecord] = []
    for index, row in enumerate(structural):
        if target_role is not None and _row_role(row) != target_role:
            continue
        original = row.codigo_original.strip("[]| ")
        if not original:
            continue
        reasons = code_suspicion_reasons(
            original,
            row.descripcion,
            evidence_catalog,
        )
        current = (
            row.codigo_normalizado or original
        ).upper().replace(",", ".")
        previous_code = _row_context_code(structural[index - 1]) if index else ""
        next_code = (
            _row_context_code(structural[index + 1])
            if index + 1 < len(structural)
            else ""
        )

        if reasons and _numeric_sequence_confirms_original(row, structural):
            row.codigo_normalizado = current
            row.codigo_pendiente = False
            row.confianza = "ALTA"
            row.metodo_correccion = "Sufijo numérico confirmado por hermanos"
            row.add_rule(row.metodo_correccion)
            corrections.append(
                CorrectionRecord(
                    tipo="Código OCR validado",
                    pagina=row.pagina,
                    referencia=current,
                    descripcion=row.descripcion,
                    campo="item" if row.tipo_fila == "partida" else "código",
                    original=original,
                    corrected=current,
                    method=row.metodo_correccion,
                    confidence="ALTA",
                    confusion_type=_code_confusion_type(reasons),
                    evidence="hermanos numéricos anterior y posterior",
                    score=20,
                    margin=20,
                    applied=current,
                    reason="El valor numérico OCR es coherente y no se sustituyó",
                )
            )
            continue

        if not reasons:
            # Mantiene las normalizaciones inequívocas ya realizadas, como
            # una coma interna delante de una letra.
            if current != original and is_item_code(current):
                row.codigo_normalizado = current
                row.codigo_pendiente = False
                row.confianza = "ALTA"
                corrections.append(
                    CorrectionRecord(
                        tipo="Código de partida"
                        if row.tipo_fila == "partida"
                        else "Estructura",
                        pagina=row.pagina,
                        referencia=current,
                        descripcion=row.descripcion,
                        campo="item"
                        if row.tipo_fila == "partida"
                        else "código",
                        original=original,
                        corrected=current,
                        method="Separador OCR normalizado inequívocamente",
                        confidence="ALTA",
                        confusion_type="separador",
                        evidence="patrón de código válido",
                        score=20,
                        margin=20,
                        applied=current,
                    )
                )
            continue

        candidates = [
            candidate.upper()
            for candidate in generate_code_candidates(
                original,
                row.descripcion,
                evidence_catalog,
            )
            if is_item_code(candidate)
            and code_family_compatible(original, candidate)
            and code_role_compatible(candidate, row, evidence_catalog)
        ]
        candidates = list(dict.fromkeys(candidates))
        scored: List[Tuple[int, str, List[str]]] = []
        for candidate in candidates:
            candidate_evidence, score = _candidate_evidence(
                candidate,
                row,
                evidence_catalog,
                previous_code,
                next_code,
                structural,
            )
            scored.append((score, candidate, candidate_evidence))
        scored.sort(reverse=True)
        best_score, best, best_evidence = (
            scored[0] if scored else (0, "", [])
        )
        second_score = scored[1][0] if len(scored) > 1 else 0
        margin = best_score - second_score
        contextual = [
            item
            for item in best_evidence
            if item not in ("prefijo numérico conservado", "misma familia")
        ]
        canonical_unique = (
            bool(best)
            and normalize_description_key(row.descripcion)
            in evidence_catalog.high_confidence_by_description
            and evidence_catalog.high_confidence_by_description[
                normalize_description_key(row.descripcion)
            ]
            == [best]
        )
        high = bool(
            best
            and margin >= CODE_HIGH_CONFIDENCE_MARGIN
            and (
                (
                    "prefijo numérico conservado" in best_evidence
                    and "misma familia" in best_evidence
                    and contextual
                )
                or (
                    not _code_family(original)
                    and canonical_unique
                    and "descripción repetida en catálogo canónico documental"
                    in best_evidence
                )
            )
        )
        structural_b = (
            row.tipo_fila != "partida"
            and re.fullmatch(
                r"\d{1,4}\.8",
                original.upper().replace(",", "."),
            )
            and best.endswith(".B")
        )
        if structural_b and (
            "hermanos estructurales A y C" not in best_evidence
        ):
            high = False
        if high:
            row.codigo_normalizado = best
            row.codigo_pendiente = False
            row.metodo_correccion = (
                "normalización documental final: "
                + " + ".join(contextual)
            )
            row.confianza = "ALTA"
            row.add_rule(row.metodo_correccion)
            row.motivo_revision = re.sub(
                r"(?:^|; )(?:Ambigüedad|Código propuesto)[^;]*",
                "",
                row.motivo_revision,
            ).strip("; ")
            if not row.motivo_revision:
                row.estado_revision = "OK"
            applied = best
            record_type = (
                "Código de partida"
                if row.tipo_fila == "partida"
                else "Estructura"
            )
            reason = "Candidato único con evidencia documental suficiente"
        else:
            row.codigo_normalizado = ""
            row.codigo_pendiente = True
            row.confianza = "MEDIA" if best_score >= 8 and best else "BAJA"
            alternatives = ", ".join(item[1] for item in scored[:5])
            row.add_review(
                "Código OCR no validado; candidatos: %s"
                % (alternatives or "sin candidato confiable")
            )
            row.metodo_correccion = "pendiente de revisión documental"
            applied = ""
            record_type = "Código propuesto" if best else "Código pendiente"
            reason = (
                "Evidencia insuficiente o margen menor al requerido; "
                "el OCR sospechoso no se presenta como código final"
            )
        corrections.append(
            CorrectionRecord(
                tipo=record_type,
                pagina=row.pagina,
                referencia=applied,
                descripcion=row.descripcion,
                campo="item" if row.tipo_fila == "partida" else "código",
                original=original,
                corrected=best,
                method=row.metodo_correccion,
                confidence=row.confianza,
                confusion_type=_code_confusion_type(reasons),
                evidence="; ".join(best_evidence),
                score=best_score,
                margin=margin,
                applied=applied,
                reason=reason,
            )
        )
        logging.getLogger("presupuestos").info(
            "FINALIZACION_CODIGO pagina=%s original=%r propuesto=%r "
            "aplicado=%r confianza=%s puntuacion=%s margen=%s evidencias=%s "
            "motivo=%s",
            row.pagina,
            original,
            best,
            applied,
            row.confianza,
            best_score,
            margin,
            "; ".join(best_evidence),
            reason,
        )
    return corrections


def finalize_structural_codes(
    rows: Sequence[ExtractedRow],
    catalog: Optional[DocumentCodeCatalog] = None,
) -> List[CorrectionRecord]:
    prepare_structural_code_context(rows)
    return finalize_document_codes(rows, catalog, "estructura")


def finalize_partida_codes(
    rows: Sequence[ExtractedRow],
    catalog: Optional[DocumentCodeCatalog] = None,
) -> List[CorrectionRecord]:
    return finalize_document_codes(rows, catalog, "partida")


def make_code_review_id(source_name: str, row: ExtractedRow) -> str:
    return "%s|pagina%s|orden%s|%s" % (
        source_name,
        row.pagina,
        row.orden_documento,
        row.tipo_fila,
    )


def rank_code_candidates(
    row: ExtractedRow,
    rows: Sequence[ExtractedRow],
    catalog: DocumentCodeCatalog,
    limit: int = 2,
) -> List[Tuple[str, int, List[str]]]:
    structural = [
        item
        for item in rows
        if item.tipo_fila in ("partida", "grupo", "categoria", "subgrupo")
    ]
    try:
        index = structural.index(row)
    except ValueError:
        return []
    previous_code = _row_context_code(structural[index - 1]) if index else ""
    next_code = (
        _row_context_code(structural[index + 1])
        if index + 1 < len(structural)
        else ""
    )
    candidates = [
        candidate.upper()
        for candidate in generate_code_candidates(
            row.codigo_original,
            row.descripcion,
            catalog,
        )
        if is_item_code(candidate)
        and code_family_compatible(row.codigo_original, candidate)
        and code_role_compatible(candidate, row, catalog)
    ]
    ranked: List[Tuple[str, int, List[str]]] = []
    for candidate in dict.fromkeys(candidates):
        evidence, score = _candidate_evidence(
            candidate,
            row,
            catalog,
            previous_code,
            next_code,
            structural,
        )
        ranked.append((candidate, score, evidence))
    ranked.sort(key=lambda item: (item[1], item[0]), reverse=True)
    return ranked[:limit]


def build_code_review_records(
    source_name: str,
    rows: Sequence[ExtractedRow],
    catalog: Optional[DocumentCodeCatalog] = None,
) -> List[CodeReviewRecord]:
    evidence_catalog = catalog or build_document_code_catalog(rows)
    structural = [
        row
        for row in rows
        if row.tipo_fila in ("partida", "grupo", "categoria", "subgrupo")
    ]
    records: List[CodeReviewRecord] = []
    for index, row in enumerate(structural):
        if not row.codigo_pendiente:
            continue
        ranked = rank_code_candidates(row, rows, evidence_catalog, 2)
        first = ranked[0] if ranked else ("", 0, [])
        second = ranked[1] if len(ranked) > 1 else ("", 0, [])
        evidence = list(first[2])
        parent_or_path = row.ruta_jerarquica or row.codigo_padre
        records.append(
            CodeReviewRecord(
                review_id=make_code_review_id(source_name, row),
                page=row.pagina,
                order=row.orden_documento,
                row_type=row.tipo_fila,
                description=row.descripcion,
                item_ocr=row.codigo_original,
                candidate_1=first[0],
                candidate_1_score=first[1],
                candidate_2=second[0],
                candidate_2_score=second[1],
                evidence="; ".join(evidence),
                parent_or_path=parent_or_path,
                previous_code=(
                    structural[index - 1].item if index else ""
                ),
                next_code=(
                    structural[index + 1].item
                    if index + 1 < len(structural)
                    else ""
                ),
                automatic_confidence=row.confianza,
            )
        )
    return records


def _code_review_row(record: CodeReviewRecord) -> List[object]:
    return [
        record.review_id,
        record.page,
        record.order,
        record.row_type,
        record.description,
        record.item_ocr,
        record.candidate_1,
        record.candidate_1_score,
        record.candidate_2,
        record.candidate_2_score,
        record.evidence,
        record.parent_or_path,
        record.previous_code,
        record.next_code,
        record.automatic_confidence,
        record.approved_code,
        record.review_status,
        record.reviewer_comment,
    ]


def apply_approved_code_reviews(
    review_path: Path,
    source_name: str,
    rows: Sequence[ExtractedRow],
) -> List[CorrectionRecord]:
    try:
        from openpyxl import load_workbook  # type: ignore
    except ImportError as exc:
        raise RuntimeError("openpyxl no está disponible") from exc
    workbook = load_workbook(str(review_path), read_only=True, data_only=True)
    if "Revision_codigos" not in workbook.sheetnames:
        workbook.close()
        raise ValueError("El archivo no contiene la hoja Revision_codigos")
    sheet = workbook["Revision_codigos"]
    headers = [cell.value for cell in sheet[1]]
    missing = [
        column for column in CODE_REVIEW_COLUMNS if column not in headers
    ]
    if missing:
        workbook.close()
        raise ValueError(
            "Faltan columnas de revisión: %s" % ", ".join(missing)
        )
    indexes = {column: headers.index(column) for column in CODE_REVIEW_COLUMNS}
    by_id = {
        make_code_review_id(source_name, row): row
        for row in rows
        if row.tipo_fila in ("partida", "grupo", "categoria", "subgrupo")
    }
    corrections: List[CorrectionRecord] = []
    for values in sheet.iter_rows(min_row=2, values_only=True):
        status = str(values[indexes["Estado revisión"]] or "").upper()
        if status not in ("PENDIENTE", "APROBADO", "RECHAZADO"):
            workbook.close()
            raise ValueError("Estado revisión no válido: %s" % status)
        if status != "APROBADO":
            continue
        review_id = str(values[indexes["ID revisión"]] or "")
        row = by_id.get(review_id)
        if row is None:
            workbook.close()
            raise ValueError(
                "La revisión no corresponde al documento: %s" % review_id
            )
        expected = (
            int(values[indexes["Página PDF"]] or 0) == row.pagina
            and int(values[indexes["Orden"]] or 0) == row.orden_documento
            and str(values[indexes["Tipo fila"]] or "") == row.tipo_fila
            and normalize_description_key(
                str(values[indexes["Descripción"]] or "")
            )
            == normalize_description_key(row.descripcion)
            and str(values[indexes["Item OCR"]] or "")
            == row.codigo_original
        )
        if not expected:
            workbook.close()
            raise ValueError(
                "Documento, página, descripción o Item OCR no coincide: %s"
                % review_id
            )
        approved = str(values[indexes["Código aprobado"]] or "").strip()
        if not is_item_code(approved) or code_suspicion_reasons(approved):
            workbook.close()
            raise ValueError(
                "Código aprobado no válido para %s: %s"
                % (review_id, approved)
            )
        row.codigo_normalizado = approved
        row.codigo_pendiente = False
        row.confianza = "ALTA"
        row.metodo_correccion = "revisión humana aprobada"
        row.add_rule(
            "Revisión humana aprobada ID %s" % review_id
        )
        row.motivo_revision = re.sub(
            r"(?:^|; )Código OCR no validado[^;]*",
            "",
            row.motivo_revision,
        ).strip("; ")
        if not row.motivo_revision:
            row.estado_revision = "OK"
        corrections.append(
            CorrectionRecord(
                tipo="Revisión humana",
                pagina=row.pagina,
                referencia=review_id,
                descripcion=row.descripcion,
                campo="item" if row.tipo_fila == "partida" else "código",
                original=row.codigo_original,
                corrected=approved,
                method="revisión humana aprobada",
                confidence="ALTA",
                applied=approved,
                reason="Código aprobado por revisor; ID %s" % review_id,
            )
        )
    workbook.close()
    return corrections


def apply_code_corrections(
    rows: Sequence[ExtractedRow],
    catalog: Optional[DocumentCodeCatalog] = None,
) -> List[CorrectionRecord]:
    return finalize_document_codes(rows, catalog)


def normalize_unit(raw: str) -> UnitResult:
    original = raw.strip()
    if not original:
        return UnitResult(original=original, normalized="")
    lower = original.lower()
    normalized = UNIT_ALIASES.get(lower, lower)
    if normalized in VALID_UNITS:
        rule = ""
        incidents: List[str] = []
        if normalized != original:
            rule = "Unidad normalizada: %s → %s" % (original, normalized)
            incidents.append("unidad_normalizada")
        if normalized == "gb":
            incidents.append("posible_confusion_gb_glb")
        return UnitResult(
            original=original,
            normalized=normalized,
            rule=rule,
            incident_types=incidents,
        )
    return UnitResult(
        original=original,
        normalized="",
        reassigned_text=original,
        rule="Fragmento de unidad reasignado a descripción",
        review_reason="Unidad OCR no reconocida: %s" % original,
    )


def _unit_tokens_are_close(words: Sequence[Word], maximum_gap: float = 3.0) -> bool:
    ordered = sorted(words, key=lambda item: item.x0)
    return all(
        ordered[index + 1].x0 - ordered[index].x1 <= maximum_gap
        for index in range(len(ordered) - 1)
    )


def split_unit_tokens(
    words: Sequence[Word],
    allow_unknown_candidate: bool = False,
) -> UnitResult:
    if not words:
        return UnitResult(original="", normalized="")
    ordered = sorted(words, key=lambda item: item.x0)
    original = " ".join(word.text for word in ordered)
    valid_index: Optional[int] = None
    valid_result: Optional[UnitResult] = None
    reconstructed = False

    # Primero se prueban sufijos contiguos de varios tokens. La combinación
    # debe existir en el catálogo; nunca se crean unidades por concatenación
    # libre. En particular, "m." + "pto" no forma "m.pto".
    for index in range(0, len(ordered) - 1):
        candidate_words = ordered[index:]
        if not _unit_tokens_are_close(candidate_words):
            continue
        candidate = "".join(word.text for word in candidate_words)
        if candidate.lower() == "m.pto":
            continue
        result = normalize_unit(candidate)
        if result.normalized:
            valid_index = index
            valid_result = result
            reconstructed = True
            break

    if valid_result is None:
        for index in range(len(ordered) - 1, -1, -1):
            result = normalize_unit(ordered[index].text)
            if result.normalized:
                valid_index = index
                valid_result = result
                break

    if valid_index is None or valid_result is None:
        if allow_unknown_candidate and len(ordered) == 1:
            token = ordered[0].text.strip()
            if (
                token
                and len(token) <= 8
                and not re.fullmatch(r"[+\-]?\d[\d.,]*", token)
            ):
                return UnitResult(
                    original=original,
                    normalized=token,
                    rule="Unidad provisional conservada por geometría de columna",
                    review_reason="Unidad no catalogada: %s" % token,
                    incident_types=["unidad_no_catalogada"],
                )
        return UnitResult(
            original=original,
            normalized="",
            reassigned_text=original,
            rule="Fragmento de unidad reasignado a descripción",
            review_reason="No se detectó una unidad válida en la banda",
        )

    first_unit_index = valid_index
    if reconstructed:
        valid_result.rule = _append_message(
            valid_result.rule,
            "Unidad reconstruida desde varios tokens de la misma línea",
        )
        valid_result.incident_types.append(
            "unidad_reconstruida_desde_varios_tokens"
        )
    reassigned = " ".join(
        word.text
        for index, word in enumerate(ordered)
        if index < first_unit_index
    )
    rule = valid_result.rule
    if reassigned:
        rule = _append_message(
            rule, "Texto ajeno a unidad reasignado a descripción"
        )
    return UnitResult(
        original=original,
        normalized=valid_result.normalized,
        reassigned_text=reassigned,
        rule=rule,
        review_reason=valid_result.review_reason,
        incident_types=list(dict.fromkeys(valid_result.incident_types)),
    )


def unit_geometry_is_clear(word: Word, page_bands: PageBands) -> bool:
    unit_band = Band("unit", page_bands.unit_start, page_bands.metrado_start)
    description_band = Band(
        "description", page_bands.description_start, page_bands.unit_start
    )
    inside_or_overlapping = (
        unit_band.start <= word.center_x < unit_band.end
        or overlap_ratio(word, unit_band) >= 0.5
    )
    if not inside_or_overlapping:
        return False
    if not (page_bands.description_start < word.center_x < page_bands.metrado_start):
        return False
    if len(word.text.strip()) > 8:
        return False
    if re.fullmatch(r"[+\-]?\d[\d.,]*", word.text.strip()):
        return False
    unit_center = (unit_band.start + unit_band.end) / 2.0
    description_center = (description_band.start + description_band.end) / 2.0
    return abs(word.center_x - unit_center) < abs(
        word.center_x - description_center
    )


def recover_unit_words_from_description(
    assigned: Dict[str, List[Word]],
    page_bands: PageBands,
    has_numeric_values: bool,
) -> List[Word]:
    """Mueve solo un sufijo cuya geometría original pertenece a unidad."""
    if not has_numeric_values or not assigned["description"]:
        return []
    ordered = sorted(assigned["description"], key=lambda item: item.x0)
    recovered: List[Word] = []
    for candidate in reversed(ordered):
        if not unit_geometry_is_clear(candidate, page_bands):
            break
        recovered.insert(0, candidate)
    if not recovered or len(recovered) == len(ordered):
        return []
    tentative = split_unit_tokens(
        recovered,
        allow_unknown_candidate=len(recovered) == 1,
    )
    if not tentative.normalized:
        return []
    recovered_ids = {id(word) for word in recovered}
    assigned["description"] = [
        word for word in assigned["description"] if id(word) not in recovered_ids
    ]
    assigned["unit"].extend(recovered)
    assigned["unit"].sort(key=lambda item: item.x0)
    return recovered


def monetary_tolerance(expected: Decimal, percentage: Decimal) -> Decimal:
    return max(Decimal("0.10"), abs(expected) * percentage / Decimal("100"))


def within_tolerance(
    actual: Decimal, expected: Decimal, percentage: Decimal
) -> bool:
    return abs(actual - expected) <= monetary_tolerance(expected, percentage)


def recover_lost_decimal(
    raw: str,
    price: Optional[Decimal],
    partial: Optional[Decimal],
    neighbor_decimal_places: Sequence[int],
    allow_three_decimals: bool = False,
) -> DecimalRecovery:
    parsed = parse_ocr_number(raw)
    if parsed.value is None:
        return DecimalRecovery(
            value=None, review_reason=parsed.rejection or "Metrado OCR inválido"
        )
    value = parsed.value
    token = _strip_numeric_wrapper(raw)
    if not re.fullmatch(r"\d+", token):
        return DecimalRecovery(value=value, rule=parsed.rule)

    candidates = [value, value / Decimal("10"), value / Decimal("100")]
    if allow_three_decimals:
        candidates.append(value / Decimal("1000"))

    if price is None or partial is None:
        return DecimalRecovery(
            value=value,
            review_reason="Decimal perdido ambiguo sin precio y parcial",
            candidates=candidates,
        )

    coherent = [
        candidate
        for candidate in candidates
        if within_tolerance(candidate * price, partial, Decimal("1"))
    ]
    if value in coherent:
        return DecimalRecovery(value=value, candidates=coherent)
    if len(coherent) != 1:
        return DecimalRecovery(
            value=value,
            review_reason="Candidatos decimales ambiguos: %s"
            % ", ".join(str(candidate) for candidate in coherent or candidates),
            candidates=coherent or candidates,
        )

    candidate = coherent[0]
    places = max(0, -candidate.as_tuple().exponent)
    common_places = set(neighbor_decimal_places)
    if common_places and places not in common_places:
        return DecimalRecovery(
            value=value,
            review_reason=(
                "El candidato %s contradice el formato decimal de filas vecinas"
                % candidate
            ),
            candidates=coherent,
        )
    return DecimalRecovery(
        value=candidate,
        rule="Decimal recuperado mediante metrado × precio = parcial",
        candidates=coherent,
    )


def recover_document_decimals(rows: Sequence[ExtractedRow]) -> None:
    """Recupera metrados enteros usando formato vecino y ecuación de partida."""
    decimal_places_by_page: Dict[int, List[int]] = {}
    for row in rows:
        if row.tipo_fila != "partida" or row.metrado is None:
            continue
        token = _strip_numeric_wrapper(row.metrado_ocr)
        if not token or re.fullmatch(r"\d+", token):
            continue
        places = max(0, -row.metrado.as_tuple().exponent)
        decimal_places_by_page.setdefault(row.pagina, []).append(places)

    for row in rows:
        if (
            row.tipo_fila != "partida"
            or row.metrado is None
            or not re.fullmatch(r"\d+", _strip_numeric_wrapper(row.metrado_ocr))
        ):
            continue
        neighbor_places = decimal_places_by_page.get(row.pagina, [])
        common_places = sorted(set(neighbor_places))
        allow_three = 3 in common_places
        recovery = recover_lost_decimal(
            row.metrado_ocr,
            row.precio_soles,
            row.parcial_soles,
            common_places,
            allow_three,
        )
        if recovery.rule and recovery.value is not None:
            original_value = row.metrado
            row.metrado = recovery.value
            row.add_rule(recovery.rule)
            default_audit_logger(
                row.metrado_ocr,
                str(recovery.value),
                row.pagina,
                recovery.rule,
                "metrado",
            )
            logging.getLogger("presupuestos").info(
                "RECUPERACION_DECIMAL pagina=%s codigo=%r original=%r "
                "valor_anterior=%s normalizado=%s regla=%s",
                row.pagina,
                row.codigo_original,
                row.metrado_ocr,
                original_value,
                recovery.value,
                recovery.rule,
            )
        elif recovery.review_reason:
            row.add_review(recovery.review_reason)


def _decimal_2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _digit_signature(value: object) -> str:
    return re.sub(r"\D", "", "" if value is None else str(value))


def _digit_edit_distance(first: str, second: str) -> int:
    if first == second:
        return 0
    if not first:
        return len(second)
    if not second:
        return len(first)
    previous = list(range(len(second) + 1))
    for index, left in enumerate(first, 1):
        current = [index]
        for other_index, right in enumerate(second, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[other_index] + 1,
                    previous[other_index - 1] + (left != right),
                )
            )
        previous = current
    return previous[-1]


def document_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _review_decimal(value: object, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(
            "Valor decimal inválido en revisión numérica: %s" % field_name
        )
    if not result.is_finite():
        raise ValueError(
            "Valor decimal no finito en revisión numérica: %s" % field_name
        )
    return result


def load_numeric_review_approvals(
    review_path: Path,
) -> List[NumericReviewApproval]:
    try:
        payload = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(
            "No se pudo leer la revisión numérica: %s" % review_path
        ) from exc
    entries = payload.get("aprobaciones") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ValueError(
            "La revisión numérica debe contener una lista 'aprobaciones'"
        )
    approvals: List[NumericReviewApproval] = []
    required = (
        "id_aprobacion",
        "documento_sha256",
        "archivo_origen",
        "pagina",
        "orden_fila",
        "campo",
        "valor_ocr",
        "valor_aprobado",
        "descripcion_normalizada",
        "referencia_revision_humana",
        "estado",
        "motivo",
    )
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            raise ValueError("Aprobación numérica %s inválida" % index)
        missing = [key for key in required if key not in entry]
        if missing:
            raise ValueError(
                "Aprobación numérica %s incompleta: %s"
                % (index, ", ".join(missing))
            )
        field_name = str(entry["campo"]).strip()
        if field_name not in NUMERIC_REVIEW_FIELDS:
            raise ValueError(
                "Campo numérico no autorizado: %s" % field_name
            )
        approvals.append(
            NumericReviewApproval(
                approval_id=str(entry["id_aprobacion"]).strip(),
                document_sha256=str(entry["documento_sha256"]).lower().strip(),
                source_filename=str(entry["archivo_origen"]).strip(),
                page=int(entry["pagina"]),
                row_order=int(entry["orden_fila"]),
                field_name=field_name,
                ocr_value=_review_decimal(entry["valor_ocr"], "valor_ocr"),
                approved_value=_review_decimal(
                    entry["valor_aprobado"], "valor_aprobado"
                ),
                normalized_description=normalize_description_key(
                    str(entry["descripcion_normalizada"])
                ),
                reviewer_reference=str(
                    entry["referencia_revision_humana"]
                ).strip(),
                status=str(entry["estado"]).upper().strip(),
                reason=str(entry["motivo"]).strip(),
            )
        )
    return approvals


def _numeric_raw_text(row: ExtractedRow, field_name: str) -> str:
    return {
        "metrado": row.metrado_ocr,
        "precio_soles": row.precio_ocr,
        "parcial_soles": row.parcial_ocr,
    }[field_name]


def _mathematical_numeric_candidate(
    row: ExtractedRow, field_name: str
) -> Optional[Decimal]:
    if field_name == "parcial_soles":
        if row.metrado is None or row.precio_soles is None:
            return None
        return _decimal_2(row.metrado * row.precio_soles)
    if field_name == "metrado":
        if (
            row.parcial_soles is None
            or row.precio_soles is None
            or not row.precio_soles
        ):
            return None
        return _decimal_2(row.parcial_soles / row.precio_soles)
    if field_name == "precio_soles":
        if row.parcial_soles is None or row.metrado is None or not row.metrado:
            return None
        return _decimal_2(row.parcial_soles / row.metrado)
    return None


def _single_digit_numeric_confusion(
    original: Decimal, candidate: Decimal
) -> bool:
    original_digits = _digit_signature(format(original, "f"))
    candidate_digits = _digit_signature(format(candidate, "f"))
    return (
        len(original_digits) == len(candidate_digits)
        and _digit_edit_distance(original_digits, candidate_digits) == 1
        and original.as_tuple().exponent == candidate.as_tuple().exponent
    )


def _numeric_operands_are_reliable(
    row: ExtractedRow, field_name: str
) -> bool:
    if field_name != "parcial_soles":
        return _mathematical_numeric_candidate(row, field_name) is not None
    if row.metrado is None or row.precio_soles is None:
        return False
    unresolved = (row.motivo_revision or "").lower()
    return not any(
        marker in unresolved
        for marker in (
            "faltan campos: metrado",
            "faltan campos: precio_soles",
            "decimal perdido ambiguo",
        )
    )


def propose_human_numeric_corrections(
    rows: Sequence[ExtractedRow],
) -> List[CorrectionRecord]:
    proposals: List[CorrectionRecord] = []
    for row in rows:
        if row.tipo_fila != "partida":
            continue
        field_name = "parcial_soles"
        if field_name in row.human_numeric_corrections:
            continue
        raw_result = parse_ocr_number(_numeric_raw_text(row, field_name))
        candidate = _mathematical_numeric_candidate(row, field_name)
        if (
            raw_result.value is None
            or candidate is None
            or raw_result.value == candidate
            or not _numeric_operands_are_reliable(row, field_name)
            or not _single_digit_numeric_confusion(raw_result.value, candidate)
        ):
            continue
        reason = (
            "Posible confusión OCR de un dígito; requiere confirmación "
            "visual humana"
        )
        row.add_review(reason)
        proposals.append(
            CorrectionRecord(
                tipo="Propuesta corrección numérica humana",
                pagina=row.pagina,
                referencia=row.item or row.codigo_original,
                descripcion=row.descripcion,
                campo=field_name,
                original=raw_result.value,
                corrected=candidate,
                method="propuesta por validación matemática",
                confidence="MEDIA",
                confusion_type="un_digito",
                evidence="metrado × precio redondeado produce candidato único",
                applied="",
                reason=reason,
                severity="REQUIERE REVISIÓN",
                action_required="Confirmación visual humana",
            )
        )
    return proposals


def apply_approved_numeric_reviews(
    review_path: Path,
    pdf_path: Path,
    source_filename: str,
    rows: Sequence[ExtractedRow],
) -> List[CorrectionRecord]:
    approvals = load_numeric_review_approvals(review_path)
    actual_hash = document_sha256(pdf_path)
    corrections: List[CorrectionRecord] = []
    seen_ids: Set[str] = set()
    for approval in approvals:
        if approval.status != "APROBADO":
            continue
        if not approval.approval_id or approval.approval_id in seen_ids:
            raise ValueError("ID de aprobación numérica vacío o duplicado")
        seen_ids.add(approval.approval_id)
        if approval.document_sha256 != actual_hash:
            raise ValueError(
                "La aprobación numérica no corresponde al hash del documento"
            )
        if approval.source_filename != source_filename:
            raise ValueError(
                "La aprobación numérica no corresponde al archivo de origen"
            )
        if not approval.reviewer_reference:
            raise ValueError("Falta la referencia de revisión humana")
        matches = [
            row
            for row in rows
            if row.tipo_fila == "partida"
            and row.pagina == approval.page
            and row.orden_pagina == approval.row_order
            and normalize_description_key(row.descripcion)
            == approval.normalized_description
        ]
        if len(matches) != 1:
            raise ValueError(
                "La aprobación numérica no identifica una fila única"
            )
        row = matches[0]
        raw_result = parse_ocr_number(
            _numeric_raw_text(row, approval.field_name)
        )
        if raw_result.value != approval.ocr_value:
            raise ValueError(
                "El valor OCR de la aprobación numérica no coincide"
            )
        current_value = getattr(row, approval.field_name)
        if current_value != approval.ocr_value:
            raise ValueError(
                "El valor actual ya no coincide con el valor OCR aprobado"
            )
        candidate = _mathematical_numeric_candidate(row, approval.field_name)
        if candidate != approval.approved_value:
            raise ValueError(
                "El valor aprobado no coincide con el candidato matemático único"
            )
        if not _numeric_operands_are_reliable(row, approval.field_name):
            raise ValueError("Los operandos de la corrección no son confiables")
        if not _single_digit_numeric_confusion(
            approval.ocr_value, approval.approved_value
        ):
            raise ValueError(
                "La aprobación no corresponde a una confusión de un solo dígito"
            )
        note = approval.reason or (
            "Confusión OCR de un dígito confirmada visual y matemáticamente"
        )
        setattr(row, approval.field_name, approval.approved_value)
        row.human_numeric_corrections[approval.field_name] = (
            AppliedNumericCorrection(
                field_name=approval.field_name,
                original_value=approval.ocr_value,
                corrected_value=approval.approved_value,
                method=HUMAN_NUMERIC_METHOD,
                confidence="ALTA",
                note=note,
                severity=HUMAN_NUMERIC_SEVERITY,
                action_required=HUMAN_NUMERIC_ACTION,
                reviewer_reference=approval.reviewer_reference,
                approval_id=approval.approval_id,
            )
        )
        row.metodo_correccion = _append_message(
            row.metodo_correccion, HUMAN_NUMERIC_METHOD
        )
        row.confianza = "ALTA"
        row.nota = _append_message(row.nota, note)
        refresh_partida_review(row)
        corrections.append(
            CorrectionRecord(
                tipo="Corrección numérica humana",
                pagina=row.pagina,
                referencia=row.item or row.codigo_original,
                descripcion=row.descripcion,
                campo=approval.field_name,
                original=approval.ocr_value,
                corrected=approval.approved_value,
                method=HUMAN_NUMERIC_METHOD,
                confidence="ALTA",
                confusion_type="6/5" if note.lower().find("6/5") >= 0 else "un_digito",
                evidence=(
                    "confirmación visual humana; metrado × precio "
                    "redondeado produce candidato único"
                ),
                applied=approval.approved_value,
                reason=note,
                severity=HUMAN_NUMERIC_SEVERITY,
                action_required=HUMAN_NUMERIC_ACTION,
                reviewer_reference=approval.reviewer_reference,
            )
        )
        logging.getLogger("presupuestos").info(
            "CORRECCION_NUMERICA_HUMANA id=%s documento_sha256=%s pagina=%s "
            "orden_fila=%s campo=%s original=%s corregido=%s revisor=%r",
            approval.approval_id,
            actual_hash,
            approval.page,
            approval.row_order,
            approval.field_name,
            approval.ocr_value,
            approval.approved_value,
            approval.reviewer_reference,
        )
    return corrections


def _numeric_evidence_matches(raw: str, candidate: Decimal) -> Tuple[bool, int]:
    original_digits = _digit_signature(raw)
    candidate_digits = _digit_signature(format(_decimal_2(candidate), "f"))
    if not original_digits:
        return False, 999
    distance = _digit_edit_distance(original_digits, candidate_digits)
    suffix = len(original_digits) >= 2 and candidate_digits.endswith(original_digits)
    return distance <= 1 or suffix, distance if not suffix else 1


def apply_unit_document_corrections(
    rows: Sequence[ExtractedRow],
) -> List[CorrectionRecord]:
    by_description: Dict[str, List[str]] = {}
    for row in rows:
        if row.tipo_fila != "partida" or not row.und:
            continue
        if "unidad_no_catalogada" in row.unit_incident_types:
            continue
        key = normalize_description_key(row.descripcion)
        by_description.setdefault(key, []).append(row.und)

    corrections: List[CorrectionRecord] = []
    for row in rows:
        if row.tipo_fila != "partida":
            continue
        key = normalize_description_key(row.descripcion)
        values = by_description.get(key, [])
        if not values:
            continue
        frequency: Dict[str, int] = {}
        for value in values:
            frequency[value] = frequency.get(value, 0) + 1
        canonical = max(frequency, key=frequency.get)
        needs_document_evidence = (
            not row.und
            or "unidad_no_catalogada" in row.unit_incident_types
        )
        if (
            needs_document_evidence
            and canonical
            and canonical != row.und
            and frequency[canonical] >= 1
        ):
            previous = row.und
            row.und = canonical
            row.metodo_correccion = _append_message(
                row.metodo_correccion,
                "unidad confirmada por descripción repetida en el documento",
            )
            row.confianza = "ALTA"
            row.unit_incident_types = [
                item
                for item in row.unit_incident_types
                if item != "unidad_no_catalogada"
            ]
            corrections.append(
                CorrectionRecord(
                    tipo="Unidad",
                    pagina=row.pagina,
                    referencia=row.item,
                    descripcion=row.descripcion,
                    campo="unidad",
                    original=row.und_ocr,
                    corrected=canonical,
                    method="catálogo de unidades por descripción repetida",
                    confidence="ALTA",
                )
            )
            logging.getLogger("presupuestos").info(
                "CORRECCION_UNIDAD_DOCUMENTAL pagina=%s item=%r ocr=%r "
                "anterior=%r corregida=%r",
                row.pagina,
                row.item,
                row.und_ocr,
                previous,
                canonical,
            )
    return corrections


def apply_numeric_corrections(
    rows: Sequence[ExtractedRow],
) -> List[CorrectionRecord]:
    """Segunda pasada: solo aplica un candidato matemático inequívoco."""
    corrections: List[CorrectionRecord] = []
    prices_by_description: Dict[str, List[Decimal]] = {}
    for row in rows:
        if row.tipo_fila == "partida" and row.precio_soles is not None:
            prices_by_description.setdefault(
                normalize_description_key(row.descripcion), []
            ).append(row.precio_soles)

    for row in rows:
        if row.tipo_fila != "partida":
            continue
        changes: List[Tuple[str, Optional[Decimal], Decimal, str, int]] = []
        metrado = row.metrado
        price = row.precio_soles
        partial = row.parcial_soles

        if metrado is None and price is not None and partial is not None and price:
            candidate = _decimal_2(partial / price)
            if within_tolerance(candidate * price, partial, Decimal("0.01")):
                evidence, distance = _numeric_evidence_matches(
                    row.metrado_ocr, candidate
                )
                if evidence or not row.metrado_ocr.strip():
                    changes.append(
                        (
                            "metrado",
                            metrado,
                            candidate,
                            (
                                "ecuación parcial ÷ precio y evidencia OCR"
                                if evidence
                                else "metrado recuperado como único campo faltante"
                            ),
                            distance,
                        )
                    )
        if price is None and metrado is not None and partial is not None and metrado:
            key = normalize_description_key(row.descripcion)
            repeated = prices_by_description.get(key, [])
            if repeated and all(value == repeated[0] for value in repeated):
                candidate = repeated[0]
                if within_tolerance(
                    metrado * candidate, partial, Decimal("1")
                ):
                    changes.append(
                        (
                            "precio_soles",
                            price,
                            candidate,
                            "precio repetido para la misma descripción",
                            0,
                        )
                    )
            elif within_tolerance(
                metrado * _decimal_2(partial / metrado),
                partial,
                Decimal("0.01"),
            ):
                changes.append(
                    (
                        "precio_soles",
                        price,
                        _decimal_2(partial / metrado),
                        "precio recuperado como único campo faltante",
                        0,
                    )
                )
        if partial is None and metrado is not None and price is not None:
            candidate = _decimal_2(metrado * price)
            evidence, distance = _numeric_evidence_matches(
                row.parcial_ocr, candidate
            )
            if evidence or not row.parcial_ocr.strip():
                changes.append(
                    (
                        "parcial_soles",
                        partial,
                        candidate,
                        (
                            "metrado × precio y evidencia OCR parcial"
                            if evidence
                            else "parcial recuperado como único campo faltante"
                        ),
                        distance,
                    )
                )

        if metrado is not None and price is not None and partial is not None:
            if not within_tolerance(partial, metrado * price, Decimal("0.01")):
                candidates = [
                    (
                        "parcial_soles",
                        partial,
                        _decimal_2(metrado * price),
                        row.parcial_ocr,
                    ),
                    (
                        "metrado",
                        metrado,
                        _decimal_2(partial / price) if price else metrado,
                        row.metrado_ocr,
                    ),
                    (
                        "precio_soles",
                        price,
                        _decimal_2(partial / metrado) if metrado else price,
                        row.precio_ocr,
                    ),
                ]
                plausible: List[
                    Tuple[str, Optional[Decimal], Decimal, str, int]
                ] = []
                for field_name, old, candidate, raw in candidates:
                    evidence, distance = _numeric_evidence_matches(raw, candidate)
                    if evidence and old != candidate:
                        key = normalize_description_key(row.descripcion)
                        repeated_prices = prices_by_description.get(key, [])
                        if (
                            field_name == "metrado"
                            and price is not None
                            and repeated_prices.count(price) >= 2
                        ):
                            distance -= 1
                        elif (
                            field_name == "precio_soles"
                            and repeated_prices.count(candidate) >= 2
                        ):
                            distance -= 1
                        plausible.append(
                            (
                                field_name,
                                old,
                                candidate,
                                "corrección de un dígito confirmada por ecuación",
                                distance,
                            )
                        )
                plausible.sort(key=lambda item: item[4])
                if (
                    plausible
                    and (
                        len(plausible) == 1
                        or plausible[0][4] < plausible[1][4]
                    )
                ):
                    changes.append(plausible[0])

        # Solo una corrección por fila y pasada: evita forzar conciliaciones.
        if not changes:
            continue
        changes.sort(key=lambda item: item[4])
        best = changes[0]
        if len(changes) > 1 and changes[0][4] == changes[1][4]:
            row.add_review(
                "Corrección numérica ambigua; candidatos: %s"
                % ", ".join(item[0] for item in changes)
            )
            continue
        field_name, old, corrected, method, unused_distance = best
        setattr(row, field_name, corrected)
        row.metodo_correccion = _append_message(row.metodo_correccion, method)
        row.confianza = "ALTA"
        row.add_rule(method)
        corrections.append(
            CorrectionRecord(
                tipo="Valor de partida",
                pagina=row.pagina,
                referencia=row.item,
                descripcion=row.descripcion,
                campo=field_name,
                original={
                    "metrado": row.metrado_ocr,
                    "precio_soles": row.precio_ocr,
                    "parcial_soles": row.parcial_ocr,
                }[field_name],
                corrected=corrected,
                method=method,
                confidence="ALTA",
            )
        )
        refresh_partida_review(row)
    return corrections


def refresh_partida_review(row: ExtractedRow) -> None:
    """Retira solo incidencias numéricas que una segunda pasada resolvió."""
    retained = [
        reason
        for reason in row.motivo_revision.split("; ")
        if reason
        and not reason.startswith("Faltan campos:")
        and reason != "El parcial no coincide con metrado por precio"
    ]
    missing = [
        name
        for value, name in (
            (row.und, "unidad"),
            (row.metrado, "metrado"),
            (row.precio_soles, "precio_soles"),
            (row.parcial_soles, "parcial_soles"),
        )
        if value in ("", None)
    ]
    if missing:
        retained.append("Faltan campos: %s" % ", ".join(missing))
    if (
        row.metrado is not None
        and row.precio_soles is not None
        and row.parcial_soles is not None
        and not within_tolerance(
            row.parcial_soles,
            row.metrado * row.precio_soles,
            Decimal("1"),
        )
    ):
        retained.append("El parcial no coincide con metrado por precio")
    row.motivo_revision = "; ".join(dict.fromkeys(retained))
    row.estado_revision = "REVISAR" if row.motivo_revision else "OK"


def validate_partida_values(
    metrado: Optional[Decimal],
    precio: Optional[Decimal],
    parcial: Optional[Decimal],
) -> List[str]:
    if metrado is None or precio is None or parcial is None:
        return []
    if within_tolerance(parcial, metrado * precio, Decimal("1")):
        return []
    return ["El parcial no coincide con metrado por precio"]


def overlap_ratio(word: Word, band: Band) -> float:
    overlap = max(0.0, min(word.x1, band.end) - max(word.x0, band.start))
    width = max(word.x1 - word.x0, 0.0001)
    return overlap / width


def assign_word_to_band(word: Word, page_bands: PageBands) -> Tuple[str, bool]:
    scored: List[Tuple[float, bool, str]] = []
    for band in page_bands.bands():
        ratio = overlap_ratio(word, band)
        contains_center = band.start <= word.center_x < band.end
        scored.append((ratio, contains_center, band.name))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    best = scored[0]
    tied = [
        score
        for score in scored
        if score[0] > 0 and abs(score[0] - best[0]) < 0.15
    ]
    ambiguous = len(tied) > 1
    return best[2], ambiguous


def assign_line_tokens(
    line: VisualLine, page_bands: PageBands
) -> Tuple[Dict[str, List[Word]], List[str]]:
    assigned: Dict[str, List[Word]] = {
        "item": [],
        "description": [],
        "unit": [],
        "metrado": [],
        "price": [],
        "partial": [],
    }
    ambiguities: List[str] = []
    for word in sorted(line.words, key=lambda item: item.x0):
        band_name, ambiguous = assign_word_to_band(word, page_bands)
        assigned[band_name].append(word)
        if ambiguous:
            ambiguities.append(
                "Token %r atraviesa bandas cerca de x=%.2f"
                % (word.text, word.center_x)
            )
    return assigned, ambiguities


def _header_key(text: str) -> str:
    return re.sub(r"[^a-záéíóúñ]", "", text.lower())


def _find_header(words: Sequence[Word], variants: Sequence[str]) -> Optional[Word]:
    for word in words:
        if _header_key(word.text) in variants:
            return word
    return None


def detect_page_bands(
    page: int,
    lines: Sequence[VisualLine],
    page_width: float,
    previous: Optional[PageBands] = None,
) -> Tuple[Optional[PageBands], Optional[int]]:
    for index, line in enumerate(lines):
        item = _find_header(line.words, ("item", "tem", "ftem"))
        description = _find_header(line.words, ("descripcion", "descripción"))
        unit = _find_header(line.words, ("und",))
        metrado = _find_header(line.words, ("metrado",))
        price = _find_header(line.words, ("precio",))
        partial = _find_header(line.words, ("parcial",))
        if all((item, description, unit, metrado, price, partial)):
            return (
                PageBands(
                    page=page,
                    item_start=item.x0,
                    description_start=description.x0,
                    unit_start=unit.x0,
                    metrado_start=metrado.x0,
                    price_start=price.x0,
                    partial_start=partial.x0,
                    page_end=page_width,
                    method="encabezado_pagina",
                ),
                index,
            )
    if previous is None:
        return None, None
    return (
        PageBands(
            page=page,
            item_start=previous.item_start,
            description_start=previous.description_start,
            unit_start=previous.unit_start,
            metrado_start=previous.metrado_start,
            price_start=previous.price_start,
            partial_start=previous.partial_start,
            page_end=page_width,
            method="bandas_pagina_anterior",
            review_reason="Encabezado de columnas no detectado; se reutilizaron bandas",
        ),
        None,
    )


def _words_text(words: Sequence[Word]) -> str:
    return " ".join(word.text for word in sorted(words, key=lambda item: item.x0)).strip()


def _single_numeric_token(
    words: Sequence[Word],
    page: int,
    context: str,
    target_center: Optional[float] = None,
) -> Tuple[str, NumberResult, str]:
    raw = _words_text(words)
    if not words:
        return raw, NumberResult(original="", value=None), ""
    numeric_words = [
        word for word in words if re.fullmatch(r"[+\-]?\d[\d.,]*", word.text)
    ]
    if len(numeric_words) == 1:
        result = parse_ocr_number(
            numeric_words[0].text, page, context, default_audit_logger
        )
        if len(words) > 1:
            noise = " ".join(
                word.text for word in words if word is not numeric_words[0]
            )
            logging.getLogger("presupuestos").info(
                "RUIDO_BANDA_NUMERICA pagina=%s campo=%s numero=%r ruido=%r",
                page,
                context,
                numeric_words[0].text,
                noise,
            )
        return raw, result, ""
    if len(numeric_words) > 1:
        ordered_numeric = sorted(numeric_words, key=lambda item: item.x0)
        numeric_gaps = [
            ordered_numeric[index + 1].x0 - ordered_numeric[index].x1
            for index in range(len(ordered_numeric) - 1)
        ]
        split_marker = any(
            word.text.endswith((",", "."))
            or word.text.startswith((",", "."))
            for word in ordered_numeric
        )
        combined_numeric = "".join(word.text for word in ordered_numeric)
        if (
            split_marker
            and numeric_gaps
            and max(numeric_gaps) <= 2.5
        ):
            combined_result = parse_ocr_number(
                combined_numeric,
                page,
                context,
                default_audit_logger,
            )
            if combined_result.value is not None:
                return (
                    raw,
                    combined_result,
                    "Fragmentos numéricos contiguos combinados",
                )
        if target_center is not None:
            ranked = sorted(
                (
                    (abs(word.center_x - target_center), word)
                    for word in numeric_words
                ),
                key=lambda item: item[0],
            )
            if len(ranked) == 1 or ranked[1][0] - ranked[0][0] >= 3.0:
                selected = ranked[0][1]
                result = parse_ocr_number(
                    selected.text,
                    page,
                    context,
                    default_audit_logger,
                )
                logging.getLogger("presupuestos").info(
                    "SELECCION_NUMERICA_GEOMETRIA pagina=%s campo=%s "
                    "seleccionado=%r candidatos=%r",
                    page,
                    context,
                    selected.text,
                    [word.text for word in numeric_words],
                )
                return raw, result, ""
        return (
            raw,
            NumberResult(original=raw, value=None),
            "Dos valores numéricos independientes en la banda %s: %s"
            % (context, raw),
        )
    # Solo se combinan fragmentos si ninguno es por sí solo un número válido.
    if len(words) > 1:
        individually_valid = [
            parse_ocr_number(word.text).value is not None for word in words
        ]
        gaps = [
            words[index + 1].x0 - words[index].x1
            for index in range(len(words) - 1)
        ]
        combined = "".join(word.text for word in words)
        if (
            not any(individually_valid)
            and gaps
            and max(gaps) <= 2.0
            and parse_ocr_number(combined).value is not None
        ):
            result = parse_ocr_number(
                combined, page, context, default_audit_logger
            )
            return raw, result, "Fragmentos numéricos contiguos combinados"
    result = parse_ocr_number(raw, page, context, default_audit_logger)
    return raw, result, result.rejection


def recover_numeric_from_adjacent_band(
    assigned: Dict[str, List[Word]],
    source_bands: Sequence[str],
    expected: Decimal,
    page: int,
    context: str,
) -> Tuple[str, Optional[Decimal], str]:
    """Recupera un único token desplazado que confirma la ecuación."""
    candidates: List[Tuple[str, Decimal]] = []
    seen: Set[Tuple[str, Decimal]] = set()
    for band_name in source_bands:
        for candidate_word in assigned.get(band_name, []):
            result = parse_ocr_number(candidate_word.text)
            if result.value is None:
                continue
            key = (candidate_word.text, result.value)
            if (
                key not in seen
                and within_tolerance(result.value, expected, Decimal("0.01"))
            ):
                candidates.append(key)
                seen.add(key)
    if len(candidates) != 1:
        return "", None, ""
    raw, value = candidates[0]
    method = "Valor recuperado desde banda vecina mediante ecuación"
    default_audit_logger(raw, str(value), page, method, context)
    return raw, value, method


def is_noise_line(line: VisualLine) -> bool:
    text = line.text.strip()
    if not text:
        return True
    if "====" in text or SUMMARY_LABEL_RE.match(text):
        return True
    if NOISE_RE.match(text):
        return True
    # Firmas y sellos suelen quedar muy abajo y sin estructura tabular.
    if line.top > 700 and not any(looks_like_item_code(word.text.strip("[]|")) for word in line.words):
        return True
    return False


def build_extracted_row(
    filename: str,
    line: VisualLine,
    page_bands: PageBands,
    order_document: int,
    evidence_codes: Optional[Set[str]] = None,
) -> ExtractedRow:
    assigned, ambiguities = assign_line_tokens(line, page_bands)
    item_text = _words_text(assigned["item"]).strip("[]| ")
    row = ExtractedRow(
        archivo_origen=filename,
        pagina=line.page,
        orden_documento=order_document,
        orden_pagina=line.order_page,
        posicion_y=round(line.top, 2),
        texto_fila_ocr=line.text,
        tokens_detectados=line.tokens_json,
        tipo_fila="fila_no_clasificada",
        assigned_tokens=assigned,
    )
    if page_bands.review_reason:
        row.add_review(page_bands.review_reason)
    for ambiguity in ambiguities:
        row.add_review(ambiguity)

    if is_noise_line(line):
        row.tipo_fila = "ruido_documental"
        return row

    if item_text and looks_like_item_code(item_text):
        code = normalize_item_code(
            item_text, line.page, evidence_codes, default_audit_logger
        )
        row.codigo_original = code.original
        row.codigo_normalizado = code.normalized
        row.add_rule(code.rule)
        row.add_review(code.review_reason)

        has_numeric_tokens = any(
            assigned[name] for name in ("metrado", "price", "partial")
        )
        recovered_unit_words = recover_unit_words_from_description(
            assigned,
            page_bands,
            has_numeric_tokens,
        )
        description_words = assigned["description"]
        row.description_x = (
            min(word.x0 for word in description_words)
            if description_words
            else page_bands.description_start
        )
        row.descripcion = _words_text(description_words)
        clear_unknown_unit = (
            has_numeric_tokens
            and len(assigned["unit"]) == 1
            and unit_geometry_is_clear(assigned["unit"][0], page_bands)
        )
        unit_result = split_unit_tokens(
            assigned["unit"],
            allow_unknown_candidate=clear_unknown_unit,
        )
        row.und_ocr = unit_result.original
        row.und = unit_result.normalized
        row.unit_incident_types.extend(unit_result.incident_types)
        if recovered_unit_words:
            row.unit_incident_types.append("unidad_recuperada_desde_descripcion")
            row.add_rule(
                "Unidad recuperada desde descripción según coordenadas originales"
            )
        if unit_result.reassigned_text:
            row.descripcion = " ".join(
                part
                for part in (row.descripcion, unit_result.reassigned_text)
                if part
            )
            logging.getLogger("presupuestos").info(
                "REASIGNACION_UNIDAD pagina=%s codigo=%r original=%r descripcion=%r regla=%s",
                line.page,
                row.codigo_original,
                unit_result.original,
                unit_result.reassigned_text,
                unit_result.rule,
            )
        row.add_rule(unit_result.rule)
        if unit_result.review_reason and row.und:
            row.add_review(unit_result.review_reason)
        if "posible_confusion_gb_glb" in row.unit_incident_types:
            row.add_review(
                "Posible confusión OCR gb/glb; se conserva gb sin corregir"
            )
        row.unit_incident_types = list(dict.fromkeys(row.unit_incident_types))
        for incident_type in row.unit_incident_types:
            logging.getLogger("presupuestos").info(
                "UNIDAD_OCR pagina=%s codigo=%r tipo=%s original=%r "
                "normalizada=%r regla=%s",
                line.page,
                row.codigo_original,
                incident_type,
                row.und_ocr,
                row.und,
                row.regla_normalizacion,
            )

        row.metrado_ocr, metrado_result, metrado_issue = _single_numeric_token(
            assigned["metrado"],
            line.page,
            "metrado",
            (page_bands.metrado_start + page_bands.price_start) / 2.0,
        )
        row.precio_ocr, price_result, price_issue = _single_numeric_token(
            assigned["price"],
            line.page,
            "precio_soles",
            (page_bands.price_start + page_bands.partial_start) / 2.0,
        )
        row.parcial_ocr, partial_result, partial_issue = _single_numeric_token(
            assigned["partial"],
            line.page,
            "parcial_soles",
            (page_bands.partial_start + page_bands.page_end) / 2.0,
        )
        row.metrado = metrado_result.value
        row.precio_soles = price_result.value
        row.parcial_ocr_decimal = partial_result.value
        row.parcial_soles = partial_result.value
        row.add_rule(metrado_result.rule)
        row.add_rule(price_result.rule)
        row.add_rule(partial_result.rule)
        for issue in (metrado_issue, price_issue, partial_issue):
            if issue:
                row.add_review(issue)

        if (
            row.parcial_soles is None
            and row.metrado is not None
            and row.precio_soles is not None
        ):
            shifted_raw, shifted_value, shifted_rule = (
                recover_numeric_from_adjacent_band(
                    assigned,
                    ("price",),
                    _decimal_2(row.metrado * row.precio_soles),
                    line.page,
                    "parcial_soles",
                )
            )
            if shifted_value is not None:
                row.parcial_ocr = shifted_raw
                row.parcial_soles = shifted_value
                row.add_rule(shifted_rule)
                row.metodo_correccion = _append_message(
                    row.metodo_correccion,
                    shifted_rule,
                )

        has_detail_values = bool(
            row.und
            or row.metrado_ocr
            or row.precio_ocr
            or (
                row.parcial_ocr
                and (row.metrado_ocr or row.precio_ocr)
            )
        )
        if has_detail_values:
            row.tipo_fila = "partida"
            for reason in validate_partida_values(
                row.metrado, row.precio_soles, row.parcial_soles
            ):
                row.add_review(reason)
            missing = [
                name
                for value, name in (
                    (row.und, "unidad"),
                    (row.metrado, "metrado"),
                    (row.precio_soles, "precio_soles"),
                    (row.parcial_soles, "parcial_soles"),
                )
                if value in ("", None)
            ]
            if missing:
                row.add_review("Faltan campos: %s" % ", ".join(missing))
        elif row.parcial_ocr and row.descripcion:
            row.tipo_fila = "grupo"  # El nivel definitivo se asigna con contexto.
            row.total_agrupador_soles = partial_result.value
            row.parcial_soles = None
        else:
            row.tipo_fila = "fila_no_clasificada"
            row.motivo_no_clasificacion = (
                "Código detectado sin estructura suficiente de partida o agrupador"
            )
    else:
        description = _words_text(assigned["description"])
        has_values = any(
            assigned[name] for name in ("unit", "metrado", "price", "partial")
        )
        possible_unit = split_unit_tokens(
            assigned["unit"],
            allow_unknown_candidate=(
                len(assigned["unit"]) == 1
                and unit_geometry_is_clear(assigned["unit"][0], page_bands)
            ),
        )
        metrado_raw, metrado_candidate, metrado_issue = _single_numeric_token(
            assigned["metrado"],
            line.page,
            "metrado",
            (page_bands.metrado_start + page_bands.price_start) / 2.0,
        )
        price_raw, price_candidate, price_issue = _single_numeric_token(
            assigned["price"],
            line.page,
            "precio_soles",
            (page_bands.price_start + page_bands.partial_start) / 2.0,
        )
        partial_raw, partial_candidate, partial_issue = _single_numeric_token(
            assigned["partial"],
            line.page,
            "parcial_soles",
            (page_bands.partial_start + page_bands.page_end) / 2.0,
        )
        numeric_count = sum(
            value is not None
            for value in (
                metrado_candidate.value,
                price_candidate.value,
                partial_candidate.value,
            )
        )
        partial_code = bool(
            item_text
            and len(item_text) <= 12
            and re.search(r"[A-Z0-9]", item_text, re.IGNORECASE)
        )
        recovery_score = (
            (2 if description else 0)
            + (1 if partial_code else 0)
            + (1 if possible_unit.normalized else 0)
            + numeric_count
        )
        if (
            metrado_candidate.value is not None
            and price_candidate.value is not None
            and partial_candidate.value is not None
            and within_tolerance(
                metrado_candidate.value * price_candidate.value,
                partial_candidate.value,
                Decimal("1"),
            )
        ):
            recovery_score += 2

        if recovery_score >= 6 and description and partial_code:
            row.tipo_fila = "partida"
            row.codigo_original = item_text
            row.codigo_normalizado = item_text
            row.descripcion = description
            row.description_x = min(
                (word.x0 for word in assigned["description"]),
                default=page_bands.description_start,
            )
            row.und_ocr = possible_unit.original
            row.und = possible_unit.normalized
            row.unit_incident_types.extend(possible_unit.incident_types)
            row.metrado_ocr = metrado_raw
            row.metrado = metrado_candidate.value
            row.precio_ocr = price_raw
            row.precio_soles = price_candidate.value
            row.parcial_ocr = partial_raw
            row.parcial_ocr_decimal = partial_candidate.value
            row.parcial_soles = partial_candidate.value
            row.fila_recuperada = True
            row.metodo_correccion = (
                "fila recuperada por geometría, contenido y columnas numéricas"
            )
            row.confianza = "ALTA" if recovery_score >= 8 else "MEDIA"
            row.nota = "Fila recuperada"
            row.add_rule(row.metodo_correccion)
            for issue in (metrado_issue, price_issue, partial_issue):
                if issue:
                    row.add_review(issue)
            missing = [
                name
                for value, name in (
                    (row.und, "unidad"),
                    (row.metrado, "metrado"),
                    (row.precio_soles, "precio_soles"),
                    (row.parcial_soles, "parcial_soles"),
                )
                if value in ("", None)
            ]
            if missing:
                row.add_review("Faltan campos: %s" % ", ".join(missing))
            logging.getLogger("presupuestos").info(
                "FILA_RECUPERADA pagina=%s codigo_ocr=%r puntuacion=%s "
                "descripcion=%r",
                line.page,
                item_text,
                recovery_score,
                description,
            )
        elif description and not has_values:
            row.tipo_fila = "continuacion_descripcion"
            row.posible_descripcion = description
        else:
            row.tipo_fila = "fila_no_clasificada"
            row.posible_item = item_text
            row.posible_descripcion = description
            row.posible_und = _words_text(assigned["unit"])
            row.posible_metrado = _words_text(assigned["metrado"])
            row.posible_precio = _words_text(assigned["price"])
            row.posible_parcial = _words_text(assigned["partial"])
            row.motivo_no_clasificacion = (
                "Línea de tabla sin código de ítem clasificable"
            )
    return row


def determine_hierarchy_level(
    row: ExtractedRow, state: HierarchyState
) -> int:
    """Combina sangría, código y jerarquía activa para un agrupador."""
    x = row.description_x
    code = row.codigo_normalizado or row.codigo_original

    if not state.categoria_codigo:
        return 1
    if x <= state.categoria_x + 1.5 and re.fullmatch(r"\d{1,4}", code):
        return 1
    if state.grupo_codigo and x > state.grupo_x + 1.5:
        return 3
    if x > state.categoria_x + 2.0:
        if state.grupo_codigo:
            return 3
        return 2
    if re.fullmatch(r"\d{1,4}\.[A-Z0-9]{1,3}", code, re.IGNORECASE):
        return 2
    return 1


def apply_hierarchy(
    rows: Sequence[ExtractedRow],
    initial_state: Optional[HierarchyState] = None,
) -> HierarchyState:
    state = initial_state or HierarchyState()
    for row in rows:
        if row.tipo_fila in ("grupo", "categoria", "subgrupo"):
            level = determine_hierarchy_level(row, state)
            row.nivel_jerarquia = level
            if level == 1:
                row.tipo_fila = "categoria"
                state.categoria_codigo = row.item
                state.categoria = row.descripcion
                state.categoria_x = row.description_x
                state.grupo_codigo = ""
                state.grupo = ""
                state.grupo_x = 0.0
                state.subgrupo_codigo = ""
                state.subgrupo = ""
                state.subgrupo_x = 0.0
                row.codigo_padre = ""
            elif level == 2:
                row.tipo_fila = "grupo"
                state.grupo_codigo = row.item
                state.grupo = row.descripcion
                state.grupo_x = row.description_x
                state.subgrupo_codigo = ""
                state.subgrupo = ""
                state.subgrupo_x = 0.0
                row.codigo_padre = state.categoria_codigo
            else:
                row.tipo_fila = "subgrupo"
                state.subgrupo_codigo = row.item
                state.subgrupo = row.descripcion
                state.subgrupo_x = row.description_x
                row.codigo_padre = state.grupo_codigo or state.categoria_codigo
        elif row.tipo_fila == "partida":
            row.nivel_jerarquia = 4
            row.codigo_padre = (
                state.subgrupo_codigo
                or state.grupo_codigo
                or state.categoria_codigo
            )

        if row.tipo_fila in ("categoria", "grupo", "subgrupo", "partida"):
            row.categoria_codigo = state.categoria_codigo
            row.categoria = state.categoria
            row.grupo_codigo = state.grupo_codigo
            row.grupo = state.grupo
            row.subgrupo_codigo = state.subgrupo_codigo
            row.subgrupo = state.subgrupo
    return state


def infer_hierarchy_level_v6(
    row: ExtractedRow,
    stack: HierarchyStack,
) -> str:
    code = (
        row.item or row.codigo_original
    ).upper().replace(",", ".")
    if code == "000" or stack.proyecto is None:
        return "proyecto"
    title = normalize_description_key(row.descripcion)
    if code == "1000" and "PUENTE" in title:
        return "capitulo"
    if re.fullmatch(r"1000\.[A-Z]", code) and "PUENTE" in title:
        return "subcapitulo"
    if re.fullmatch(r"\d{3,4}", code):
        number = int(code)
        if (
            stack.subcapitulo is not None
            and stack.subcapitulo.code.startswith("1000.")
            and 1001 <= number <= 1009
        ):
            return "seccion"
        if number % 100 == 0:
            return "capitulo"
        return "seccion" if stack.subcapitulo is not None else "capitulo"
    match_letter = re.fullmatch(r"(\d{3,4})\.([A-Z])", code)
    if match_letter:
        base = match_letter.group(1)
        if stack.capitulo is not None and base == stack.capitulo.code:
            return "subcapitulo"
        return "seccion"
    if re.fullmatch(r"\d{3,4}\.[A-Z]\d+", code):
        return "seccion"
    if re.fullmatch(r"\d{3,4}\.\d+", code):
        base = code.split(".", 1)[0]
        if stack.seccion is not None and base == stack.seccion.code:
            return "subseccion"
        return "subseccion"
    if stack.seccion is not None:
        return "subseccion"
    if stack.subcapitulo is not None:
        return "seccion"
    return "subcapitulo"


def _node_label(node: HierarchyNode) -> str:
    code = node.code if node.code else "[PENDIENTE]"
    return ("%s %s" % (code, node.title)).strip()


def reset_hierarchy_v6(rows: Sequence[ExtractedRow]) -> None:
    """Limpia la jerarquía preliminar antes de reconstruir la definitiva."""
    for row in rows:
        row.codigo_padre = ""
        row.capitulo_codigo = ""
        row.capitulo = ""
        row.subcapitulo_codigo = ""
        row.subcapitulo = ""
        row.seccion_codigo = ""
        row.seccion = ""
        row.subseccion_codigo = ""
        row.subseccion = ""
        row.ruta_jerarquica = ""


def apply_hierarchy_v6(
    rows: Sequence[ExtractedRow],
) -> List[HierarchyNode]:
    stack = HierarchyStack()
    nodes: List[HierarchyNode] = []
    nodes_by_id: Dict[str, HierarchyNode] = {}
    chapter_by_code: Dict[str, HierarchyNode] = {}
    for row in rows:
        if row.tipo_fila in ("grupo", "categoria", "subgrupo"):
            inference_code = (
                row.item or row.codigo_original
            ).upper().replace(",", ".")
            title_key = normalize_description_key(row.descripcion)
            if (
                re.fullmatch(r"1000\.[A-Z]", inference_code)
                and "PUENTE" in title_key
            ):
                bridge_chapter = chapter_by_code.get("1000")
                if bridge_chapter is not None:
                    stack.set("capitulo", bridge_chapter)
            level = (
                row.nivel_forzado_v6
                if row.nivel_forzado_v6 in HIERARCHY_LEVELS
                else infer_hierarchy_level_v6(row, stack)
            )
            level_index = HIERARCHY_LEVELS.index(level)
            parent: Optional[HierarchyNode] = (
                nodes_by_id.get(row.padre_esperado_id)
                if row.padre_esperado_id
                else None
            )
            if parent is None:
                for parent_level in reversed(HIERARCHY_LEVELS[:level_index]):
                    parent = stack.get(parent_level)
                    if parent is not None:
                        break

            code = row.item
            pending_id = "PENDIENTE@pagina%s_orden%s" % (
                row.pagina,
                row.orden_documento,
            )
            if level in ("proyecto", "capitulo") or parent is None:
                node_id = code or pending_id
            else:
                node_id = "%s|%s" % (
                    parent.node_id,
                    code or pending_id,
                )

            existing = nodes_by_id.get(node_id)
            if (
                existing is not None
                and normalize_description_key(existing.title)
                == normalize_description_key(row.descripcion)
            ):
                stack.set(level, existing)
                row.nivel_jerarquia = level_index
                row.codigo_padre = existing.parent_id
                continue

            provisional = HierarchyNode(
                order_document=row.orden_documento,
                page=row.pagina,
                level=level,
                node_id=node_id,
                code_ocr=row.codigo_original,
                code=code,
                title=row.descripcion,
                parent_id=parent.node_id if parent is not None else "",
                path="",
                total_ocr=row.total_agrupador_soles,
                total=row.total_agrupador_soles,
                correction=(
                    row.metodo_correccion
                    if row.codigo_original != code
                    else ""
                ),
                code_state="REVISAR" if row.codigo_pendiente else "OK",
                candidates=(
                    row.motivo_revision if row.codigo_pendiente else ""
                ),
            )
            stack.set(level, provisional)
            provisional.path = " > ".join(
                _node_label(node) for node in stack.active_nodes(True)
            )
            nodes.append(provisional)
            nodes_by_id[node_id] = provisional
            if level == "capitulo":
                chapter_by_code[code] = provisional
            row.nivel_jerarquia = level_index
            row.codigo_padre = provisional.parent_id
        elif row.tipo_fila == "partida":
            active = stack.active_nodes(False)
            row.ruta_jerarquica = " > ".join(
                _node_label(node) for node in active
            )
            if stack.capitulo is not None:
                row.capitulo_codigo = stack.capitulo.code
                row.capitulo = stack.capitulo.title
            if stack.subcapitulo is not None:
                row.subcapitulo_codigo = stack.subcapitulo.code
                row.subcapitulo = stack.subcapitulo.title
            if stack.seccion is not None:
                row.seccion_codigo = stack.seccion.code
                row.seccion = stack.seccion.title
            if stack.subseccion is not None:
                row.subseccion_codigo = stack.subseccion.code
                row.subseccion = stack.subseccion.title
            parent = (
                stack.subseccion
                or stack.seccion
                or stack.subcapitulo
                or stack.capitulo
                or stack.proyecto
            )
            row.codigo_padre = parent.node_id if parent is not None else ""
    return nodes


def absorb_continuations(rows: Sequence[ExtractedRow]) -> None:
    previous_structural: Optional[ExtractedRow] = None
    for row in rows:
        if row.tipo_fila in ("categoria", "grupo", "subgrupo", "partida"):
            previous_structural = row
        elif row.tipo_fila == "continuacion_descripcion":
            if previous_structural is None:
                row.tipo_fila = "fila_no_clasificada"
                row.motivo_no_clasificacion = (
                    "Continuación sin fila estructural anterior"
                )
                continue
            continuation = row.posible_descripcion or row.texto_fila_ocr
            previous_structural.descripcion = " ".join(
                part for part in (previous_structural.descripcion, continuation) if part
            )
            previous_structural.add_rule(
                "Descripción multilínea absorbida desde página %s" % row.pagina
            )


def occurrence_key(row: ExtractedRow) -> Tuple[str, int, int, float, str, str]:
    return (
        row.archivo_origen,
        row.pagina,
        row.orden_pagina,
        round(row.posicion_y, 1),
        row.codigo_original,
        row.texto_fila_ocr,
    )


def deduplicate_occurrences(
    rows: Iterable[ExtractedRow],
) -> List[ExtractedRow]:
    seen: Set[Tuple[str, int, int, float, str, str]] = set()
    result: List[ExtractedRow] = []
    for row in rows:
        key = occurrence_key(row)
        if key in seen:
            logging.getLogger("presupuestos").warning(
                "OCURRENCIA_DUPLICADA archivo=%s pagina=%s orden=%s codigo=%r",
                row.archivo_origen,
                row.pagina,
                row.orden_pagina,
                row.codigo_original,
            )
            continue
        seen.add(key)
        result.append(row)
    return result


def deduplicate_partidas(partidas: Iterable[Partida]) -> List[Partida]:
    """Compatibilidad: no elimina códigos repetidos si pertenecen a otra ocurrencia."""
    return list(partidas)


def merge_multiline_descriptions(
    rows: Sequence[RawPartida], continuations: Sequence[Tuple[int, str]]
) -> List[RawPartida]:
    result = [
        RawPartida(
            page=row.page,
            item=row.item,
            descripcion=row.descripcion,
            und=row.und,
            metrado_raw=row.metrado_raw,
            precio_raw=row.precio_raw,
            parcial_raw=row.parcial_raw,
            item_sospechoso=row.item_sospechoso,
        )
        for row in rows
    ]
    for index, text in continuations:
        if 0 <= index < len(result):
            result[index].descripcion = " ".join(
                (result[index].descripcion, " ".join(text.split()))
            ).strip()
    return result


def is_grouping_row(row: RawPartida) -> bool:
    return bool(
        row.item
        and row.descripcion
        and row.parcial_raw
        and not row.und
        and not row.metrado_raw
        and not row.precio_raw
    )


def group_words_into_lines(words: Sequence[Word], page: int) -> List[VisualLine]:
    lines: List[VisualLine] = []
    for word in sorted(words, key=lambda item: (item.top, item.x0)):
        target: Optional[VisualLine] = None
        for line in reversed(lines[-4:]):
            if abs(line.top - word.top) <= 3.0:
                target = line
                break
        if target is None:
            target = VisualLine(page=page, top=word.top, words=[])
            lines.append(target)
        target.words.append(word)
    for order, line in enumerate(lines, 1):
        line.words.sort(key=lambda item: item.x0)
        line.order_page = order
    return lines


def _parse_date(value: str) -> Optional[date]:
    match = DATE_RE.search(value)
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def extract_general_data(lines: Sequence[VisualLine]) -> GeneralData:
    data = GeneralData()
    for line in lines:
        text = " ".join(line.text.split())
        lower = text.lower()
        if not data.codigo_presupuesto:
            match = re.search(r"\bpresupuesto\s+([A-Z0-9.-]+)", text, re.IGNORECASE)
            if match and any(character.isdigit() for character in match.group(1)):
                data.codigo_presupuesto = match.group(1)
        if not data.codigo_subpresupuesto:
            match = re.search(r"\bsubpresupuesto\s+([A-Z0-9.-]+)", text, re.IGNORECASE)
            if match:
                data.codigo_subpresupuesto = match.group(1)
        if not data.cliente and re.match(
            r"^(cliente|propietario|solicitante)\b", lower
        ):
            value = re.sub(
                r"^(cliente|propietario|solicitante)\s*:?\s*",
                "",
                text,
                flags=re.IGNORECASE,
            )
            value = re.split(
                r"\b(?:costo\s+al|fecha\s+(?:de\s+)?(?:costo|costos|presupuesto))\b",
                value,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]
            data.cliente = value.strip(" :-")
        if not data.lugar and re.match(r"^(lugar|ubicaci[oó]n|obra)\b", lower):
            data.lugar = re.sub(
                r"^(lugar|ubicaci[oó]n|obra)\s*:?\s*",
                "",
                text,
                flags=re.IGNORECASE,
            ).strip()
        if data.fecha_costo is None and re.search(
            r"\b(?:costo\s+al|fecha\s+(?:de\s+)?(?:costo|costos|presupuesto))\b",
            text,
            re.IGNORECASE,
        ):
            data.fecha_costo = _parse_date(text)
    return data


def _last_numeric_word(line: VisualLine) -> str:
    numeric = [
        word.text
        for word in line.words
        if re.fullmatch(r"[+\-]?\d[\d.,]*", word.text)
    ]
    return numeric[-1] if numeric else ""


def _percentage_text(text: str) -> str:
    match = re.search(r"\(([^)]*?)\s*%\s*\)", text)
    return match.group(1).strip() if match else ""


def extract_economic_summary(lines: Sequence[VisualLine]) -> ResumenEconomico:
    summary = ResumenEconomico()
    for line in sorted(lines, key=lambda item: (item.page, item.top), reverse=True):
        text = " ".join(line.text.split())
        upper = text.upper()
        if "====" in text:
            continue
        if upper.startswith("SON:") and not summary.monto_en_letras:
            summary.monto_en_letras = text.split(":", 1)[1].strip()
            summary.page = line.page
        elif upper.startswith("COSTO DIRECTO") and summary.costo_directo_soles is None:
            summary.costo_directo_soles = normalize_ocr_number(
                _last_numeric_word(line),
                line.page,
                "costo_directo_soles",
                default_audit_logger,
            )
            summary.page = line.page
        elif (
            upper.startswith("GASTOS GENERALES") or re.match(r"^G\.?\s*G\.?", upper)
        ) and summary.gastos_generales_soles is None:
            summary.gastos_generales_porcentaje = normalize_ocr_number(
                _percentage_text(text),
                line.page,
                "gastos_generales_porcentaje",
                default_audit_logger,
                True,
            )
            summary.gastos_generales_soles = normalize_ocr_number(
                _last_numeric_word(line),
                line.page,
                "gastos_generales_soles",
                default_audit_logger,
            )
        elif upper.startswith("UTILIDAD") and summary.utilidad_soles is None:
            summary.utilidad_porcentaje = normalize_ocr_number(
                _percentage_text(text),
                line.page,
                "utilidad_porcentaje",
                default_audit_logger,
                True,
            )
            summary.utilidad_soles = normalize_ocr_number(
                _last_numeric_word(line),
                line.page,
                "utilidad_soles",
                default_audit_logger,
            )
        elif re.match(r"^SUB-?\s*TOTAL\b", upper) and summary.subtotal_soles is None:
            summary.subtotal_soles = normalize_ocr_number(
                _last_numeric_word(line),
                line.page,
                "subtotal_soles",
                default_audit_logger,
            )
        elif upper.startswith("IGV") and summary.igv_soles is None:
            summary.igv_porcentaje = normalize_ocr_number(
                _percentage_text(text),
                line.page,
                "igv_porcentaje",
                default_audit_logger,
                True,
            )
            summary.igv_soles = normalize_ocr_number(
                _last_numeric_word(line),
                line.page,
                "igv_soles",
                default_audit_logger,
            )
        elif (
            upper.startswith("PRESUPUESTO TOTAL")
            or upper.startswith("TOTAL PRESUPUESTO")
        ) and summary.presupuesto_total_soles is None:
            summary.presupuesto_total_soles = normalize_ocr_number(
                _last_numeric_word(line),
                line.page,
                "presupuesto_total_soles",
                default_audit_logger,
            )
    return summary


def _validate_relation(
    label: str,
    actual: Optional[Decimal],
    expected: Optional[Decimal],
    messages: List[str],
) -> None:
    if actual is None or expected is None:
        messages.append("%s: NO VALIDADA (dato faltante)" % label)
    elif within_tolerance(actual, expected, Decimal("0.01")):
        messages.append("%s: OK" % label)
    else:
        messages.append(
            "%s: REVISAR (diferencia S/ %s)" % (label, actual - expected)
        )


def validate_economic_summary(
    summary: ResumenEconomico, leaf_sum: Optional[Decimal] = None
) -> List[str]:
    messages: List[str] = []
    if leaf_sum is not None:
        _validate_relation(
            "Suma de parciales vs costo directo",
            leaf_sum,
            summary.costo_directo_soles,
            messages,
        )
    subtotal_expected: Optional[Decimal] = None
    if (
        summary.costo_directo_soles is not None
        and summary.gastos_generales_soles is not None
        and summary.utilidad_soles is not None
    ):
        subtotal_expected = (
            summary.costo_directo_soles
            + summary.gastos_generales_soles
            + summary.utilidad_soles
        )
    _validate_relation(
        "Costo directo + gastos generales + utilidad vs subtotal",
        summary.subtotal_soles,
        subtotal_expected,
        messages,
    )
    total_expected: Optional[Decimal] = None
    if summary.subtotal_soles is not None and summary.igv_soles is not None:
        total_expected = summary.subtotal_soles + summary.igv_soles
    _validate_relation(
        "Subtotal + IGV vs presupuesto total",
        summary.presupuesto_total_soles,
        total_expected,
        messages,
    )
    gg_expected: Optional[Decimal] = None
    if (
        summary.costo_directo_soles is not None
        and summary.gastos_generales_porcentaje is not None
    ):
        gg_expected = (
            summary.costo_directo_soles
            * summary.gastos_generales_porcentaje
            / Decimal("100")
        )
    _validate_relation(
        "Gastos generales calculados desde porcentaje",
        summary.gastos_generales_soles,
        gg_expected,
        messages,
    )
    utility_expected: Optional[Decimal] = None
    if (
        summary.costo_directo_soles is not None
        and summary.utilidad_porcentaje is not None
    ):
        utility_expected = (
            summary.costo_directo_soles
            * summary.utilidad_porcentaje
            / Decimal("100")
        )
    _validate_relation(
        "Utilidad calculada desde porcentaje",
        summary.utilidad_soles,
        utility_expected,
        messages,
    )
    igv_expected: Optional[Decimal] = None
    if summary.subtotal_soles is not None and summary.igv_porcentaje is not None:
        igv_expected = (
            summary.subtotal_soles * summary.igv_porcentaje / Decimal("100")
        )
    _validate_relation(
        "IGV calculado desde porcentaje",
        summary.igv_soles,
        igv_expected,
        messages,
    )
    return messages


def reconcile_page(
    filename: str,
    page: int,
    rows: Sequence[ExtractedRow],
    bands: PageBands,
) -> PageControl:
    control = PageControl(
        archivo_origen=filename,
        pagina=page,
        filas_detectadas_en_tabla=len(rows),
        categorias=sum(row.tipo_fila == "categoria" for row in rows),
        grupos=sum(row.tipo_fila == "grupo" for row in rows),
        subgrupos=sum(row.tipo_fila == "subgrupo" for row in rows),
        partidas=sum(row.tipo_fila == "partida" for row in rows),
        continuaciones_absorbidas=sum(
            row.tipo_fila == "continuacion_descripcion" for row in rows
        ),
        filas_no_clasificadas=sum(
            row.tipo_fila == "fila_no_clasificada" for row in rows
        ),
        ruido_documental=sum(
            row.tipo_fila == "ruido_documental" for row in rows
        ),
        filas_descartadas=0,
        item_x_inicio=round(bands.item_start, 2),
        descripcion_x_inicio=round(bands.description_start, 2),
        und_x_inicio=round(bands.unit_start, 2),
        metrado_x_inicio=round(bands.metrado_start, 2),
        precio_x_inicio=round(bands.price_start, 2),
        parcial_x_inicio=round(bands.partial_start, 2),
        metodo_deteccion_bandas=bands.method,
    )
    reasons: List[str] = []
    if bands.review_reason:
        reasons.append(bands.review_reason)
    if control.reconciled_total != control.filas_detectadas_en_tabla:
        reasons.append(
            "Diferencia de conciliación: detectadas=%s conciliadas=%s"
            % (control.filas_detectadas_en_tabla, control.reconciled_total)
        )
    if control.filas_descartadas != 0:
        reasons.append("filas_descartadas debe ser cero")
    if reasons:
        control.estado_control = "REVISAR"
        control.motivo_control = "; ".join(reasons)
    return control


def _import_pdfplumber():
    try:
        import pdfplumber  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pdfplumber no está disponible") from exc
    return pdfplumber


def pdf_has_usable_text(pdf_path: Path, minimum_words: int = 20) -> bool:
    """Comprueba si existe texto suficiente sin alterar el documento."""
    pdfplumber = _import_pdfplumber()
    total_words = 0
    with pdfplumber.open(str(pdf_path)) as document:
        for page in document.pages:
            total_words += len(
                page.extract_words(
                    x_tolerance=2,
                    y_tolerance=3,
                    use_text_flow=False,
                )
            )
            if total_words >= minimum_words:
                return True
    return False


def prepare_searchable_pdf(
    pdf_path: Path,
    logger: logging.Logger,
    processed_dir: Optional[Path] = None,
) -> Path:
    """Devuelve el PDF original si ya tiene texto o crea un OCR derivado."""
    source = pdf_path.resolve()
    if pdf_has_usable_text(source):
        logger.info("PDF_TEXTO_UTIL original=%s ocr_requerido=no", source)
        return source

    target_dir = (processed_dir or Path("procesados")).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    derived = target_dir / ("%s_ocr_v6.pdf" % source.stem)
    if derived.exists():
        raise FileExistsError(
            "El PDF OCR derivado ya existe y no será sobrescrito: %s" % derived
        )

    try:
        version = subprocess.run(
            ["ocrmypdf", "--version"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("No se pudo consultar OCRmyPDF: %s" % exc) from exc

    command = [
        "ocrmypdf",
        "-l",
        "spa",
        "--rotate-pages",
        "--deskew",
        "--clean",
        "--skip-text",
        str(source),
        str(derived),
    ]
    logger.info(
        "OCR_INICIO original=%s derivado=%s ocrmypdf=%s idioma=spa",
        source,
        derived,
        version,
    )
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError("OCRmyPDF no está disponible: %s" % exc) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError("OCRmyPDF falló: %s" % detail) from exc
    logger.info(
        "OCR_FIN original=%s derivado=%s salida=%s",
        source,
        derived,
        (completed.stderr or completed.stdout or "").strip(),
    )
    if not derived.exists() or not pdf_has_usable_text(derived):
        raise RuntimeError(
            "OCRmyPDF terminó pero el PDF derivado no contiene texto utilizable"
        )
    return derived


def read_pdf_lines(
    pdf_path: Path,
) -> Tuple[List[VisualLine], Dict[int, List[VisualLine]], Dict[int, float]]:
    pdfplumber = _import_pdfplumber()
    all_lines: List[VisualLine] = []
    by_page: Dict[int, List[VisualLine]] = {}
    widths: Dict[int, float] = {}
    with pdfplumber.open(str(pdf_path)) as document:
        for page_number, page in enumerate(document.pages, 1):
            extracted = page.extract_words(
                x_tolerance=2, y_tolerance=3, use_text_flow=False
            )
            words = [
                Word(
                    text=item["text"],
                    x0=float(item["x0"]),
                    x1=float(item["x1"]),
                    top=float(item["top"]),
                    bottom=float(item["bottom"]),
                )
                for item in extracted
            ]
            lines = group_words_into_lines(words, page_number)
            by_page[page_number] = lines
            widths[page_number] = float(page.width)
            all_lines.extend(lines)
    return all_lines, by_page, widths


def _collect_correct_code_evidence(lines: Sequence[VisualLine]) -> Set[str]:
    evidence: Set[str] = set()
    for line in lines:
        for word in line.words:
            token = word.text.strip("[]|")
            if is_item_code(token) and re.search(r"\.[AB](?:\.|$)", token):
                evidence.add(token)
    return evidence


def _process_searchable_pdf(
    searchable_pdf: Path,
    source_name: str,
    logger: logging.Logger,
    approved_code_review: Optional[Path] = None,
    approved_numeric_review: Optional[Path] = None,
) -> DocumentResult:
    all_lines, by_page, widths = read_pdf_lines(searchable_pdf)
    general = extract_general_data(all_lines)
    summary = extract_economic_summary(all_lines)
    processed_at = datetime.now().replace(microsecond=0)
    all_rows: List[ExtractedRow] = []
    page_rows: Dict[int, List[ExtractedRow]] = {}
    page_bands: Dict[int, PageBands] = {}
    previous_bands: Optional[PageBands] = None
    order_document = 0

    for page in sorted(by_page):
        lines = by_page[page]
        bands, header_index = detect_page_bands(
            page, lines, widths[page], previous_bands
        )
        if bands is None:
            continue  # Página anterior a la primera tabla (por ejemplo, portada).
        previous_bands = bands
        page_bands[page] = bands
        if header_index is None:
            start_index = next(
                (
                    index
                    for index, line in enumerate(lines)
                    if any(
                        looks_like_item_code(word.text.strip("[]|"))
                        for word in line.words
                    )
                ),
                len(lines),
            )
        else:
            start_index = header_index + 1
        detected: List[ExtractedRow] = []
        for line in lines[start_index:]:
            order_document += 1
            detected.append(
                build_extracted_row(
                    source_name,
                    line,
                    bands,
                    order_document,
                    # No se considera inequívoca una coincidencia basada solo
                    # en el código; A/4 y B/8 quedan para revisión contextual.
                    None,
                )
            )
        page_rows[page] = detected
        all_rows.extend(detected)

    all_rows = deduplicate_occurrences(all_rows)
    # Las continuaciones atraviesan páginas y deben completar la descripción
    # antes de construir el catálogo documental.
    absorb_continuations(all_rows)
    catalog = build_document_code_catalog(all_rows)
    corrections: List[CorrectionRecord] = []
    corrections.extend(apply_unit_document_corrections(all_rows))
    recover_document_decimals(all_rows)
    corrections.extend(apply_numeric_corrections(all_rows))
    if approved_numeric_review is not None:
        corrections.extend(
            apply_approved_numeric_reviews(
                approved_numeric_review,
                searchable_pdf,
                source_name,
                all_rows,
            )
        )
    corrections.extend(propose_human_numeric_corrections(all_rows))
    for row in all_rows:
        if row.fila_recuperada:
            corrections.append(
                CorrectionRecord(
                    tipo="Fila recuperada",
                    pagina=row.pagina,
                    referencia=row.item,
                    descripcion=row.descripcion,
                    campo="fila",
                    original=row.texto_fila_ocr,
                    corrected=row.item,
                    method=(
                        "clasificación por geometría, descripción y "
                        "columnas numéricas"
                    ),
                    confidence=row.confianza,
                )
            )
        if "unidad_normalizada" in row.unit_incident_types:
            corrections.append(
                CorrectionRecord(
                    tipo="Unidad",
                    pagina=row.pagina,
                    referencia=row.item,
                    descripcion=row.descripcion,
                    campo="unidad",
                    original=row.und_ocr,
                    corrected=row.und,
                    method="Normalización de unidad inequívoca",
                    confidence="ALTA",
                )
            )
        if "Decimal recuperado" in row.regla_normalizacion:
            corrections.append(
                CorrectionRecord(
                    tipo="Valor de partida",
                    pagina=row.pagina,
                    referencia=row.item,
                    descripcion=row.descripcion,
                    campo="metrado",
                    original=row.metrado_ocr,
                    corrected=row.metrado,
                    method="Decimal recuperado mediante ecuación",
                    confidence="ALTA",
                )
            )

    # Fase 6: primero se resuelve la estructura con evidencia global. Solo
    # después se evalúan las partidas y se reconstruyen todas las rutas.
    apply_hierarchy_v6(all_rows)
    initial_code_audit = audit_document_codes(all_rows, catalog)
    corrections.extend(finalize_structural_codes(all_rows, catalog))
    reset_hierarchy_v6(all_rows)
    apply_hierarchy_v6(all_rows)
    corrections.extend(finalize_partida_codes(all_rows, catalog))
    if approved_code_review is not None:
        corrections.extend(
            apply_approved_code_reviews(
                approved_code_review,
                source_name,
                all_rows,
            )
        )
    reset_hierarchy_v6(all_rows)
    nodes_v6 = apply_hierarchy_v6(all_rows)
    code_reviews = build_code_review_records(
        source_name,
        all_rows,
        catalog,
    )
    final_code_audit = audit_final_document_codes(all_rows)
    high_codes = sum(
        record.confidence == "ALTA"
        and record.tipo in (
            "Código de partida",
            "Estructura",
            "Código OCR validado",
        )
        for record in corrections
    )
    medium_codes = sum(
        record.confidence == "MEDIA"
        and record.tipo in ("Código propuesto", "Código pendiente")
        for record in corrections
    )
    low_codes = sum(
        record.confidence == "BAJA"
        and record.tipo in ("Código propuesto", "Código pendiente")
        for record in corrections
    )
    incomplete_initial = sum(
        record.ocr_code.endswith((".", ","))
        for record in initial_code_audit
    )
    incomplete_pending = sum(
        record.ocr_code.endswith((".", ","))
        for record in final_code_audit
    )
    logger.info(
        "AUDITORIA_CODIGOS sospechosos_iniciales=%s corregidos_alta=%s "
        "pendientes_media=%s pendientes_baja=%s incompletos_resueltos=%s "
        "incompletos_pendientes=%s residuales_8_B=%s residuales_0_C=%s "
        "residuales_4_A=%s",
        len(initial_code_audit),
        high_codes,
        medium_codes,
        low_codes,
        incomplete_initial - incomplete_pending,
        incomplete_pending,
        sum("8_B" in record.reason for record in final_code_audit),
        sum("0_C" in record.reason for record in final_code_audit),
        sum("4_A" in record.reason for record in final_code_audit),
    )

    # Recalcular listas por página tras reclasificaciones.
    page_rows = {
        page: [row for row in all_rows if row.pagina == page]
        for page in page_bands
    }
    controls = [
        reconcile_page(source_name, page, page_rows[page], page_bands[page])
        for page in sorted(page_rows)
    ]
    for control in controls:
        rows_for_page = page_rows[control.pagina]
        control.partidas_antes_recuperacion = sum(
            row.tipo_fila == "partida" and not row.fila_recuperada
            for row in rows_for_page
        )
    structural = [
        row
        for row in all_rows
        if row.tipo_fila in ("categoria", "grupo", "subgrupo", "partida")
    ]
    unclassified = [
        row for row in all_rows if row.tipo_fila == "fila_no_clasificada"
    ]
    leaf_sum = sum(
        (
            row.parcial_soles
            for row in structural
            if row.tipo_fila == "partida" and row.parcial_soles is not None
        ),
        Decimal("0"),
    )
    validations = validate_economic_summary(summary, leaf_sum)
    logger.info(
        "CONCILIACION_DOCUMENTO detectadas=%s estructurales=%s continuaciones=%s "
        "no_clasificadas=%s ruido=%s descartadas=0",
        sum(control.filas_detectadas_en_tabla for control in controls),
        sum(control.filas_estructurales_exportadas for control in controls),
        sum(control.continuaciones_absorbidas for control in controls),
        sum(control.filas_no_clasificadas for control in controls),
        sum(control.ruido_documental for control in controls),
    )
    return DocumentResult(
        general=general,
        summary=summary,
        rows=structural,
        unclassified=unclassified,
        controls=controls,
        validations=validations,
        processed_at=processed_at,
        nodes_v6=nodes_v6,
        corrections_v6=corrections,
        total_pdf_pages=len(widths),
        searchable_pdf=str(searchable_pdf),
        code_reviews=code_reviews,
    )


def process_processed_pdf(
    pdf_path: Path,
    logger: logging.Logger,
    approved_code_review: Optional[Path] = None,
    approved_numeric_review: Optional[Path] = None,
) -> DocumentResult:
    return _process_searchable_pdf(
        pdf_path,
        pdf_path.name,
        logger,
        approved_code_review,
        approved_numeric_review,
    )


def process_source_pdf(
    pdf_path: Path,
    logger: logging.Logger,
    processed_dir: Optional[Path] = None,
    approved_code_review: Optional[Path] = None,
    approved_numeric_review: Optional[Path] = None,
) -> DocumentResult:
    searchable = prepare_searchable_pdf(pdf_path, logger, processed_dir)
    return _process_searchable_pdf(
        searchable,
        pdf_path.name,
        logger,
        approved_code_review,
        approved_numeric_review,
    )


def _detail_row(row: ExtractedRow, processed_at: datetime) -> List[object]:
    return [
        row.archivo_origen,
        row.pagina,
        row.orden_documento,
        row.orden_pagina,
        row.posicion_y,
        row.tipo_fila,
        row.nivel_jerarquia,
        row.codigo_original,
        row.codigo_normalizado,
        row.codigo_padre,
        row.categoria_codigo,
        row.categoria,
        row.grupo_codigo,
        row.grupo,
        row.subgrupo_codigo,
        row.subgrupo,
        row.item,
        row.descripcion,
        row.und_ocr,
        row.und,
        row.metrado_ocr,
        row.metrado,
        row.precio_ocr,
        row.precio_soles,
        row.parcial_ocr,
        row.parcial_soles,
        row.total_agrupador_soles,
        row.texto_fila_ocr,
        row.regla_normalizacion,
        row.estado_revision,
        row.motivo_revision,
        processed_at,
    ]


def _public_review_reason(row: ExtractedRow) -> str:
    """Oculta detalles geométricos sin ocultar la necesidad de revisión."""
    visible: List[str] = []
    hidden_prefixes = (
        "Token ",
        "Encabezado de columnas no detectado",
        "se reutilizaron bandas",
    )
    for reason in (row.motivo_revision or "").split("; "):
        if reason and not reason.startswith(hidden_prefixes):
            visible.append(reason)
    if row.estado_revision == "REVISAR" and not visible:
        visible.append("Revisar extracción OCR")
    return "; ".join(visible)


def _partida_v4_row(
    row: ExtractedRow, general: GeneralData
) -> List[object]:
    return [
        row.archivo_origen,
        row.pagina,
        general.lugar,
        general.cliente,
        general.fecha_costo,
        general.codigo_presupuesto,
        general.codigo_subpresupuesto,
        row.categoria_codigo,
        row.categoria,
        row.grupo_codigo,
        row.grupo,
        row.subgrupo_codigo,
        row.subgrupo,
        row.codigo_original,
        row.item,
        row.descripcion,
        row.und_ocr,
        row.und,
        row.metrado,
        row.precio_soles,
        row.parcial_soles,
        row.estado_revision,
        _public_review_reason(row),
    ]


def _structure_v4_row(row: ExtractedRow) -> List[object]:
    return [
        row.archivo_origen,
        row.orden_documento,
        row.pagina,
        row.tipo_fila,
        row.codigo_original,
        row.item,
        row.descripcion,
        row.codigo_padre,
        row.total_agrupador_soles,
        row.estado_revision,
        _public_review_reason(row),
    ]


def _candidate_from_reason(reason: str) -> str:
    matches = re.findall(r"candidato:\s*([^;]+)", reason or "", re.IGNORECASE)
    return ", ".join(dict.fromkeys(match.strip() for match in matches))


def build_revision_incidents(result: DocumentResult) -> List[RevisionIncident]:
    incidents: List[RevisionIncident] = []
    all_structural = result.rows

    for row in all_structural:
        reason = row.motivo_revision or ""
        rule = row.regla_normalizacion or ""
        unit_incident_details = {
            "unidad_normalizada": (
                "Normalización inequívoca incluida en el catálogo",
                "Unidad normalizada de forma segura",
            ),
            "unidad_no_catalogada": (
                "Geometría inequívoca de la banda de unidad; valor provisional",
                "La unidad no figura en el catálogo y requiere validación",
            ),
            "posible_confusion_gb_glb": (
                "Conservar gb; no sustituir por glb sin evidencia",
                "Posible confusión OCR entre gb y glb",
            ),
            "unidad_reconstruida_desde_varios_tokens": (
                "Tokens contiguos de la misma línea forman una unidad catalogada",
                "Unidad reconstruida conservando el OCR original",
            ),
            "unidad_recuperada_desde_descripcion": (
                "Coordenadas originales pertenecen a la banda de unidad",
                "Unidad retirada del final visual de la descripción",
            ),
        }
        for incident_type in row.unit_incident_types:
            applied, motive = unit_incident_details[incident_type]
            incidents.append(
                RevisionIncident(
                    archivo_origen=row.archivo_origen,
                    pagina=row.pagina,
                    tipo_incidencia=incident_type,
                    texto_fila_ocr=row.texto_fila_ocr,
                    campo="und",
                    valor_original=row.und_ocr,
                    valor_propuesto=row.und,
                    regla_aplicada=applied,
                    motivo_revision=motive,
                )
            )
        if "Ambigüedad A/4" in reason or "Ambigüedad B/8" in reason:
            incidents.append(
                RevisionIncident(
                    archivo_origen=row.archivo_origen,
                    pagina=row.pagina,
                    tipo_incidencia="codigo_ambiguo",
                    texto_fila_ocr=row.texto_fila_ocr,
                    campo="item",
                    valor_original=row.codigo_original,
                    valor_propuesto=_candidate_from_reason(reason),
                    regla_aplicada="No corregir A/4 ni B/8 sin evidencia inequívoca",
                    motivo_revision=reason,
                )
            )
        if (
            row.codigo_original
            and row.codigo_normalizado
            and row.codigo_original != row.codigo_normalizado
            and ("Coma en banda de ítem" in rule or "punto" in rule.lower())
        ):
            incidents.append(
                RevisionIncident(
                    archivo_origen=row.archivo_origen,
                    pagina=row.pagina,
                    tipo_incidencia="normalizacion_codigo",
                    texto_fila_ocr=row.texto_fila_ocr,
                    campo="item",
                    valor_original=row.codigo_original,
                    valor_propuesto=row.codigo_normalizado,
                    regla_aplicada=rule,
                    motivo_revision="Validar separador del código",
                )
            )
        if "Decimal recuperado" in rule or "Decimal perdido" in reason:
            incidents.append(
                RevisionIncident(
                    archivo_origen=row.archivo_origen,
                    pagina=row.pagina,
                    tipo_incidencia="decimal_posiblemente_perdido",
                    texto_fila_ocr=row.texto_fila_ocr,
                    campo="metrado",
                    valor_original=row.metrado_ocr,
                    valor_propuesto="" if row.metrado is None else str(row.metrado),
                    regla_aplicada=rule,
                    motivo_revision=reason or "Validar decimal recuperado",
                )
            )
        if row.und_ocr and not row.und:
            incidents.append(
                RevisionIncident(
                    archivo_origen=row.archivo_origen,
                    pagina=row.pagina,
                    tipo_incidencia="unidad_no_reconocida",
                    texto_fila_ocr=row.texto_fila_ocr,
                    campo="und",
                    valor_original=row.und_ocr,
                    valor_propuesto="",
                    regla_aplicada="Texto reasignado a descripción",
                    motivo_revision="Unidad no incluida en la lista válida",
                )
            )
        if any(
            marker in reason
            for marker in (
                "Dos valores numéricos",
                "no se fusiona",
                "separadores consecutivos",
                "caracteres no numéricos",
            )
        ):
            incidents.append(
                RevisionIncident(
                    archivo_origen=row.archivo_origen,
                    pagina=row.pagina,
                    tipo_incidencia="valor_numerico_ambiguo",
                    texto_fila_ocr=row.texto_fila_ocr,
                    campo="metrado/precio/parcial",
                    valor_original=" | ".join(
                        value
                        for value in (
                            row.metrado_ocr,
                            row.precio_ocr,
                            row.parcial_ocr,
                        )
                        if value
                    ),
                    valor_propuesto="",
                    regla_aplicada="No fusionar ni completar automáticamente",
                    motivo_revision=reason,
                )
            )
        if (
            row.tipo_fila == "partida"
            and row.posicion_y >= 650
            and any(
                value is None
                for value in (row.metrado, row.precio_soles, row.parcial_soles)
            )
        ):
            incidents.append(
                RevisionIncident(
                    archivo_origen=row.archivo_origen,
                    pagina=row.pagina,
                    tipo_incidencia="fila_final_pagina_incompleta",
                    texto_fila_ocr=row.texto_fila_ocr,
                    campo="metrado/precio/parcial",
                    valor_original=" | ".join(
                        value
                        for value in (
                            row.metrado_ocr,
                            row.precio_ocr,
                            row.parcial_ocr,
                        )
                        if value
                    ),
                    valor_propuesto="",
                    regla_aplicada="Conservar valores OCR sin completar",
                    motivo_revision=reason,
                )
            )

    for row in result.unclassified:
        incidents.append(
            RevisionIncident(
                archivo_origen=row.archivo_origen,
                pagina=row.pagina,
                tipo_incidencia="fila_no_clasificada",
                texto_fila_ocr=row.texto_fila_ocr,
                campo="fila",
                valor_original=row.texto_fila_ocr,
                valor_propuesto="",
                regla_aplicada="Conservar para revisión manual",
                motivo_revision=(
                    row.motivo_no_clasificacion
                    or "Línea de tabla sin clasificación estructural"
                ),
            )
        )
    return incidents


def _revision_v4_row(incident: RevisionIncident) -> List[object]:
    return [
        incident.archivo_origen,
        incident.pagina,
        incident.tipo_incidencia,
        incident.texto_fila_ocr,
        incident.campo,
        incident.valor_original,
        incident.valor_propuesto,
        incident.regla_aplicada,
        incident.motivo_revision,
    ]


def _unclassified_row(row: ExtractedRow, processed_at: datetime) -> List[object]:
    return [
        row.archivo_origen,
        row.pagina,
        row.orden_pagina,
        row.posicion_y,
        row.texto_fila_ocr,
        row.tokens_detectados,
        row.posible_item or row.codigo_original,
        row.posible_descripcion or row.descripcion,
        row.posible_und or row.und_ocr,
        row.posible_metrado or row.metrado_ocr,
        row.posible_precio or row.precio_ocr,
        row.posible_parcial or row.parcial_ocr,
        row.motivo_no_clasificacion or row.motivo_revision,
        processed_at,
    ]


def _control_row(control: PageControl) -> List[object]:
    return [
        control.archivo_origen,
        control.pagina,
        control.filas_detectadas_en_tabla,
        control.categorias,
        control.grupos,
        control.subgrupos,
        control.partidas,
        control.continuaciones_absorbidas,
        control.filas_no_clasificadas,
        control.filas_exportadas,
        control.estado_control,
        control.motivo_control,
        control.filas_estructurales_exportadas,
        control.continuaciones_absorbidas,
        control.ruido_documental,
        control.filas_descartadas,
        control.item_x_inicio,
        control.descripcion_x_inicio,
        control.und_x_inicio,
        control.metrado_x_inicio,
        control.precio_x_inicio,
        control.parcial_x_inicio,
        control.metodo_deteccion_bandas,
    ]


def _summary_row(
    filename: str, result: DocumentResult
) -> List[object]:
    summary = result.summary
    review = [
        validation for validation in result.validations if "REVISAR" in validation
    ]
    return [
        filename,
        result.general.lugar,
        result.general.cliente,
        result.general.fecha_costo,
        result.general.codigo_presupuesto,
        result.general.codigo_subpresupuesto,
        summary.costo_directo_soles,
        summary.gastos_generales_porcentaje,
        summary.gastos_generales_soles,
        summary.utilidad_porcentaje,
        summary.utilidad_soles,
        summary.subtotal_soles,
        summary.igv_porcentaje,
        summary.igv_soles,
        summary.presupuesto_total_soles,
        summary.monto_en_letras,
        "REVISAR" if review else "OK",
        "; ".join(review),
        result.processed_at,
    ]


def _review_candidates(row: ExtractedRow) -> List[str]:
    text = "%s; %s" % (row.motivo_revision or "", row.nota or "")
    match = re.search(r"candidatos?\s*:\s*([^;]+)", text, re.IGNORECASE)
    if not match:
        return []
    return [
        value.strip()
        for value in re.split(r"[,|/]", match.group(1))
        if value.strip()
    ][:2]


def _automatic_numeric_correction(
    row: ExtractedRow,
) -> Optional[Tuple[str, object, object]]:
    fields = (
        ("metrado", row.metrado_ocr, row.metrado),
        ("precio_soles", row.precio_ocr, row.precio_soles),
        ("parcial_soles", row.parcial_ocr, row.parcial_soles),
    )
    for field_name, raw, final_value in fields:
        if not raw or final_value is None:
            continue
        parsed = parse_ocr_number(raw)
        if parsed.value is not None and parsed.value != final_value:
            return field_name, raw, final_value
    return None


def build_partida_presentation(row: ExtractedRow) -> PartidaPresentation:
    human = row.human_numeric_corrections.get("parcial_soles")
    if human is not None:
        return PartidaPresentation(
            general_state="CORREGIDO",
            severity=human.severity or "INFORMATIVA",
            observed_field="parcial_soles",
            original_value=human.original_value,
            corrected_or_suggested=human.corrected_value,
            reason=human.note,
            required_action=human.action_required,
            review_state="APROBADO",
            approved_value=human.corrected_value,
            reviewer_comment=human.reviewer_reference,
        )

    required = (
        ("descripcion", row.descripcion),
        ("und", row.und),
        ("metrado", row.metrado),
        ("precio_soles", row.precio_soles),
        ("parcial_soles", row.parcial_soles),
    )
    missing = [name for name, value in required if value in (None, "")]
    if missing:
        return PartidaPresentation(
            general_state="REVISAR",
            severity="CRÍTICA",
            observed_field=", ".join(missing),
            original_value="",
            reason="Faltan campos obligatorios: %s" % ", ".join(missing),
            required_action="Completar o confirmar el valor",
            review_state="PENDIENTE",
        )

    if row.metrado is not None and row.precio_soles is not None:
        calculated = _decimal_2(row.metrado * row.precio_soles)
        if row.parcial_soles is not None and not within_tolerance(
            row.parcial_soles, calculated, Decimal("1")
        ):
            return PartidaPresentation(
                general_state="REVISAR",
                severity="CRÍTICA",
                observed_field="parcial_soles",
                original_value=row.parcial_ocr or row.parcial_soles,
                corrected_or_suggested=calculated,
                reason=(
                    "El parcial no coincide con metrado por precio: "
                    "metrado=%s; precio=%s; parcial=%s; diferencia=%s"
                    % (
                        row.metrado,
                        row.precio_soles,
                        row.parcial_soles,
                        row.parcial_soles - calculated,
                    )
                ),
                required_action="Validar el parcial contra el PDF",
                review_state="PENDIENTE",
            )

    if row.codigo_pendiente or not row.item:
        candidates = _review_candidates(row)
        return PartidaPresentation(
            general_state="REVISAR",
            severity="MEDIA",
            observed_field="item",
            original_value=row.codigo_original,
            corrected_or_suggested=" / ".join(candidates),
            reason=_public_review_reason(row) or "Código pendiente de validación",
            required_action="Confirmar código en el documento",
            review_state="PENDIENTE",
        )

    confidence = (row.confianza or "").upper()
    if confidence in ("MEDIA", "BAJA"):
        return PartidaPresentation(
            general_state="REVISAR",
            severity=confidence,
            observed_field="item",
            original_value=row.codigo_original,
            corrected_or_suggested=row.item,
            reason=_public_review_reason(row) or "Corrección con confianza insuficiente",
            required_action="Confirmar el valor contra el PDF",
            review_state="PENDIENTE",
        )

    if row.estado_revision == "REVISAR":
        return PartidaPresentation(
            general_state="REVISAR",
            severity="MEDIA",
            observed_field="fila",
            original_value=row.texto_fila_ocr,
            reason=_public_review_reason(row),
            required_action="Validar la fila contra el PDF",
            review_state="PENDIENTE",
        )

    if row.codigo_original and row.item and row.codigo_original != row.item:
        return PartidaPresentation(
            general_state="CORREGIDO",
            severity="INFORMATIVA",
            observed_field="item",
            original_value=row.codigo_original,
            corrected_or_suggested=row.item,
            reason=row.metodo_correccion or row.regla_normalizacion,
            required_action="Ninguna, corrección validada",
        )

    numeric = _automatic_numeric_correction(row)
    if numeric is not None:
        return PartidaPresentation(
            general_state="CORREGIDO",
            severity="INFORMATIVA",
            observed_field=numeric[0],
            original_value=numeric[1],
            corrected_or_suggested=numeric[2],
            reason=row.regla_normalizacion,
            required_action="Ninguna, corrección validada",
        )

    if row.und_ocr and row.und and row.und_ocr != row.und:
        return PartidaPresentation(
            general_state="CORREGIDO",
            severity="INFORMATIVA",
            observed_field="und",
            original_value=row.und_ocr,
            corrected_or_suggested=row.und,
            reason=row.regla_normalizacion,
            required_action="Ninguna, normalización segura",
        )
    return PartidaPresentation(general_state="VALIDADO")


def _client_review_row(record: ClientReviewRecord) -> List[object]:
    return [
        record.review_id,
        record.page,
        record.order,
        record.row_type,
        record.item_ocr,
        record.corrected_item,
        record.description,
        record.observed_field,
        record.original_value,
        record.candidate_1,
        record.candidate_2,
        record.suggested_value,
        record.reason,
        record.severity,
        record.confidence,
        record.required_action,
        record.approved_value,
        record.review_state,
        record.reviewer_comment,
    ]


def build_client_review_records(
    filename: str, result: DocumentResult
) -> List[ClientReviewRecord]:
    records: List[ClientReviewRecord] = []
    covered: set = set()
    for review in result.code_reviews:
        if (review.review_status or "PENDIENTE").upper() != "PENDIENTE":
            continue
        severity = "ALTA" if review.row_type != "partida" else "MEDIA"
        records.append(
            ClientReviewRecord(
                review_id=review.review_id,
                page=review.page,
                order=review.order,
                row_type=review.row_type,
                item_ocr=review.item_ocr,
                corrected_item="",
                description=review.description,
                observed_field="item",
                original_value=review.item_ocr,
                candidate_1=review.candidate_1,
                candidate_2=review.candidate_2,
                suggested_value=(
                    review.candidate_1
                    if review.candidate_1 and not review.candidate_2
                    else ""
                ),
                reason=review.evidence or "Código ambiguo",
                severity=severity,
                confidence=review.automatic_confidence,
                required_action="Confirmar el código contra el PDF",
                approved_value="",
                review_state="PENDIENTE",
                reviewer_comment="",
            )
        )
        covered.add((review.page, review.order, "item"))

    for row in result.rows:
        if row.tipo_fila != "partida":
            continue
        presentation = build_partida_presentation(row)
        if presentation.general_state != "REVISAR":
            continue
        key = (row.pagina, row.orden_documento, presentation.observed_field)
        if key in covered or (
            presentation.observed_field == "item"
            and (row.pagina, row.orden_documento, "item") in covered
        ):
            continue
        candidates = _review_candidates(row)
        records.append(
            ClientReviewRecord(
                review_id="%s-P%s-O%s-%s"
                % (filename, row.pagina, row.orden_documento, presentation.observed_field),
                page=row.pagina,
                order=row.orden_documento,
                row_type="partida",
                item_ocr=row.codigo_original,
                corrected_item=row.item,
                description=row.descripcion,
                observed_field=presentation.observed_field,
                original_value=presentation.original_value,
                candidate_1=candidates[0] if candidates else "",
                candidate_2=candidates[1] if len(candidates) > 1 else "",
                suggested_value=presentation.corrected_or_suggested,
                reason=presentation.reason,
                severity=presentation.severity,
                confidence=row.confianza,
                required_action=presentation.required_action,
            )
        )

    for row in result.unclassified:
        records.append(
            ClientReviewRecord(
                review_id="%s-P%s-O%s-fila" % (
                    filename,
                    row.pagina,
                    row.orden_documento,
                ),
                page=row.pagina,
                order=row.orden_documento,
                row_type="fila_no_clasificada",
                item_ocr=row.posible_item or row.codigo_original,
                corrected_item="",
                description=row.posible_descripcion or row.descripcion,
                observed_field="fila",
                original_value=row.texto_fila_ocr,
                candidate_1=row.posible_item,
                candidate_2="",
                suggested_value="",
                reason=(
                    row.motivo_no_clasificacion
                    or "Línea de tabla sin clasificación estructural"
                ),
                severity=(
                    "CRÍTICA"
                    if any((row.posible_metrado, row.posible_precio, row.posible_parcial))
                    else "MEDIA"
                ),
                confidence="BAJA",
                required_action="Clasificar la fila contra el PDF",
            )
        )
    records.sort(key=lambda value: (value.page, value.order, value.review_id))
    return records


def client_review_duplicate_key(
    record: ClientReviewRecord,
) -> Tuple[object, ...]:
    return (
        record.page,
        record.order,
        record.row_type,
        record.observed_field,
        str(record.original_value),
        record.reason,
    )


def audit_client_review_records(
    records: Sequence[ClientReviewRecord],
) -> Dict[str, object]:
    key_counts: Dict[Tuple[object, ...], int] = {}
    entities: Set[Tuple[int, int, str]] = set()
    for record in records:
        key = client_review_duplicate_key(record)
        key_counts[key] = key_counts.get(key, 0) + 1
        entities.add((record.page, record.order, record.row_type))
    return {
        "registros_totales": len(records),
        "partidas_unicas": sum(value[2] == "partida" for value in entities),
        "nodos_estructurales_unicos": sum(
            value[2] not in ("partida", "fila_no_clasificada")
            for value in entities
        ),
        "duplicados": {
            key: count for key, count in key_counts.items() if count > 1
        },
    }


def _trace_field_name(field_name: str) -> str:
    return {
        "item": "codigo",
        "código": "codigo",
        "codigo": "codigo",
        "unidad": "unidad",
        "und": "unidad",
        "metrado": "metrado",
        "precio": "precio",
        "precio_soles": "precio",
        "parcial": "parcial",
        "parcial_soles": "parcial",
    }.get(field_name, "")


def _correction_matches_row(
    correction: CorrectionRecord, row: ExtractedRow
) -> bool:
    if correction.pagina != row.pagina:
        return False
    if normalize_description_key(correction.descripcion) != normalize_description_key(
        row.descripcion
    ):
        return False
    identifiers = {value for value in (row.codigo_original, row.item) if value}
    values = {
        str(value)
        for value in (
            correction.referencia,
            correction.original,
            correction.corrected,
            correction.applied,
        )
        if value not in (None, "")
    }
    return not identifiers or bool(identifiers.intersection(values))


def build_field_correction_traces(
    row: ExtractedRow,
    corrections: Sequence[CorrectionRecord] = (),
) -> Dict[str, List[Dict[str, object]]]:
    traces: Dict[str, List[Dict[str, object]]] = {}

    def add(
        field_name: str,
        original: object,
        corrected: object,
        method: str,
        confidence: str,
        reason: str,
    ) -> None:
        field = _trace_field_name(field_name)
        if not field or not method:
            return
        entry = {
            "original": original,
            "corregido": corrected,
            "metodo": method,
            "confianza": confidence,
            "motivo": reason,
        }
        values = traces.setdefault(field, [])
        if entry not in values:
            values.append(entry)

    for correction in corrections:
        if _correction_matches_row(correction, row):
            add(
                correction.campo,
                correction.original,
                correction.corrected,
                correction.method,
                correction.confidence,
                correction.reason,
            )
    for field_name, correction in row.human_numeric_corrections.items():
        add(
            field_name,
            correction.original_value,
            correction.corrected_value,
            correction.method,
            correction.confidence,
            correction.note,
        )
    if (
        "codigo" not in traces
        and row.codigo_original
        and row.item
        and row.codigo_original != row.item
    ):
        add(
            "item",
            row.codigo_original,
            row.item,
            row.metodo_correccion,
            row.confianza,
            row.regla_normalizacion,
        )
    if (
        "unidad" not in traces
        and row.und_ocr
        and row.und
        and row.und_ocr != row.und
    ):
        add(
            "und",
            row.und_ocr,
            row.und,
            "Normalización de unidad inequívoca",
            "ALTA",
            row.regla_normalizacion,
        )
    numeric = _automatic_numeric_correction(row)
    if numeric is not None and _trace_field_name(numeric[0]) not in traces:
        add(
            numeric[0],
            numeric[1],
            numeric[2],
            row.metodo_correccion or row.regla_normalizacion,
            row.confianza,
            row.nota or row.regla_normalizacion,
        )
    return traces


def _trace_methods(
    traces: Dict[str, List[Dict[str, object]]], field_name: str
) -> str:
    return "; ".join(
        dict.fromkeys(
            str(value.get("metodo") or "")
            for value in traces.get(field_name, [])
            if value.get("metodo")
        )
    )


def _trace_confidences(
    traces: Dict[str, List[Dict[str, object]]], field_name: str
) -> str:
    return "; ".join(
        dict.fromkeys(
            str(value.get("confianza") or "")
            for value in traces.get(field_name, [])
            if value.get("confianza")
        )
    )


def _partida_v6_row(
    order: int,
    row: ExtractedRow,
    corrections: Sequence[CorrectionRecord] = (),
) -> List[object]:
    calculated: Optional[Decimal] = None
    difference: Optional[Decimal] = None
    state = "REVISAR"
    if row.metrado is not None and row.precio_soles is not None:
        calculated = _decimal_2(row.metrado * row.precio_soles)
    if row.parcial_soles is not None and calculated is not None:
        difference = row.parcial_soles - calculated
        if within_tolerance(
            row.parcial_soles,
            calculated,
            Decimal("1"),
        ) and not row.codigo_pendiente:
            state = "OK"
    human_correction = row.human_numeric_corrections.get("parcial_soles")
    if state == "OK" and human_correction is not None:
        state = "CORREGIDO"
    presentation = build_partida_presentation(row)
    traces = build_field_correction_traces(row, corrections)
    return [
        order,
        row.pagina,
        row.item,
        row.descripcion,
        row.und,
        row.metrado,
        row.precio_soles,
        row.parcial_soles,
        presentation.general_state,
        presentation.severity,
        presentation.observed_field,
        presentation.original_value,
        presentation.corrected_or_suggested,
        presentation.reason,
        presentation.required_action,
        presentation.review_state,
        presentation.approved_value,
        presentation.reviewer_comment,
        row.ruta_jerarquica,
        row.capitulo_codigo,
        row.capitulo,
        row.subcapitulo_codigo,
        row.subcapitulo,
        row.seccion_codigo,
        row.seccion,
        row.subseccion_codigo,
        row.subseccion,
        calculated,
        difference,
        state,
        row.codigo_original,
        row.und_ocr,
        row.metodo_correccion,
        row.confianza,
        row.nota,
        (
            human_correction.original_value
            if human_correction is not None
            else row.parcial_ocr_decimal
        ),
        (
            human_correction.corrected_value
            if human_correction is not None
            else None
        ),
        row.parcial_soles,
        _trace_methods(traces, "codigo"),
        _trace_confidences(traces, "codigo"),
        _trace_methods(traces, "unidad"),
        _trace_confidences(traces, "unidad"),
        _trace_methods(traces, "metrado"),
        _trace_confidences(traces, "metrado"),
        _trace_methods(traces, "precio"),
        _trace_confidences(traces, "precio"),
        _trace_methods(traces, "parcial"),
        _trace_confidences(traces, "parcial"),
        json.dumps(traces, ensure_ascii=False, default=str),
    ]


def _structure_v6_row(node: HierarchyNode) -> List[object]:
    return [
        node.order_document,
        node.page,
        node.level,
        node.node_id,
        node.code_ocr,
        node.code,
        node.title,
        node.parent_id,
        node.path,
        node.total_ocr,
        node.total,
        node.difference,
        node.correction,
        node.code_state,
        node.candidates,
    ]


def _correction_v6_row(record: CorrectionRecord) -> List[object]:
    return [
        record.tipo,
        record.pagina,
        record.referencia,
        record.descripcion,
        record.campo,
        record.original,
        record.corrected,
        record.method,
        record.confidence,
        record.confusion_type,
        record.evidence,
        record.score,
        record.margin,
        record.applied,
        record.reason,
        record.severity,
        record.action_required,
        record.reviewer_reference,
    ]


def collect_v6_corrections(result: DocumentResult) -> List[CorrectionRecord]:
    records = list(result.corrections_v6)
    for row in result.rows:
        if "Descripción multilínea absorbida" in row.regla_normalizacion:
            records.append(
                CorrectionRecord(
                    tipo="Descripción reconstruida",
                    pagina=row.pagina,
                    referencia=row.item,
                    descripcion=row.descripcion,
                    campo="descripcion",
                    original=row.texto_fila_ocr,
                    corrected=row.descripcion,
                    method="continuación en banda de descripción",
                    confidence="ALTA",
                )
            )
    for row in result.unclassified:
        records.append(
            CorrectionRecord(
                tipo="Caso no clasificado",
                pagina=row.pagina,
                referencia=row.posible_item,
                descripcion=row.posible_descripcion,
                campo="fila",
                original=row.texto_fila_ocr,
                corrected="",
                method="conservada para revisión; no descartada",
                confidence="BAJA",
            )
        )
    return records


def _control_v6_row(
    control: PageControl,
    rows: Sequence[ExtractedRow],
    nodes: Sequence[HierarchyNode],
) -> List[object]:
    page_rows = [row for row in rows if row.pagina == control.pagina]
    parts = [row for row in page_rows if row.tipo_fila == "partida"]
    recovered = sum(row.fila_recuperada for row in parts)
    page_sum = sum(
        (
            row.parcial_soles
            for row in parts
            if row.parcial_soles is not None
        ),
        Decimal("0"),
    )
    state = (
        "OK"
        if control.reconciled_total == control.filas_detectadas_en_tabla
        and control.filas_descartadas == 0
        else "REVISAR"
    )
    return [
        control.pagina,
        control.filas_detectadas_en_tabla,
        control.partidas_antes_recuperacion,
        len(parts),
        recovered,
        sum(node.page == control.pagina for node in nodes),
        control.continuaciones_absorbidas,
        control.ruido_documental,
        control.filas_no_clasificadas,
        control.filas_descartadas,
        page_sum,
        state,
    ]


def _write_summary_v6(
    sheet,
    filename: str,
    result: DocumentResult,
    corrections: Sequence[CorrectionRecord],
    client_reviews: Sequence[ClientReviewRecord],
) -> None:
    parts = [row for row in result.rows if row.tipo_fila == "partida"]
    leaf_sum = sum(
        (
            row.parcial_soles
            for row in parts
            if row.parcial_soles is not None
        ),
        Decimal("0"),
    )
    summary = result.summary
    project_name = next(
        (node.title for node in result.nodes_v6 if node.level == "proyecto"),
        "",
    )
    discarded = sum(control.filas_descartadas for control in result.controls)
    pending = sum(
        build_partida_presentation(row).general_state == "REVISAR"
        for row in parts
    ) + len(result.unclassified)
    corrected_codes = sum(
        record.tipo in ("Código de partida", "Estructura")
        and record.confidence.upper() == "ALTA"
        for record in corrections
    )
    recovered = sum(row.fila_recuperada for row in parts)
    numeric = sum(record.tipo == "Valor de partida" for record in corrections)
    human_numeric = [
        record
        for record in corrections
        if record.tipo == "Corrección numérica humana"
        and record.confidence == "ALTA"
    ]
    difference = (
        leaf_sum - summary.costo_directo_soles
        if summary.costo_directo_soles is not None
        else None
    )

    sheet.merge_cells("A1:H1")
    sheet["A1"] = "Presupuesto de obra - extracción v6"
    sheet.append([])
    sheet.append(["A. Datos generales", None, None, "B. Indicadores", None])
    general_rows = [
        ("Archivo fuente", filename),
        ("Código de presupuesto", result.general.codigo_presupuesto),
        ("Código de subpresupuesto", result.general.codigo_subpresupuesto),
        ("Nombre del presupuesto u obra", project_name),
        ("Cliente", result.general.cliente),
        ("Lugar", result.general.lugar),
        ("Fecha de costo", result.general.fecha_costo),
        ("Total de páginas del PDF", result.total_pdf_pages),
        ("Páginas que contienen presupuesto", len(result.controls)),
        (
            "Jerarquía utilizada",
            "Capítulo > Subcapítulo > Sección > Subsección > Partida",
        ),
    ]
    indicator_rows = [
        ("Partidas finales", len(parts)),
        ("Nodos jerárquicos detectados", len(result.nodes_v6)),
        ("Códigos corregidos", corrected_codes),
        ("Filas recuperadas", recovered),
        ("Correcciones numéricas", numeric),
        ("Correcciones humanas aprobadas", len(human_numeric)),
        ("Casos pendientes de revisión", pending),
        ("Filas no clasificadas", len(result.unclassified)),
        ("Filas descartadas silenciosamente", discarded),
    ]
    for index in range(max(len(general_rows), len(indicator_rows))):
        left = general_rows[index] if index < len(general_rows) else ("", "")
        right = (
            indicator_rows[index] if index < len(indicator_rows) else ("", "")
        )
        sheet.append([left[0], left[1], None, right[0], right[1]])

    sheet.append([])
    sheet.append(["C. Resumen económico", "Valor", None, "D. Validaciones", "Resultado"])
    economic = [
        ("costo_directo_soles", summary.costo_directo_soles),
        (
            "gastos_generales_porcentaje",
            summary.gastos_generales_porcentaje,
        ),
        ("gastos_generales_soles", summary.gastos_generales_soles),
        ("utilidad_porcentaje", summary.utilidad_porcentaje),
        ("utilidad_soles", summary.utilidad_soles),
        ("subtotal_soles", summary.subtotal_soles),
        ("igv_porcentaje", summary.igv_porcentaje),
        ("igv_soles", summary.igv_soles),
        ("presupuesto_total_soles", summary.presupuesto_total_soles),
        ("monto_en_letras", summary.monto_en_letras),
    ]
    validations = [
        ("Suma de parciales de partidas", leaf_sum),
        ("Costo directo del PDF", summary.costo_directo_soles),
        ("Diferencia entre suma y costo directo", difference),
    ] + [
        ("Validación %s" % (index + 1), message)
        for index, message in enumerate(result.validations)
    ]
    for index in range(max(len(economic), len(validations))):
        left = economic[index] if index < len(economic) else ("", "")
        right = validations[index] if index < len(validations) else ("", "")
        sheet.append([left[0], left[1], None, right[0], right[1]])
    general_ok = (
        difference is not None
        and within_tolerance(
            leaf_sum,
            summary.costo_directo_soles or Decimal("0"),
            Decimal("0.01"),
        )
        and all("REVISAR" not in message for message in result.validations)
        and discarded == 0
    )
    if general_ok and human_numeric:
        general_status = "CORREGIDO"
    else:
        general_status = "OK" if general_ok else "REVISAR"
    sheet.append([None, None, None, "Estado general", general_status])
    if human_numeric:
        motives = list(
            dict.fromkeys(record.reason for record in human_numeric if record.reason)
        )
        sheet.append(
            [
                None,
                None,
                None,
                "Severidad",
                HUMAN_NUMERIC_SEVERITY,
            ]
        )
        sheet.append([None, None, None, "Confianza", "ALTA"])
        sheet.append(
            [None, None, None, "Motivo", "; ".join(motives)]
        )
        sheet.append(
            [None, None, None, "Acción requerida", HUMAN_NUMERIC_ACTION]
        )

    presentations = [build_partida_presentation(row) for row in parts]
    validated = sum(value.general_state == "VALIDADO" for value in presentations)
    corrected = sum(value.general_state == "CORREGIDO" for value in presentations)
    needs_review = sum(value.general_state == "REVISAR" for value in presentations)
    critical = sum(value.severity == "CRÍTICA" for value in presentations)
    structural_pending = sum(
        node.code_state == "REVISAR" for node in result.nodes_v6
    )
    empty_required = sum(
        any(
            value in (None, "")
            for value in (
                row.descripcion,
                row.und,
                row.metrado,
                row.precio_soles,
                row.parcial_soles,
            )
        )
        for row in parts
    )
    economic_state = "CONCILIADO" if general_ok else "REVISAR"
    quality_state = (
        "REVISAR"
        if critical or needs_review or structural_pending or result.unclassified
        else ("CORREGIDO" if corrected else "VALIDADO")
    )
    sheet.append([])
    sheet.append(["E. Estado de calidad y revisión", "Valor"])
    quality_rows = [
        ("Total de partidas procesadas", len(parts)),
        ("Partidas validadas", validated),
        ("Partidas corregidas automáticamente", corrected),
        ("Partidas pendientes de revisión", needs_review),
        ("Incidencias críticas", critical),
        ("Códigos estructurales pendientes", structural_pending),
        ("Campos obligatorios vacíos", empty_required),
        ("Estado de conciliación económica", economic_state),
        ("Diferencia contra costo directo", difference),
        ("Estado general del documento", quality_state),
        ("Casos que requieren acción humana", len(client_reviews)),
    ]
    for label, value in quality_rows:
        sheet.append([label, value])
    sheet.append(["Ver casos pendientes", "Abrir hoja Revision"])
    sheet.cell(row=sheet.max_row, column=2).hyperlink = "#'Revision'!A1"
    sheet.cell(row=sheet.max_row, column=2).style = "Hyperlink"
    sheet.append([])
    sheet.append(["Leyenda", "Significado"])
    for label, meaning in (
        ("Rojo", "Error crítico, dato faltante o fuera de tolerancia"),
        ("Amarillo", "Ambigüedad o revisión humana pendiente"),
        ("Azul", "Valor corregido con confianza alta"),
        ("Verde", "Estado validado"),
        ("Gris", "Valor original reconocido por OCR"),
    ):
        sheet.append([label, meaning])


def _style_v6_workbook(workbook) -> None:
    from openpyxl.comments import Comment  # type: ignore
    from openpyxl.styles import Alignment, Font, PatternFill  # type: ignore
    from openpyxl.utils import get_column_letter  # type: ignore
    from openpyxl.worksheet.datavalidation import DataValidation  # type: ignore

    header_fill = PatternFill("solid", fgColor="1F4E78")
    red_fill = PatternFill("solid", fgColor="F4CCCC")
    yellow_fill = PatternFill("solid", fgColor="FFF2CC")
    blue_fill = PatternFill("solid", fgColor="DDEBF7")
    green_fill = PatternFill("solid", fgColor="E2F0D9")
    gray_fill = PatternFill("solid", fgColor="E7E6E6")
    header_font = Font(color="FFFFFF", bold=True)

    def indexes(sheet) -> Dict[str, int]:
        return {
            str(cell.value): cell.column
            for cell in sheet[1]
            if cell.value not in (None, "")
        }

    for sheet in workbook.worksheets:
        if sheet.title == "Resumen":
            sheet["A1"].font = Font(size=16, bold=True, color="FFFFFF")
            sheet["A1"].fill = header_fill
            sheet["A1"].alignment = Alignment(horizontal="center")
            for row_number in range(2, sheet.max_row + 1):
                first = str(sheet.cell(row=row_number, column=1).value or "")
                if re.match(r"^[A-Z]\. ", first) or first == "Leyenda":
                    for cell in sheet[row_number]:
                        if cell.value:
                            cell.font = Font(bold=True, color="FFFFFF")
                            cell.fill = header_fill
                label = first.lower()
                value_cell = sheet.cell(row=row_number, column=2)
                if label == "rojo":
                    value_cell.fill = red_fill
                elif label == "amarillo":
                    value_cell.fill = yellow_fill
                elif label == "azul":
                    value_cell.fill = blue_fill
                elif label == "verde":
                    value_cell.fill = green_fill
                elif label == "gris":
                    value_cell.fill = gray_fill
                if first == "Estado general del documento":
                    state = str(value_cell.value or "")
                    value_cell.fill = (
                        green_fill
                        if state == "VALIDADO"
                        else blue_fill if state == "CORREGIDO" else yellow_fill
                    )
            sheet.column_dimensions["A"].width = 36
            sheet.column_dimensions["B"].width = 70
            sheet.column_dimensions["C"].width = 3
            sheet.column_dimensions["D"].width = 42
            sheet.column_dimensions["E"].width = 35
            for row in sheet.iter_rows():
                for cell in row:
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
            continue
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True,
            )
        for column in range(1, sheet.max_column + 1):
            maximum = max(
                len(str(sheet.cell(row=row, column=column).value or ""))
                for row in range(1, min(sheet.max_row, 80) + 1)
            )
            sheet.column_dimensions[get_column_letter(column)].width = min(
                max(maximum + 2, 12),
                60,
            )
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

    partidas = workbook["Partidas"]
    part_cols = indexes(partidas)
    for header in (
        "Item corregido",
        "Capítulo código",
        "Subcapítulo código",
        "Sección código",
        "Subsección código",
        "Item OCR",
        "Unidad OCR",
    ):
        column = part_cols[header]
        for row_number in range(1, partidas.max_row + 1):
            partidas.cell(row=row_number, column=column).number_format = "@"
    for header in (
        "Metrado",
        "Precio S/",
        "Parcial S/",
        "Parcial calculado",
        "Diferencia",
        "Parcial OCR S/",
        "Parcial corregido S/",
        "Parcial utilizado S/",
    ):
        column = part_cols[header]
        for row_number in range(2, partidas.max_row + 1):
            partidas.cell(row=row_number, column=column).number_format = '#,##0.00'

    field_headers = {
        "item": "Item corregido",
        "descripcion": "Descripción",
        "und": "Und",
        "metrado": "Metrado",
        "precio_soles": "Precio S/",
        "parcial_soles": "Parcial S/",
    }
    for row_number in range(2, partidas.max_row + 1):
        state_cell = partidas.cell(row=row_number, column=part_cols["Estado general"])
        severity = str(
            partidas.cell(row=row_number, column=part_cols["Severidad"]).value or ""
        ).upper()
        observed = str(
            partidas.cell(row=row_number, column=part_cols["Campo observado"]).value
            or ""
        )
        original_cell = partidas.cell(
            row=row_number, column=part_cols["Valor original OCR"]
        )
        proposed_cell = partidas.cell(
            row=row_number, column=part_cols["Valor corregido o sugerido"]
        )
        if original_cell.value not in (None, ""):
            original_cell.fill = gray_fill
            original_cell.font = Font(color="7F7F7F")
        state = str(state_cell.value or "")
        if state == "VALIDADO":
            state_cell.fill = green_fill
        elif state == "CORREGIDO":
            state_cell.fill = blue_fill
            if proposed_cell.value not in (None, ""):
                proposed_cell.fill = blue_fill
                proposed_cell.font = Font(color="1F4E78", bold=True)
        elif state == "REVISAR":
            alert_fill = red_fill if severity == "CRÍTICA" else yellow_fill
            state_cell.fill = alert_fill
            for field_name in [value.strip() for value in observed.split(",")]:
                header = field_headers.get(field_name)
                if header:
                    partidas.cell(
                        row=row_number, column=part_cols[header]
                    ).fill = alert_fill

        for header in ("Item OCR", "Unidad OCR", "Parcial OCR S/"):
            cell = partidas.cell(row=row_number, column=part_cols[header])
            if cell.value not in (None, ""):
                cell.fill = gray_fill
                cell.font = Font(color="7F7F7F")
        corrected_partial = partidas.cell(
            row=row_number, column=part_cols["Parcial corregido S/"]
        )
        used_partial = partidas.cell(
            row=row_number, column=part_cols["Parcial utilizado S/"]
        )
        if corrected_partial.value not in (None, ""):
            corrected_partial.fill = blue_fill
            corrected_partial.font = Font(color="1F4E78", bold=True)
            used_partial.fill = blue_fill
            used_partial.font = Font(color="1F4E78", bold=True)

        raw_traces = partidas.cell(
            row=row_number, column=part_cols["Trazabilidad por campo"]
        ).value
        try:
            traces = json.loads(str(raw_traces or "{}"))
        except ValueError:
            traces = {}
        trace_targets = {
            "codigo": partidas.cell(
                row=row_number, column=part_cols["Item corregido"]
            ),
            "unidad": partidas.cell(row=row_number, column=part_cols["Und"]),
            "metrado": partidas.cell(
                row=row_number, column=part_cols["Metrado"]
            ),
            "precio": partidas.cell(
                row=row_number, column=part_cols["Precio S/"]
            ),
            "parcial": (
                corrected_partial
                if corrected_partial.value not in (None, "")
                else partidas.cell(row=row_number, column=part_cols["Parcial S/"])
            ),
        }
        comments_by_field: Dict[str, str] = {}
        for field_name, entries in traces.items():
            if field_name not in trace_targets or not entries:
                continue
            blocks: List[str] = []
            for entry in entries:
                if field_name == "codigo":
                    block = (
                        "Código OCR: %s\nValor original OCR: %s\n"
                        "Código corregido: %s\nValor corregido: %s\n"
                        "Método de corrección del código: %s\nConfianza: %s\n"
                        "Motivo: %s\nPágina: %s"
                        % (
                            entry.get("original", ""),
                            entry.get("original", ""),
                            entry.get("corregido", ""),
                            entry.get("corregido", ""),
                            entry.get("metodo", ""),
                            entry.get("confianza", ""),
                            entry.get("motivo", ""),
                            partidas.cell(
                                row=row_number,
                                column=part_cols["Página PDF"],
                            ).value,
                        )
                    )
                else:
                    public_field = {
                        "unidad": "und",
                        "metrado": "metrado",
                        "precio": "precio_soles",
                        "parcial": "parcial_soles",
                    }[field_name]
                    block = (
                        "Valor original OCR: %s\nValor corregido: %s\n"
                        "Campo observado: %s\nMétodo: %s\nConfianza: %s\n"
                        "Motivo: %s\nPágina: %s\nDescripción: %s"
                        % (
                            entry.get("original", ""),
                            entry.get("corregido", ""),
                            public_field,
                            entry.get("metodo", ""),
                            entry.get("confianza", ""),
                            entry.get("motivo", ""),
                            partidas.cell(
                                row=row_number,
                                column=part_cols["Página PDF"],
                            ).value,
                            partidas.cell(
                                row=row_number,
                                column=part_cols["Descripción"],
                            ).value,
                        )
                    )
                blocks.append(block)
            comment_text = "\n\n---\n\n".join(blocks)
            comments_by_field[field_name] = comment_text
            trace_targets[field_name].comment = Comment(
                comment_text, "Extractor OCR"
            )

        observed_trace_field = _trace_field_name(observed)
        if observed_trace_field in comments_by_field:
            comment_cell = (
                proposed_cell
                if proposed_cell.value not in (None, "")
                else original_cell
            )
            comment_cell.comment = Comment(
                comments_by_field[observed_trace_field], "Extractor OCR"
            )
        elif observed:
            comment_cell = (
                proposed_cell
                if proposed_cell.value not in (None, "")
                else original_cell
            )
            comment_cell.comment = Comment(
                "Página: %s\nDescripción: %s\nCampo observado: %s\n"
                "Motivo: %s\nAcción requerida: %s"
                % (
                    partidas.cell(
                        row=row_number, column=part_cols["Página PDF"]
                    ).value,
                    partidas.cell(
                        row=row_number, column=part_cols["Descripción"]
                    ).value,
                    observed,
                    partidas.cell(row=row_number, column=part_cols["Motivo"]).value,
                    partidas.cell(
                        row=row_number, column=part_cols["Acción requerida"]
                    ).value,
                ),
                "Extractor OCR",
            )

    estructura = workbook["Estructura"]
    for column in ("D", "E", "F", "H"):
        for cell in estructura[column]:
            cell.number_format = "@"
    for column in ("J", "K", "L"):
        for cell in estructura[column][1:]:
            cell.number_format = '#,##0.00'
    control = workbook["Control"]
    for cell in control["K"][1:]:
        cell.number_format = '#,##0.00'

    revision = workbook["Revision"]
    revision_cols = indexes(revision)
    validation = DataValidation(
        type="list",
        formula1='"PENDIENTE,APROBADO,RECHAZADO"',
        allow_blank=False,
    )
    revision.add_data_validation(validation)
    status_letter = get_column_letter(revision_cols["Estado revisión"])
    validation.add("%s2:%s%s" % (
        status_letter,
        status_letter,
        max(revision.max_row + 100, 1000),
    ))
    for row_number in range(2, revision.max_row + 1):
        severity = str(
            revision.cell(row=row_number, column=revision_cols["Severidad"]).value
            or ""
        ).upper()
        fill = red_fill if severity == "CRÍTICA" else yellow_fill
        for header in ("Campo observado", "Valor original", "Severidad"):
            revision.cell(row=row_number, column=revision_cols[header]).fill = fill
        original = revision.cell(
            row=row_number, column=revision_cols["Valor original"]
        )
        original.font = Font(color="7F7F7F")
    legend_column = revision.max_column + 2
    revision.cell(row=1, column=legend_column, value="Leyenda")
    revision.cell(row=1, column=legend_column + 1, value="Significado")
    for cell in (
        revision.cell(row=1, column=legend_column),
        revision.cell(row=1, column=legend_column + 1),
    ):
        cell.fill = header_fill
        cell.font = header_font
    legend = (
        ("Rojo", "Error crítico, dato faltante o fuera de tolerancia", red_fill),
        ("Amarillo", "Ambigüedad o revisión humana pendiente", yellow_fill),
        ("Azul", "Valor corregido con confianza alta", blue_fill),
        ("Verde", "Estado validado", green_fill),
        ("Gris", "Valor original reconocido por OCR", gray_fill),
    )
    for offset, (label, meaning, fill) in enumerate(legend, 2):
        revision.cell(row=offset, column=legend_column, value=label).fill = fill
        revision.cell(row=offset, column=legend_column + 1, value=meaning)


def write_workbook_v6(
    output_path: Path,
    filename: str,
    result: DocumentResult,
    overwrite: bool = False,
) -> None:
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            "El resultado ya existe y no será sobrescrito: %s" % output_path
        )
    try:
        from openpyxl import Workbook  # type: ignore
    except ImportError as exc:
        raise RuntimeError("openpyxl no está disponible") from exc

    corrections = collect_v6_corrections(result)
    client_reviews = build_client_review_records(filename, result)
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Resumen"
    _write_summary_v6(
        summary, filename, result, corrections, client_reviews
    )

    parts_sheet = workbook.create_sheet("Partidas")
    parts_sheet.append(V6_PARTIDAS_COLUMNS)
    parts = [row for row in result.rows if row.tipo_fila == "partida"]
    for index, row in enumerate(parts, 1):
        parts_sheet.append(_partida_v6_row(index, row, corrections))

    structure = workbook.create_sheet("Estructura")
    structure.append(V6_ESTRUCTURA_COLUMNS)
    for node in result.nodes_v6:
        structure.append(_structure_v6_row(node))

    correction_sheet = workbook.create_sheet("Correcciones")
    correction_sheet.append(V6_CORRECCIONES_COLUMNS)
    for correction in corrections:
        correction_sheet.append(_correction_v6_row(correction))

    client_review_sheet = workbook.create_sheet("Revision")
    client_review_sheet.append(CLIENT_REVIEW_COLUMNS)
    for review in client_reviews:
        client_review_sheet.append(_client_review_row(review))

    review_sheet = workbook.create_sheet("Revision_codigos")
    review_sheet.append(CODE_REVIEW_COLUMNS)
    for review in result.code_reviews:
        review_sheet.append(_code_review_row(review))

    control_sheet = workbook.create_sheet("Control")
    control_sheet.append(V6_CONTROL_COLUMNS)
    for control in result.controls:
        control_sheet.append(
            _control_v6_row(control, result.rows, result.nodes_v6)
        )

    _style_v6_workbook(workbook)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=output_path.stem + "-",
            suffix=".xlsx",
            dir=str(output_path.parent),
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
        workbook.save(str(temp_path))
        temp_path.replace(output_path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def write_code_review_workbook(
    output_path: Path,
    reviews: Sequence[CodeReviewRecord],
) -> None:
    if output_path.exists():
        raise FileExistsError(
            "El archivo de revisión ya existe y no será sobrescrito: %s"
            % output_path
        )
    try:
        from openpyxl import Workbook  # type: ignore
        from openpyxl.styles import Font, PatternFill  # type: ignore
    except ImportError as exc:
        raise RuntimeError("openpyxl no está disponible") from exc
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Revision_codigos"
    sheet.append(CODE_REVIEW_COLUMNS)
    for review in reviews:
        sheet.append(_code_review_row(review))
    header_fill = PatternFill("solid", fgColor="1F4E78")
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(str(output_path))


def write_workbook(
    output_path: Path,
    filename: str,
    result: DocumentResult,
    overwrite: bool = False,
) -> None:
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            "El resultado ya existe y no será sobrescrito: %s" % output_path
        )
    try:
        from openpyxl import Workbook  # type: ignore
    except ImportError as exc:
        raise RuntimeError("openpyxl no está disponible") from exc

    workbook = Workbook()
    partidas = workbook.active
    partidas.title = "partidas"
    partidas.append(PARTIDAS_COLUMNS)
    for row in result.rows:
        if row.tipo_fila == "partida":
            partidas.append(_partida_v4_row(row, result.general))

    estructura = workbook.create_sheet("estructura")
    estructura.append(ESTRUCTURA_COLUMNS)
    for row in result.rows:
        if row.tipo_fila in ("categoria", "grupo", "subgrupo"):
            estructura.append(_structure_v4_row(row))

    revision = workbook.create_sheet("revision_ocr")
    revision.append(REVISION_OCR_COLUMNS)
    for incident in build_revision_incidents(result):
        revision.append(_revision_v4_row(incident))

    control = workbook.create_sheet("control_paginas")
    control.append(CONTROL_COLUMNS)
    for page_control in result.controls:
        control.append(_control_row(page_control))

    summary = workbook.create_sheet("resumen_presupuesto")
    summary.append(SUMMARY_COLUMNS)
    summary.append(_summary_row(filename, result))

    # Códigos e ítems siempre como texto en las hojas de usuario.
    for column in ("F", "G", "H", "J", "L", "N", "O", "Q", "R"):
        for cell in partidas[column]:
            cell.number_format = "@"
    for column in ("E", "F", "H"):
        for cell in estructura[column]:
            cell.number_format = "@"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=output_path.stem + "-",
            suffix=".xlsx",
            dir=str(output_path.parent),
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
        workbook.save(str(temp_path))
        temp_path.replace(output_path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _workbook_rows(path: Path, sheet_name: str) -> Tuple[List[str], List[Dict[str, object]]]:
    from openpyxl import load_workbook  # type: ignore

    workbook = load_workbook(str(path), read_only=True, data_only=True)
    sheet = workbook[sheet_name]
    values = list(sheet.iter_rows(values_only=True))
    if not values:
        return [], []
    headers = [str(value or "") for value in values[0]]
    return headers, [dict(zip(headers, row)) for row in values[1:]]


def _comparison_key(sheet: str, row: Dict[str, object]) -> str:
    if sheet == "Partidas":
        return "|".join(
            str(row.get(name) or "")
            for name in ("Página PDF", "Item OCR", "Descripción")
        )
    if sheet == "Estructura":
        return "|".join(
            str(row.get(name) or "")
            for name in ("Página PDF", "Código OCR", "Título")
        )
    if sheet == "Correcciones":
        return "|".join(
            str(row.get(name) or "")
            for name in (
                "Tipo",
                "Página PDF",
                "Campo",
                "Valor original/OCR",
                "Valor corregido",
            )
        )
    if sheet == "Control":
        return str(row.get("Página PDF") or "")
    return ""


def _comparison_match_cost(
    sheet: str,
    obtained: Dict[str, object],
    expected: Dict[str, object],
) -> float:
    page_column = "Página PDF"
    if str(obtained.get(page_column) or "") != str(
        expected.get(page_column) or ""
    ):
        return 10000.0
    if sheet == "Partidas":
        description_column = "Descripción"
        order_column = "Orden"
        ocr_column = "Item OCR"
    else:
        description_column = "Título"
        order_column = "Orden documento"
        ocr_column = "Código OCR"
    left_description = normalize_description_key(
        str(obtained.get(description_column) or "")
    )
    right_description = normalize_description_key(
        str(expected.get(description_column) or "")
    )
    similarity = difflib.SequenceMatcher(
        None,
        left_description,
        right_description,
    ).ratio()
    if similarity < 0.60:
        return 10000.0
    try:
        order_difference = abs(
            int(obtained.get(order_column) or 0)
            - int(expected.get(order_column) or 0)
        )
    except (TypeError, ValueError):
        order_difference = 0
    ocr_penalty = (
        0
        if normalize_description_key(str(obtained.get(ocr_column) or ""))
        == normalize_description_key(str(expected.get(ocr_column) or ""))
        else 4
    )
    return (1.0 - similarity) * 100.0 + min(order_difference, 20) + ocr_penalty


def _match_comparison_rows(
    sheet: str,
    obtained_rows: Sequence[Dict[str, object]],
    golden_rows: Sequence[Dict[str, object]],
) -> List[
    Tuple[str, Optional[Dict[str, object]], Optional[Dict[str, object]]]
]:
    if sheet not in ("Partidas", "Estructura"):
        obtained_map = {
            _comparison_key(sheet, row): row for row in obtained_rows
        }
        golden_map = {
            _comparison_key(sheet, row): row for row in golden_rows
        }
        return [
            (key, obtained_map.get(key), golden_map.get(key))
            for key in sorted(set(obtained_map) | set(golden_map))
        ]

    unmatched_expected = set(range(len(golden_rows)))
    matches: List[
        Tuple[str, Optional[Dict[str, object]], Optional[Dict[str, object]]]
    ] = []
    for obtained_index, obtained in enumerate(obtained_rows):
        ranked = sorted(
            (
                (
                    _comparison_match_cost(
                        sheet,
                        obtained,
                        golden_rows[expected_index],
                    ),
                    expected_index,
                )
                for expected_index in unmatched_expected
            ),
            key=lambda item: item[0],
        )
        if not ranked or ranked[0][0] >= 10000.0:
            key = "%s|obtenida|%s" % (
                _comparison_key(sheet, obtained),
                obtained_index,
            )
            matches.append((key, obtained, None))
            continue
        unused_cost, expected_index = ranked[0]
        unmatched_expected.remove(expected_index)
        expected = golden_rows[expected_index]
        key = "%s|%s" % (
            str(obtained.get("Página PDF") or ""),
            str(obtained.get("Orden") or obtained.get("Orden documento") or ""),
        )
        matches.append((key, obtained, expected))
    for expected_index in sorted(unmatched_expected):
        expected = golden_rows[expected_index]
        key = "%s|esperada|%s" % (
            _comparison_key(sheet, expected),
            expected_index,
        )
        matches.append((key, None, expected))
    return matches


def _values_equal(first: object, second: object) -> Tuple[bool, object]:
    if first in (None, "") and second in (None, ""):
        return True, Decimal("0")
    try:
        left = Decimal(str(first))
        right = Decimal(str(second))
    except (InvalidOperation, ValueError):
        return (
            normalize_description_key(str(first or ""))
            == normalize_description_key(str(second or "")),
            "",
        )
    difference = left - right
    return abs(difference) <= Decimal("0.01"), difference


def _difference_severity(
    sheet: str,
    column: str,
    difference: object,
) -> Tuple[str, str]:
    critical = {
        "Partidas": {
            "Página PDF",
            "Ruta jerárquica",
            "Capítulo código",
            "Subcapítulo código",
            "Sección código",
            "Subsección código",
            "Item corregido",
            "Descripción",
            "Und",
            "Metrado",
            "Precio S/",
            "Parcial S/",
            "Estado cálculo",
        },
        "Estructura": {
            "Nivel",
            "Nodo ID",
            "Código corregido",
            "Título",
            "Nodo padre",
            "Ruta jerárquica",
            "Total corregido S/",
        },
        "Control": {
            "Partidas finales",
            "Filas descartadas",
            "Suma parcial final S/",
        },
    }
    if column in ("Item OCR", "Unidad OCR", "Parcial OCR S/"):
        return (
            "NO CRÍTICA",
            "Se conserva el OCR original aunque el golden lo haya corregido",
        )
    monetary_columns = {
        "Metrado",
        "Precio S/",
        "Parcial S/",
        "Parcial corregido S/",
        "Parcial utilizado S/",
        "Parcial calculado",
        "Diferencia",
        "Total OCR S/",
        "Total corregido S/",
        "Diferencia S/",
        "Suma parcial final S/",
    }
    if column in monetary_columns:
        try:
            if abs(Decimal(str(difference))) <= Decimal("0.10"):
                return (
                    "NO CRÍTICA",
                    "Diferencia Decimal dentro de tolerancia",
                )
        except (InvalidOperation, ValueError):
            pass
    hierarchy_columns = {
        "Ruta jerárquica",
        "Capítulo código",
        "Capítulo",
        "Subcapítulo código",
        "Subcapítulo",
        "Sección código",
        "Sección",
        "Subsección código",
        "Subsección",
        "Nivel",
        "Nodo ID",
        "Nodo padre",
    }
    if column in hierarchy_columns:
        return "CRÍTICA", "Diferencia de jerarquía"
    if column in critical.get(sheet, set()):
        return "CRÍTICA", "Diferencia real de datos"
    if column in (
        "Método",
        "Método corrección",
        "Confianza",
        "Nota",
        "Severidad",
        "Motivo corrección",
        "Acción requerida",
        "Referencia revisión humana",
    ):
        return "NO CRÍTICA", "Diferencia de auditoría"
    return "NO CRÍTICA", "Diferencia visual o de columna auxiliar"


def compare_v6_workbooks(
    obtained_path: Path,
    golden_path: Path,
) -> List[WorkbookDifference]:
    """Comparador de desarrollo; nunca participa en la extracción."""
    differences: List[WorkbookDifference] = []
    from openpyxl import load_workbook  # type: ignore

    def summary_map(path: Path) -> Dict[str, object]:
        workbook = load_workbook(str(path), read_only=True, data_only=True)
        sheet = workbook["Resumen"]
        result: Dict[str, object] = {}
        for row in sheet.iter_rows(values_only=True):
            for label_index, value_index in ((0, 1), (3, 4)):
                if len(row) <= value_index:
                    continue
                label = row[label_index]
                value = row[value_index]
                if label not in (None, "") and value not in (None, ""):
                    result[normalize_description_key(str(label))] = value
        return result

    obtained_summary = summary_map(obtained_path)
    golden_summary = summary_map(golden_path)
    summary_aliases = {
        "COSTO DIRECTO": "COSTO DIRECTO SOLES",
        "PRESUPUESTO TOTAL": "PRESUPUESTO TOTAL SOLES",
        "SUMA DE PARTIDAS": "SUMA DE PARCIALES DE PARTIDAS",
        "DIFERENCIA FINAL": "DIFERENCIA ENTRE SUMA Y COSTO DIRECTO",
    }
    for golden_label, obtained_label in summary_aliases.items():
        expected = golden_summary.get(golden_label)
        obtained = obtained_summary.get(obtained_label)
        equal, numeric_difference = _values_equal(obtained, expected)
        if not equal:
            severity = "CRÍTICA"
            explanation = "Resumen económico o conciliación diferente"
            try:
                if abs(Decimal(str(numeric_difference))) <= Decimal("0.10"):
                    severity = "NO CRÍTICA"
                    explanation = "Diferencia Decimal dentro de tolerancia"
            except (InvalidOperation, ValueError):
                pass
            differences.append(
                WorkbookDifference(
                    sheet="Resumen",
                    key=golden_label,
                    column="valor",
                    obtained=obtained,
                    expected=expected,
                    difference=numeric_difference,
                    severity=severity,
                    explanation=explanation,
                )
            )
    for sheet in ("Partidas", "Estructura", "Correcciones", "Control"):
        obtained_headers, obtained_rows = _workbook_rows(obtained_path, sheet)
        golden_headers, golden_rows = _workbook_rows(golden_path, sheet)
        matches = _match_comparison_rows(
            sheet,
            obtained_rows,
            golden_rows,
        )
        for key, obtained, expected in matches:
            if obtained is None or expected is None:
                severity = (
                    "CRÍTICA"
                    if sheet in ("Partidas", "Estructura")
                    else "NO CRÍTICA"
                )
                differences.append(
                    WorkbookDifference(
                        sheet=sheet,
                        key=key,
                        column="fila",
                        obtained="FALTANTE" if obtained is None else "PRESENTE",
                        expected="PRESENTE" if expected is not None else "FALTANTE",
                        difference="",
                        severity=severity,
                        explanation=(
                            "Partida o nodo faltante/adicional"
                            if severity == "CRÍTICA"
                            else "Registro de control o auditoría diferente"
                        ),
                    )
                )
                continue
            for column in sorted(set(obtained_headers) | set(golden_headers)):
                if column not in obtained or column not in expected:
                    differences.append(
                        WorkbookDifference(
                            sheet=sheet,
                            key=key,
                            column=column,
                            obtained=obtained.get(column, "COLUMNA AUSENTE"),
                            expected=expected.get(column, "COLUMNA AUSENTE"),
                            difference="",
                            severity="NO CRÍTICA",
                            explanation="Columna adicional solicitada o diferencia de esquema",
                        )
                    )
                    continue
                equal, numeric_difference = _values_equal(
                    obtained[column], expected[column]
                )
                if equal:
                    continue
                severity, explanation = _difference_severity(
                    sheet,
                    column,
                    numeric_difference,
                )
                differences.append(
                    WorkbookDifference(
                        sheet=sheet,
                        key=key,
                        column=column,
                        obtained=obtained[column],
                        expected=expected[column],
                        difference=numeric_difference,
                        severity=severity,
                        explanation=explanation,
                    )
                )
    return differences


def write_difference_report(
    output_path: Path,
    differences: Sequence[WorkbookDifference],
) -> None:
    if output_path.exists():
        raise FileExistsError(
            "El reporte ya existe y no será sobrescrito: %s" % output_path
        )
    from openpyxl import Workbook  # type: ignore
    from openpyxl.styles import Font, PatternFill  # type: ignore

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Diferencias"
    sheet.append(DIFFERENCE_COLUMNS)
    for item in differences:
        sheet.append(
            [
                item.sheet,
                item.key,
                item.column,
                item.obtained,
                item.expected,
                item.difference,
                item.severity,
                item.explanation,
            ]
        )
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = PatternFill("solid", fgColor="1F4E78")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    widths = (18, 50, 28, 35, 35, 18, 15, 55)
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[chr(64 + index)].width = width
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(str(output_path))


def configure_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("presupuestos")
    logger.setLevel(logging.INFO)
    logger.handlers = []
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


def format_result(result: DocumentResult) -> str:
    structural = result.rows
    leaf_sum = sum(
        (
            row.parcial_soles
            for row in structural
            if row.tipo_fila == "partida" and row.parcial_soles is not None
        ),
        Decimal("0"),
    )
    lines = [
        "páginas con tabla: %s" % len(result.controls),
        "partidas exportadas: %s"
        % sum(row.tipo_fila == "partida" for row in structural),
        "títulos de estructura: %s"
        % sum(
            row.tipo_fila in ("categoria", "grupo", "subgrupo")
            for row in structural
        ),
        "incidencias de revisión OCR: %s" % len(build_revision_incidents(result)),
        "filas descartadas: %s"
        % sum(control.filas_descartadas for control in result.controls),
        "suma de parciales hoja: %s" % leaf_sum,
        "validaciones:",
    ]
    lines.extend("  - %s" % validation for validation in result.validations)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extrae un presupuesto desde PDF imagen o PDF con OCR."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--source-pdf",
        type=Path,
        help="PDF original; se crea OCR derivado si no tiene texto.",
    )
    source.add_argument(
        "--processed-pdf",
        type=Path,
        help="PDF que ya contiene una capa OCR utilizable.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("salida/presupuestos_extraidos_v6_codex.xlsx"),
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("logs/procesamiento_v6_codex.log"),
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=Path("procesados"),
        help="Directorio para el PDF OCR derivado.",
    )
    parser.add_argument(
        "--golden",
        type=Path,
        help="Golden opcional, usado solo para comparación de desarrollo.",
    )
    parser.add_argument(
        "--diff-output",
        type=Path,
        help="Reporte opcional de diferencias contra --golden.",
    )
    parser.add_argument(
        "--code-review-output",
        type=Path,
        help="Libro independiente para revisión humana de códigos pendientes.",
    )
    parser.add_argument(
        "--approved-code-review",
        type=Path,
        help="Libro de revisión humana previamente completado.",
    )
    parser.add_argument(
        "--approved-numeric-review",
        type=Path,
        help=(
            "Registro JSON de correcciones numéricas confirmadas "
            "visualmente por una persona."
        ),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    input_pdf = args.source_pdf or args.processed_pdf
    if input_pdf is None or not input_pdf.is_file():
        print("No existe el PDF: %s" % input_pdf, file=sys.stderr)
        return 2
    if bool(args.golden) != bool(args.diff_output):
        print(
            "--golden y --diff-output deben usarse juntos",
            file=sys.stderr,
        )
        return 2
    if (
        args.approved_code_review is not None
        and not args.approved_code_review.is_file()
    ):
        print(
            "No existe el archivo de revisión aprobada: %s"
            % args.approved_code_review,
            file=sys.stderr,
        )
        return 2
    if (
        args.approved_numeric_review is not None
        and not args.approved_numeric_review.is_file()
    ):
        print(
            "No existe el archivo de revisión numérica aprobada: %s"
            % args.approved_numeric_review,
            file=sys.stderr,
        )
        return 2
    logger = configure_logging(args.log)
    try:
        if args.source_pdf is not None:
            result = process_source_pdf(
                args.source_pdf,
                logger,
                args.processed_dir,
                args.approved_code_review,
                args.approved_numeric_review,
            )
        else:
            result = process_processed_pdf(
                args.processed_pdf,
                logger,
                args.approved_code_review,
                args.approved_numeric_review,
            )
        write_workbook_v6(
            args.output,
            input_pdf.name,
            result,
            args.overwrite,
        )
        if args.golden is not None and args.diff_output is not None:
            differences = compare_v6_workbooks(args.output, args.golden)
            write_difference_report(args.diff_output, differences)
            logger.info(
                "COMPARACION_GOLDEN diferencias=%s criticas=%s reporte=%s",
                len(differences),
                sum(item.severity == "CRÍTICA" for item in differences),
                args.diff_output,
            )
        if args.code_review_output is not None:
            write_code_review_workbook(
                args.code_review_output,
                result.code_reviews,
            )
    except Exception:
        logger.exception("FALLO_DOCUMENTO archivo=%s", input_pdf)
        return 1
    print(format_result(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
