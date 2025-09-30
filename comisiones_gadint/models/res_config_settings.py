# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    gadint_auto_assign_commission = fields.Boolean(
        string='Auto-asignar Referrer/Plan (Vendedores Externos)',
        config_parameter='comisiones_gadint.auto_assign_commission',
        help='Si está activo, al elegir vendedores externos en el pedido se establecerá Referrer y Plan automáticamente.'
    )

    gadint_default_commission_plan_id = fields.Many2one(
        'sale.commission.plan',  
        string='Plan de Comisión por defecto (Vendedores Externos)',
        config_parameter='comisiones_gadint.default_commission_plan_id',
        help='Plan que se aplicará por defecto a Vendedores Externos cuando el partner no tenga uno propio.'
    )
    
    @api.model
    def get_values(self):
        """Sobrescribir para manejar casos donde sale_commission no está instalado"""
        res = super().get_values()
        
        # Solo obtener el valor si el modelo existe
        if 'sale.commission.plan' in self.env:
            param = self.env['ir.config_parameter'].sudo().get_param('comisiones_gadint.default_commission_plan_id')
            if param:
                try:
                    plan_id = int(param)
                    # Verificar que el plan existe
                    plan_exists = self.env['sale.commission.plan'].sudo().browse(plan_id).exists()
                    if plan_exists:
                        res['gadint_default_commission_plan_id'] = plan_id
                except Exception:
                    res['gadint_default_commission_plan_id'] = False
        else:
            res['gadint_default_commission_plan_id'] = False
            
        return res