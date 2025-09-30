from odoo import models, fields, api, _


class MrpProductionCloseConfirmation(models.TransientModel):
    _name = 'mrp.production.close.confirmation'
    _description = 'Confirmación de cierre de producción'
    
    production_id = fields.Many2one(
        'mrp.production',
        string='Orden de Fabricación',
        required=True
    )
    
    message = fields.Text(
        string='Mensaje',
        default='Faltan valores por ingresar en los costos indirectos.',
        readonly=True
    )
    
    def action_accept(self):
        """Aceptar y cerrar producción"""
        self.production_id.force_close_production()
        return {'type': 'ir.actions.act_window_close'}
    
    def action_cancel(self):
        """Cancelar y no cerrar producción"""
        return {'type': 'ir.actions.act_window_close'}