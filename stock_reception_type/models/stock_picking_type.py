from odoo import models, fields, api


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    reception_operation_type = fields.Selection(
        selection=[('garantia', 'Garantía')],
        string='Tipo de operación de recepción',
        help='Tipo específico de operación de recepción'
    )

    is_reception_type = fields.Boolean(
        string='Es tipo de recepción',
        compute='_compute_is_reception_type',
        store=False
    )

    @api.depends('code')
    def _compute_is_reception_type(self):
        """Calcula si el tipo de operación actual es de recepción"""
        for record in self:
            record.is_reception_type = record.code == 'incoming'