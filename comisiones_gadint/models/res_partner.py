# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Plan de comisión nativo (Odoo 18) - Solo si el módulo está disponible
    commission_plan_id = fields.Many2one(
        'sale.commission.plan',  
        string='Plan de comisión (nativo)',
        help='Plan de comisión nativo de Odoo 18 usado cuando este contacto actúa como Referrer.'
    )

    # Campo booleano para identificar vendedores externos
    external_sales_team = fields.Boolean(
        string='Equipo vendedores externos',
        default=False,
        help='Marque esta casilla si este contacto pertenece al equipo de vendedores externos'
    )
    
    # Campo computed para mostrar si es vendedor externo en vistas
    is_external_salesperson = fields.Boolean(
        string='Es vendedor externo',
        compute='_compute_is_external_salesperson',
        store=True,
        help='Indica si este contacto está configurado como vendedor externo'
    )
    
    @api.onchange('external_sales_team')
    def _onchange_external_sales_team_commission_plan(self):
        """Si el contacto pasa a ser Vendedor Externo y no tiene plan, usar el plan por defecto."""
        if self.external_sales_team and not self.commission_plan_id:
            # Verificar si el modelo existe antes de usarlo
            if 'sale.commission.plan' in self.env:
                param = self.env['ir.config_parameter'].sudo().get_param('comisiones_gadint.default_commission_plan_id')
                if param:
                    try:
                        plan_id = int(param)
                        # Verificar que el plan existe
                        plan_exists = self.env['sale.commission.plan'].sudo().browse(plan_id).exists()
                        if plan_exists:
                            self.commission_plan_id = plan_id
                    except Exception:
                        # Silencioso: no romper el onchange si el parámetro está corrupto
                        pass

    def write(self, vals):
        res = super().write(vals)
        # Asignación automática en write (por si se marca vía importación o servidor)
        if 'external_sales_team' in vals and vals.get('external_sales_team'):
            for partner in self:
                if not partner.commission_plan_id and 'sale.commission.plan' in self.env:
                    param = self.env['ir.config_parameter'].sudo().get_param('comisiones_gadint.default_commission_plan_id')
                    if param:
                        try:
                            plan_id = int(param)
                            # Verificar que el plan existe
                            plan_exists = self.env['sale.commission.plan'].sudo().browse(plan_id).exists()
                            if plan_exists:
                                partner.commission_plan_id = plan_id
                        except Exception:
                            # no levantamos error aquí para no bloquear escrituras masivas
                            pass
        return res

    @api.depends('external_sales_team')
    def _compute_is_external_salesperson(self):
        """Computa si el partner es vendedor externo"""
        for partner in self:
            # Verificar si existe en el modelo de vendedores externos
            external_salesperson = self.env['gadint.external.salesperson'].search([
                ('partner_id', '=', partner.id)
            ], limit=1)
            partner.is_external_salesperson = bool(external_salesperson)
    
    def name_get(self):
        """Sobrescribir name_get para mostrar información adicional en vendedores externos"""
        result = super().name_get()
        if self.env.context.get('show_external_salesperson_info'):
            new_result = []
            for partner_id, name in result:
                partner = self.browse(partner_id)
                if partner.external_sales_team:
                    name = f"{name} (Vendedor Externo)"
                new_result.append((partner_id, name))
            return new_result
        return result