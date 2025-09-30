# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Campo Many2many para vendedores externos
    external_salesperson_ids = fields.Many2many(
        'gadint.external.salesperson',
        'sale_order_external_salesperson_rel',
        'sale_order_id',
        'external_salesperson_id',
        string='Vendedores Externos',
        help='Seleccione uno o más vendedores externos para esta cotización si aplica.'
    )
    
    # Campo computed para mostrar nombres de vendedores externos
    external_salesperson_names = fields.Char(
        string='Vendedores Externos',
        compute='_compute_external_salesperson_names',
        store=True,
        help='Nombres de los vendedores externos asignados'
    )
    
    @api.depends('external_salesperson_ids')
    def _compute_external_salesperson_names(self):
        """Computa los nombres de vendedores externos para mostrar"""
        for order in self:
            if order.external_salesperson_ids:
                names = order.external_salesperson_ids.mapped('display_name')
                order.external_salesperson_names = ', '.join(names)
            else:
                order.external_salesperson_names = ''
    
    
    def action_update_external_salesperson(self):
        """Acción para actualizar vendedores externos en facturas relacionadas"""
        for order in self:
            if order.state == 'sale':  # Solo para pedidos confirmados
                # Buscar facturas relacionadas
                invoices = order.invoice_ids.filtered(lambda x: x.move_type == 'out_invoice')
                
                if invoices:
                    # Contador para tracking
                    commissions_calculated = 0
                    
                    # Actualizar vendedores externos en todas las facturas
                    for invoice in invoices:
                        invoice.write({
                            'external_salesperson_ids': [(6, 0, order.external_salesperson_ids.ids)]
                        })
                        
                        # NUEVO: Calcular comisiones para facturas confirmadas con vendedores
                        if (invoice.state == 'posted' and 
                            invoice.external_salesperson_ids and 
                            'sale.commission.plan' in self.env):
                            
                            # Verificar si ya existen comisiones
                            existing_achievements = self.env['sale.commission.achievement'].search([
                                ('invoice_id', '=', invoice.id),
                                ('type', '=', 'amount_collected')
                            ])
                            
                            if not existing_achievements:
                                # Solo calcular si no existen comisiones previas
                                commission_model = self.env['account.move'].sudo()
                                if hasattr(commission_model, '_calculate_amount_collected_commissions'):
                                    commission_model._calculate_amount_collected_commissions(invoice)
                                    commissions_calculated += 1
                                    
                                    # Forzar actualización de campos computed
                                    invoice._compute_total_commission_amount()
                                    invoice._compute_commission_detail()
                                    
                                    # Actualizar display de vendedores externos
                                    for salesperson in invoice.external_salesperson_ids:
                                        salesperson._compute_commission_rate_display()
                                    
                                    # Log en la factura
                                    invoice.message_post(
                                        body=f"✅ COMISIONES CALCULADAS automáticamente por actualización de vendedores desde cotización {order.name}",
                                        subject='Comisiones - Cálculo Automático'
                                    )
                    
                    # Mensaje de confirmación
                    message = f"""
                    <p><strong>Vendedores externos actualizados:</strong></p>
                    <ul>
                    """
                    for salesperson in order.external_salesperson_ids:
                        message += f"<li>{salesperson.display_name}</li>"
                    message += f"""
                    </ul>
                    <p>Actualizado en {len(invoices)} factura(s) relacionada(s).</p>
                    """
                    
                    # Agregar información sobre comisiones calculadas
                    if commissions_calculated > 0:
                        message += f"""
                        <p><strong>🎉 Comisiones calculadas automáticamente en {commissions_calculated} factura(s) confirmada(s).</strong></p>
                        """
                    
                    order.message_post(
                        body=message,
                        subject='Vendedores Externos Actualizados'
                    )
                    
                    # Mensaje de notificación mejorado
                    if commissions_calculated > 0:
                        notification_message = f'Vendedores actualizados en {len(invoices)} factura(s) y comisiones calculadas en {commissions_calculated} factura(s)'
                        notification_title = '🎉 Actualización y Cálculo Exitoso'
                    else:
                        notification_message = f'Vendedores externos actualizados en {len(invoices)} factura(s)'
                        notification_title = 'Actualización Exitosa'
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': notification_title,
                            'message': notification_message,
                            'type': 'success',
                            'sticky': False,
                        }
                    }
                else:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Sin facturas',
                            'message': 'No hay facturas relacionadas para actualizar',
                            'type': 'warning',
                            'sticky': False,
                        }
                    }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Estado inválido',
                        'message': 'Solo se pueden actualizar pedidos confirmados',
                        'type': 'warning',
                        'sticky': False,
                    }
                }
    
    def _create_invoices(self, grouped=False, final=False, date=None):
        """Sobrescribir para transferir vendedores externos a facturas"""
        invoices = super()._create_invoices(grouped=grouped, final=final, date=date)
        
        # Transferir vendedores externos a las facturas creadas
        for invoice in invoices:
            # Buscar las órdenes de venta relacionadas con esta factura
            sale_orders = invoice.invoice_line_ids.mapped('sale_line_ids.order_id')
            
            # Recopilar todos los vendedores externos de las órdenes relacionadas
            all_external_salesperson_ids = []
            for order in sale_orders:
                if order.external_salesperson_ids:
                    all_external_salesperson_ids.extend(order.external_salesperson_ids.ids)
            
            # Eliminar duplicados y asignar a la factura
            unique_ids = list(set(all_external_salesperson_ids))
            if unique_ids:
                invoice.write({
                    'external_salesperson_ids': [(6, 0, unique_ids)]
                })
        
        return invoices
    
    @api.onchange('partner_id')
    def _onchange_partner_external_salesperson(self):
        """Limpiar vendedores externos cuando cambia el cliente"""
        if self.partner_id:
            # Mantener los vendedores externos ya seleccionados
            pass
        else:
            self.external_salesperson_ids = [(5, 0, 0)]  # Limpiar todos
    
    def write(self, vals):
        """Sobrescribir write para registrar cambios en vendedores externos"""
        result = super().write(vals)
        
        if 'external_salesperson_ids' in vals:
            for order in self:
                if order.external_salesperson_ids:
                    # Crear mensaje en el chatter cuando se cambian los vendedores
                    salesperson_names = order.external_salesperson_ids.mapped('display_name')
                    message = f"""
                    <p><strong>Vendedores externos modificados:</strong></p>
                    <ul>
                    """
                    for name in salesperson_names:
                        message += f"<li>{name}</li>"
                    message += "</ul>"
                    
                    order.message_post(
                        body=message,
                        subject='Vendedores Externos Modificados'
                    )
        
        return result
    
    def _gadint_pick_referrer_partner(self):
        """Devuelve el partner del líder si existe; sino el primero."""
        self.ensure_one()
        partner = False
        if self.external_salesperson_ids:
            leader = self.external_salesperson_ids.filtered(lambda s: s.seller_type == 'leader')[:1]
            chosen = leader or self.external_salesperson_ids[:1]
            if chosen:
                partner = chosen.partner_id
        return partner

    @api.onchange('external_salesperson_ids')
    def _onchange_external_salesperson_ids_set_referrer_plan(self):
        """Auto-asignar Referrer + Plan cuando cambian los vendedores externos."""
        if not self.external_salesperson_ids:
            return

        auto = self.env['ir.config_parameter'].sudo().get_param('comisiones_gadint.auto_assign_commission')
        if not (auto and auto not in ('False', '0')):
            return

        ref_partner = self._gadint_pick_referrer_partner()
        if ref_partner:
            # Solo si el campo existe en el modelo (evita fallos si la feature está desactivada)
            if 'referrer_id' in self._fields:
                self.referrer_id = ref_partner
            # Plan en pedido (si el campo existe)
            if 'commission_plan_id' in self._fields:
                self.commission_plan_id = ref_partner.commission_plan_id or False
                if not self.commission_plan_id:
                    param = self.env['ir.config_parameter'].sudo().get_param('comisiones_gadint.default_commission_plan_id')
                    if param:
                        try:
                            self.commission_plan_id = int(param)
                        except Exception:
                            pass

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        # Mantener coherencia en factura: Referrer + Plan (si los campos existen en account.move)
        try:
            ref_partner = self._gadint_pick_referrer_partner()
            Move = self.env['account.move']
            if ref_partner and 'referrer_id' in Move._fields:
                vals['referrer_id'] = ref_partner.id
            if 'commission_plan_id' in Move._fields:
                plan_id = None
                if ref_partner and ref_partner.commission_plan_id:
                    plan_id = ref_partner.commission_plan_id.id
                else:
                    param = self.env['ir.config_parameter'].sudo().get_param('comisiones_gadint.default_commission_plan_id')
                    if param:
                        plan_id = int(param)
                if plan_id:
                    vals['commission_plan_id'] = plan_id
        except Exception:
            # Nunca romper la creación de facturas si la feature no está presente
            pass
        return vals