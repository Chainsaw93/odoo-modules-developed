from odoo import models, fields, api

class ProductProduct(models.Model):
    _inherit = 'product.product'
    
    @api.model
    def get_serial_validation_config(self):
        """Obtener configuración de validación para productos con serie"""
        return {
            'enable_realtime_validation': True,
            'validate_duplicates': True,
            'validate_availability': True,
            'allow_creation_on_incoming': True,
        }