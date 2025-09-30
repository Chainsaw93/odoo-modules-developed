from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    is_landed_cost_manufacturing = fields.Boolean(
        string='Costo en destino de fabricación',
        default=False,
        help='Indica si este producto es un costo en destino de fabricación'
    )