from odoo import models, fields, api

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    responsable_validacion = fields.Many2one(
        'res.users',
        string='Responsable:',
        readonly=True,
        help='Usuario que validó esta operación de stock'
    )
    
    def button_validate(self):
        """Sobrescribe el método de validación para capturar el usuario responsable"""
        # Ejecutar la validación original
        result = super(StockPicking, self).button_validate()
        
        # Si la validación fue exitosa y el estado cambió a 'done'
        for picking in self:
            if picking.state == 'done' and not picking.responsable_validacion:
                picking.responsable_validacion = self.env.user.id
        
        return result
    
    @api.model
    def write(self, vals):
        """Intercepta escrituras para capturar cuando el estado cambia a 'done'"""
        result = super(StockPicking, self).write(vals)
        
        # Si se está cambiando el estado a 'done'
        if vals.get('state') == 'done':
            for picking in self:
                if not picking.responsable_validacion:
                    picking.responsable_validacion = self.env.user.id
        
        return result