from odoo import models, fields, api, _

class StockPickingSerial(models.Model):
    _inherit = 'stock.picking'

    # Campo computado para resumen de validación (solo informativo)
    serial_validation_summary = fields.Html(
        compute='_compute_serial_validation_summary',
        string="Resumen de Validación de Series"
    )

    has_serial_validation_errors = fields.Boolean(
        compute='_compute_serial_validation_summary',
        help="Indica si hay errores de validación de números de serie"
    )

    def on_barcode_scanned(self, barcode):
        """
        Override para incluir validación básica de series en barcode
        """
        result = super().on_barcode_scanned(barcode)
        return result