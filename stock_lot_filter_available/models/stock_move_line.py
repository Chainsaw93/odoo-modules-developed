from odoo import models, api

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    @api.onchange('product_id', 'location_id')
    def _onchange_product_id_location_id(self):
        if self.picking_id.picking_type_code in ['internal', 'outgoing'] and self.product_id and self.location_id:
            quants = self.env['stock.quant'].search([
                ('product_id', '=', self.product_id.id),
                ('location_id', 'child_of', self.location_id.id),
                ('quantity', '>', 0),
                ('lot_id', '!=', False)
            ])
            return {
                'domain': {
                    'lot_id': [('id', 'in', quants.mapped('lot_id').ids)]
                }
            }
        return {}
