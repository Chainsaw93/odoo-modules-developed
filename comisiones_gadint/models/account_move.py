# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Campo Many2many para vendedores externos (solo lectura desde factura)
    external_salesperson_ids = fields.Many2many(
        'gadint.external.salesperson',
        'account_move_external_salesperson_rel',
        'account_move_id',
        'external_salesperson_id',
        string='Vendedores Externos',
        readonly=True,
        help='Vendedores externos asignados desde el pedido. No se puede modificar desde la factura.'
    )
    
    # Campo computed para mostrar nombres de vendedores externos
    external_salesperson_names = fields.Char(
        string='Vendedores Externos',
        compute='_compute_external_salesperson_names',
        store=True,
        help='Nombres de los vendedores externos asignados'
    )
    
    # Campo booleano para comisión pagada
    commission_paid = fields.Boolean(
        string='Comisión Pagada',
        default=False,
        help='Se marca automáticamente cuando la factura está vinculada con uno o varios pagos'
    )
    
    # Campo Many2one para pago relacionado
    related_payment_id = fields.Many2one(
        'account.payment',
        string='Pago Relacionado',
        readonly=True,
        help='Último pago vinculado que activó la comisión pagada'
    )
    
    # Campo computed para mostrar estado de pago para comisiones
    payment_status_commission = fields.Selection([
        ('unpaid', 'Sin Pagar'),
        ('partial', 'Parcialmente Pagado'),
        ('paid', 'Totalmente Pagado')
    ], string='Estado de Pago (Comisión)', 
       compute='_compute_payment_status_commission',
       store=True,
       help='Estado de pago específico para el cálculo de comisiones')
    
    amount_paid_commission = fields.Monetary(
        string='Subtotal cobrado (Comisiones)',
        currency_field='currency_id',
        compute='_compute_amount_paid_commission',
        store=True,
        help='Subtotal cobrado (proporcional al pago) para efectos de análisis de comisiones.'
    )
    
    # Campo computed para mostrar total de comisiones calculadas
    total_commission_amount = fields.Monetary(
        string='Total Comisiones Calculadas',
        currency_field='currency_id',
        compute='_compute_total_commission_amount',
        store=False,
        help='Suma total de todas las comisiones calculadas para esta factura'
    )
    
    # Campo computed para mostrar detalle de comisiones
    commission_detail = fields.Text(
        string='Detalle de Comisiones',
        compute='_compute_commission_detail',
        help='Detalle de comisiones calculadas por vendedor'
    )

    @api.depends('amount_total', 'amount_residual', 'amount_untaxed', 'currency_id', 'move_type', 'state')
    def _compute_amount_paid_commission(self):
        for move in self:
            if move.move_type == 'out_invoice' and move.state == 'posted':
                # Subtotal cobrado proporcional al pago
                if move.amount_total > 0:
                    cobrado_ratio = max(move.amount_total - move.amount_residual, 0.0) / move.amount_total
                    move.amount_paid_commission = move.amount_untaxed * cobrado_ratio
                else:
                    move.amount_paid_commission = 0.0
            else:
                move.amount_paid_commission = 0.0

    @api.depends('external_salesperson_ids')
    def _compute_external_salesperson_names(self):
        """Computa los nombres de vendedores externos para mostrar"""
        for move in self:
            if move.external_salesperson_ids:
                names = move.external_salesperson_ids.mapped('display_name')
                move.external_salesperson_names = ', '.join(names)
            else:
                move.external_salesperson_names = ''
    
    @api.depends('payment_state', 'amount_residual', 'amount_total')
    def _compute_payment_status_commission(self):
        """Computa el estado de pago para comisiones"""
        for move in self:
            if move.move_type == 'out_invoice':
                if move.payment_state == 'paid':
                    move.payment_status_commission = 'paid'
                elif move.payment_state == 'partial':
                    move.payment_status_commission = 'partial'
                else:
                    move.payment_status_commission = 'unpaid'
            else:
                move.payment_status_commission = 'unpaid'
    
    @api.depends('payment_state', 'line_ids.matched_debit_ids', 'line_ids.matched_credit_ids')
    def _compute_commission_paid_status(self):
        """Computa automáticamente el estado de comisión pagada"""
        for move in self:
            if move.move_type == 'out_invoice':
                # Verificar si hay pagos vinculados
                payments = move._get_reconciled_payments()
                
                if payments:
                    # Si hay pagos, marcar como comisión pagada
                    move.commission_paid = True
                    # Establecer el último pago como relacionado
                    move.related_payment_id = payments[-1].id if payments else False
                else:
                    move.commission_paid = False
                    move.related_payment_id = False
            else:
                move.commission_paid = False
                move.related_payment_id = False
    
    def _get_reconciled_payments(self):
        """Obtener todos los pagos reconciliados con esta factura"""
        payments = self.env['account.payment']
        
        for line in self.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable'):
            # Buscar líneas de pago reconciliadas
            matched_lines = line.matched_debit_ids + line.matched_credit_ids
            for matched in matched_lines:
                payment_line = matched.debit_move_id if matched.debit_move_id != line else matched.credit_move_id
                if payment_line.payment_id:
                    payments |= payment_line.payment_id
        
        return payments
    
    @api.depends('payment_state', 'amount_residual')
    def _compute_total_commission_amount(self):
        """Calcular total de comisiones calculadas para esta factura"""
        for move in self:
            total = 0.0
            if 'sale.commission.achievement' in self.env:
                # Buscar comisiones calculadas para esta factura
                achievements = self.env['sale.commission.achievement'].search([
                    ('invoice_id', '=', move.id),
                    ('type', '=', 'amount_collected')
                ])
                total = sum(achievements.mapped('amount'))
            move.total_commission_amount = total
    
    @api.depends('payment_state', 'amount_residual', 'external_salesperson_ids')
    def _compute_commission_detail(self):
        """Calcular detalle de comisiones por vendedor"""
        for move in self:
            detail = ""
            if 'sale.commission.achievement' in self.env and move.external_salesperson_ids:
                achievements = self.env['sale.commission.achievement'].search([
                    ('invoice_id', '=', move.id),
                    ('type', '=', 'amount_collected')
                ])
                
                if achievements:
                    detail = "COMISIONES CALCULADAS:\n"
                    for achievement in achievements:
                        detail += f"- {achievement.note}: {achievement.amount:.2f} {move.currency_id.name}\n"
                    
                    # ACTUALIZAR COMISIONES INDIVIDUALES AQUÍ
                    self._update_individual_commissions()
                    
                else:
                    # Mostrar información de por qué no hay comisiones
                    if not move.commission_paid:
                        detail = "Comisiones pendientes: Factura no está completamente pagada"
                    else:
                        detail = "Sin comisiones calculadas: Verificar planes de comisión configurados"
            move.commission_detail = detail
    
    def _update_individual_commissions(self):
        """Actualizar las comisiones individuales de cada vendedor"""
        for move in self:
            if move.external_salesperson_ids and 'sale.commission.achievement' in self.env:
                achievements = self.env['sale.commission.achievement'].search([
                    ('invoice_id', '=', move.id),
                    ('type', '=', 'amount_collected')
                ])
                
                for salesperson in move.external_salesperson_ids:
                    amount = 0.0
                    for achievement in achievements:
                        if (salesperson.name in achievement.note or 
                            salesperson.display_name in achievement.note or
                            (salesperson.partner_id and salesperson.partner_id.name in achievement.note)):
                            amount += achievement.amount
                    
                    # Forzar actualización del campo computed
                    salesperson.with_context(
                        invoice_id=move.id,
                        force_commission_amount=amount
                    )._compute_commission_amount_invoice()
    
    def get_commission_for_salesperson(self, salesperson_id):
        """Obtener comisión calculada para un vendedor específico"""
        if 'sale.commission.achievement' not in self.env:
            return 0.0
            
        achievements = self.env['sale.commission.achievement'].search([
            ('invoice_id', '=', self.id),
            ('type', '=', 'amount_collected'),
            ('note', 'ilike', f'%{self.env["gadint.external.salesperson"].browse(salesperson_id).name}%')
        ])
        
        return sum(achievements.mapped('amount'))
    
    def action_post(self):
        """Sobrescribir para verificar vendedores externos al confirmar factura"""
        result = super().action_post()
        
        for move in self:
            if move.move_type == 'out_invoice' and move.external_salesperson_ids:
                # Crear mensaje en el chatter con vendedores externos
                salesperson_names = move.external_salesperson_ids.mapped('display_name')
                message = f"""
                <p><strong>Factura confirmada con vendedores externos:</strong></p>
                <ul>
                """
                for name in salesperson_names:
                    message += f"<li>{name}</li>"
                message += "</ul>"
                
                move.message_post(
                    body=message,
                    subject='Factura Confirmada - Vendedores Externos'
                )
                
                # CALCULAR COMISIONES AUTOMÁTICAMENTE AL CONFIRMAR FACTURA
                if 'sale.commission.plan' in self.env:
                    move.message_post(
                        body=f"ACTION_POST: Iniciando cálculo automático de comisiones al confirmar factura",
                        subject='ACTION_POST - Cálculo de Comisiones'
                    )
                    
                    commission_model = self.env['account.move'].sudo()
                    if hasattr(commission_model, '_calculate_amount_collected_commissions'):
                        commission_model._calculate_amount_collected_commissions(move)
                        move._compute_total_commission_amount()
                        move._compute_commission_detail()
                        move._update_individual_commissions()
                        
                        move.message_post(
                            body="ACTION_POST: Cálculo de comisiones completado automáticamente al confirmar factura",
                            subject='ACTION_POST - Comisiones Calculadas'
                        )
        
        return result
    
    def _reconcile_payments(self, debit_moves, credit_moves):
        """Sobrescribir para actualizar comisión pagada automáticamente"""
        result = super()._reconcile_payments(debit_moves, credit_moves)
        
        # Actualizar estado de comisión pagada para facturas afectadas
        moves_to_update = (debit_moves + credit_moves).filtered(
            lambda m: m.move_type == 'out_invoice' and m.external_salesperson_ids
        )
        
        for move in moves_to_update:
            # LOG para saber cuándo se ejecuta este método
            move.message_post(
                body=f"RECONCILE TRIGGER - Procesando pago para factura con {len(move.external_salesperson_ids)} vendedores externos",
                subject='RECONCILE - Trigger Activado'
            )
            
            move._compute_commission_paid_status()
            
            # Las comisiones se calculan automáticamente en commission_plan.py
            # Solo hacer log aquí para seguimiento
            move.message_post(
                body=f"ACCOUNT_MOVE RECONCILE - Las comisiones serán calculadas por commission_plan.py automáticamente",
                subject='ACCOUNT_MOVE - Reconcile Info'
            )
            
            # Si se marcó como pagada, crear mensaje
            if move.commission_paid:
                message = f"""
                <p><strong>🎉 Comisión marcada como pagada automáticamente</strong></p>
                <p>La factura ha sido vinculada con un pago, por lo que la comisión 
                   se ha marcado como pagada para los vendedores externos:</p>
                <ul>
                """
                for salesperson in move.external_salesperson_ids:
                    message += f"<li>{salesperson.display_name}</li>"
                message += "</ul>"
                
                move.message_post(
                    body=message,
                    subject='Comisión Marcada como Pagada'
                )
        
        return result
    
    

    @api.model
    def _cron_update_commission_paid_status(self):
        """Cron job para actualizar estado de comisiones pagadas"""
        # Buscar facturas con vendedores externos que podrían necesitar actualización
        invoices = self.search([
            ('move_type', '=', 'out_invoice'),
            ('external_salesperson_ids', '!=', False),
            ('state', '=', 'posted')
        ])
        
        for invoice in invoices:
            old_status = invoice.commission_paid
            invoice._compute_commission_paid_status()
            
            # Si cambió el estado, crear log
            if old_status != invoice.commission_paid:
                status_text = 'pagada' if invoice.commission_paid else 'pendiente'
                invoice.message_post(
                    body=f'Estado de comisión actualizado automáticamente: {status_text}',
                    subject='Actualización Automática de Comisión'
                )
    
    def write(self, vals):
        """Sobrescribir write para monitorear cambios en pagos"""
        
        # LOG INICIAL - qué campos se están modificando
        if any(field in vals for field in ['payment_state', 'amount_residual', 'state']):
            for move in self.filtered(lambda m: m.move_type == 'out_invoice' and m.external_salesperson_ids):
                move.message_post(
                    body=f"WRITE TRIGGER - Campos modificados: {list(vals.keys())} | Valores: {vals}",
                    subject='WRITE - Campos Modificados'
                )
        
        result = super().write(vals)
        
        # Si se modificaron campos relacionados con pagos, recalcular comisión
        payment_fields = ['payment_state', 'amount_residual']
        if any(field in vals for field in payment_fields):
            for move in self.filtered(lambda m: m.move_type == 'out_invoice' and m.external_salesperson_ids):
                # LOG PARA DEBUG
                move.message_post(
                    body=f"DEBUG DESPUÉS DEL WRITE: payment_state = {move.payment_state}, amount_residual = {move.amount_residual}, external_salesperson_ids = {len(move.external_salesperson_ids)}",
                    subject='DEBUG - Estado Después del Write'
                )
                
                # Actualizar estado de comisión pagada (solo para 'paid')
                move._compute_commission_paid_status()
                
                # Calcular comisiones para 'paid' e 'in_payment' - EXPANDIR ESTADOS
                valid_states = ['paid', 'in_payment', 'partial']  # Expandir estados válidos
                if move.payment_state in valid_states and 'sale.commission.plan' in self.env:
                    move.message_post(
                        body=f"TRIGGER: Iniciando cálculo de comisiones para estado {move.payment_state}",
                        subject='TRIGGER - Cálculo de Comisiones'
                    )
                    
                    # Llamar al método de cálculo de comisiones desde commission_plan.py
                    commission_model = self.env['account.move'].sudo()
                    if hasattr(commission_model, '_calculate_amount_collected_commissions'):
                        commission_model._calculate_amount_collected_commissions(move)
                        # Forzar recálculo de campos computed
                        move._compute_total_commission_amount()
                        move._compute_commission_detail()
                        move._update_individual_commissions()
                        
                        # Mensaje de confirmación
                        move.message_post(
                            body=f"ACTUALIZACIÓN: Comisiones individuales actualizadas automáticamente",
                            subject='ACTUALIZACIÓN - Comisiones Individuales'
                        )
                        
                        move.message_post(
                            body="RESULTADO: Cálculo de comisiones completado",
                            subject='RESULTADO - Comisiones'
                        )
        
        return result