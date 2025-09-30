from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class LoanTrackingDetail(models.Model):
    _name = 'loan.tracking.detail'
    _description = 'Seguimiento Detallado de Préstamos'
    _order = 'loan_date desc, id desc'
    _rec_name = 'display_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _mail_post_access = 'read'

    # Referencias principales
    picking_id = fields.Many2one(
        'stock.picking',
        string='Préstamo',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        index=True
    )
    
    lot_id = fields.Many2one(
        'stock.lot',
        string='Número de Serie/Lote',
        help="Solo para productos con rastreo por serie o lote",
        index=True
    )
    
    # Información del préstamo
    quantity = fields.Float(
        string='Cantidad',
        required=True,
        digits='Product Unit of Measure',
        help="Cantidad prestada (siempre 1 para productos con número de serie)"
    )
    
    status = fields.Selection([
        ('active', 'Préstamo Activo'),
        ('sold', 'Convertido a Venta'),
        ('returned_good', 'Devuelto en Buen Estado'),
        ('returned_damaged', 'Devuelto Dañado'),
        ('returned_defective', 'Devuelto Defectuoso'),
        ('pending_resolution', 'Pendiente de Resolución')
    ], string='Estado', required=True, default='active', index=True)
    
    # Fechas importantes
    loan_date = fields.Datetime(
        string='Fecha de Préstamo',
        required=True,
        default=fields.Datetime.now,
        index=True
    )
    
    resolution_date = fields.Datetime(
        string='Fecha de Resolución',
        help="Fecha cuando se resolvió el préstamo (venta o devolución)"
    )
    
    expected_return_date = fields.Date(
        related='picking_id.loan_expected_return_date',
        string='Fecha Esperada de Devolución',
        store=True,
        readonly=True
    )
    
    # CAMBIO: Información del cliente usando el nuevo campo
    partner_id = fields.Many2one(
        'res.partner',
        related='picking_id.loaned_to_partner_id',  # CAMBIO AQUÍ
        string='Cliente',
        store=True,
        readonly=True,
        index=True
    )
    
    # Información financiera
    original_cost = fields.Float(
        string='Costo Original',
        help="Costo del producto al momento del préstamo",
        digits='Product Price'
    )
    
    sale_price = fields.Float(
        string='Precio de Venta',
        help="Precio al cual se vendió (si aplica)",
        digits='Product Price'
    )
    
    # Referencias a transacciones relacionadas
    sale_order_line_id = fields.Many2one(
        'sale.order.line',
        string='Línea de Venta',
        help="Línea de orden de venta si se convirtió a venta"
    )
    
    return_picking_id = fields.Many2one(
        'stock.picking',
        string='Devolución',
        help="Transferencia de devolución si se devolvió"
    )
    
    # Campos calculados
    days_in_loan = fields.Integer(
        string='Días en Préstamo',
        compute='_compute_days_in_loan',
        store=True,
        help="Número de días que el producto ha estado/estuvo prestado"
    )
    
    is_overdue = fields.Boolean(
        string='Vencido',
        compute='_compute_overdue_status',
        store=True
    )
    
    display_name = fields.Char(
        string='Nombre',
        compute='_compute_display_name',
        store=True
    )
    
    # Notas y observaciones
    notes = fields.Text(
        string='Notas',
        help="Observaciones adicionales sobre este préstamo específico",
        tracking=True
    )
    
    return_condition_notes = fields.Text(
        string='Notas de Condición',
        help="Notas sobre el estado del producto al momento de la devolución",
        tracking=True
    )
    
    # ==========================================
    # CAMPOS ESPECÍFICOS PARA MAIL.THREAD
    # ==========================================
    
    active = fields.Boolean(
        string='Activo',
        default=True,
        help="Desmarcar para archivar el registro"
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='picking_id.company_id',
        store=True,
        readonly=True
    )
    
    # Campos para seguimiento de cambios
    last_status_change_date = fields.Datetime(
        string='Fecha Último Cambio Estado',
        help="Última vez que cambió el estado del préstamo",
        tracking=True
    )
    
    last_status_change_user_id = fields.Many2one(
        'res.users',
        string='Usuario Último Cambio',
        help="Usuario que realizó el último cambio de estado",
        tracking=True
    )
    
    # Campos para notificaciones automáticas
    notification_sent = fields.Boolean(
        string='Notificación Enviada',
        default=False,
        help="Indica si ya se envió notificación por vencimiento"
    )
    
    reminder_count = fields.Integer(
        string='Recordatorios Enviados',
        default=0,
        help="Número de recordatorios enviados al cliente"
    )
    
    next_reminder_date = fields.Date(
        string='Próximo Recordatorio',
        help="Fecha programada para el próximo recordatorio"
    )
    
    # Campos de seguimiento de actividades
    has_overdue_activity = fields.Boolean(
        string='Tiene Actividad Vencida',
        compute='_compute_activity_status',
        help="Indica si tiene actividades vencidas"
    )
    
    activity_summary = fields.Char(
        string='Resumen Actividades',
        compute='_compute_activity_status',
        help="Resumen del estado de actividades"
    )

    @api.depends('activity_ids.res_model', 'activity_ids.res_id', 'activity_ids.date_deadline')
    def _compute_activity_status(self):
        """Calcular estado de actividades para este registro"""
        for record in self:
            activities = record.activity_ids.filtered(lambda a: a.res_id == record.id)
            
            if activities:
                overdue_activities = activities.filtered(
                    lambda a: a.date_deadline < fields.Date.today()
                )
                record.has_overdue_activity = bool(overdue_activities)
                
                if overdue_activities:
                    record.activity_summary = f"Vencidas: {len(overdue_activities)} / Total: {len(activities)}"
                else:
                    record.activity_summary = f"Pendientes: {len(activities)}"
            else:
                record.has_overdue_activity = False
                record.activity_summary = "Sin actividades"

    @api.depends('product_id', 'lot_id', 'quantity', 'partner_id')
    def _compute_display_name(self):
        """Generar nombre descriptivo para el registro"""
        for record in self:
            parts = [record.product_id.name or 'Producto']
            
            if record.lot_id:
                parts.append(f"S/N: {record.lot_id.name}")
            elif record.quantity != 1:
                parts.append(f"Qty: {record.quantity}")
                
            if record.partner_id:
                parts.append(f"→ {record.partner_id.name}")
                
            record.display_name = ' '.join(parts)

    @api.depends('loan_date', 'resolution_date', 'status')
    def _compute_days_in_loan(self):
        """Calcular días en préstamo"""
        for record in self:
            if record.status == 'active':
                # Préstamo activo - calcular desde fecha de préstamo hasta hoy
                end_date = fields.Datetime.now()
            else:
                # Préstamo resuelto - calcular hasta fecha de resolución
                end_date = record.resolution_date or record.loan_date
                
            if record.loan_date:
                delta = end_date - record.loan_date
                record.days_in_loan = delta.days
            else:
                record.days_in_loan = 0

    @api.depends('expected_return_date', 'status')
    def _compute_overdue_status(self):
        """Determinar si el préstamo está vencido"""
        today = fields.Date.today()
        for record in self:
            if (record.status == 'active' and 
                record.expected_return_date and 
                record.expected_return_date < today):
                record.is_overdue = True
            else:
                record.is_overdue = False

    @api.constrains('quantity', 'product_id', 'lot_id')
    def _check_tracking_consistency(self):
        """Validar consistencia entre tipo de rastreo y datos"""
        for record in self:
            if record.product_id.tracking == 'serial':
                # Productos con serie deben tener lot_id y cantidad = 1
                if not record.lot_id:
                    raise ValidationError(_(
                        f"El producto {record.product_id.name} requiere número de serie."
                    ))
                if record.quantity != 1:
                    raise ValidationError(_(
                        f"Los productos con número de serie deben tener cantidad = 1. "
                        f"Producto: {record.product_id.name}"
                    ))
            elif record.product_id.tracking == 'lot':
                # Productos con lote deben tener lot_id
                if not record.lot_id:
                    raise ValidationError(_(
                        f"El producto {record.product_id.name} requiere número de lote."
                    ))
            else:
                # Productos sin rastreo no deben tener lot_id
                if record.lot_id:
                    raise ValidationError(_(
                        f"El producto {record.product_id.name} no usa rastreo por serie/lote."
                    ))

    @api.constrains('status', 'resolution_date', 'sale_order_line_id', 'return_picking_id')
    def _check_resolution_consistency(self):
        """Validar consistencia en la resolución del préstamo"""
        for record in self:
            if record.status == 'sold':
                if not record.sale_order_line_id:
                    raise ValidationError(_(
                        "Los préstamos vendidos deben tener una línea de orden de venta asociada."
                    ))
                    
            if record.status in ('returned_good', 'returned_damaged', 'returned_defective'):
                if not record.return_picking_id:
                    raise ValidationError(_(
                        "Los préstamos devueltos deben tener una transferencia de devolución asociada."
                    ))
                    
            if record.status != 'active' and not record.resolution_date:
                record.resolution_date = fields.Datetime.now()

    def _validate_status_transition(self, new_status):
        """Validar si la transición de estado es válida"""
        valid_transitions = {
            'active': ['pending_resolution', 'sold', 'returned_good', 'returned_damaged', 'returned_defective'],
            'pending_resolution': ['active', 'sold', 'returned_good', 'returned_damaged', 'returned_defective'],
            'sold': [],  # Estado final
            'returned_good': [],  # Estado final
            'returned_damaged': [],  # Estado final
            'returned_defective': []  # Estado final
        }
        
        if self.status and new_status not in valid_transitions.get(self.status, []):
            raise UserError(_(
                f"Transición de estado no válida: {self.status} → {new_status}\n"
                f"Transiciones válidas desde '{self.status}': {', '.join(valid_transitions.get(self.status, []))}"
            ))
        return True

    @api.model
    def create(self, vals):
        """Override create para validar estado inicial"""
        if vals.get('status') and vals.get('status') != 'active':
            self._validate_status_transition(vals['status'])
        return super().create(vals)

    def write(self, vals):
        """Override write para validar transiciones de estado"""
        for record in self:
            if 'status' in vals and vals['status'] != record.status:
                record._validate_status_transition(vals['status'])
                # Asegurar que la fecha de resolución se establece
                if vals['status'] in ['sold', 'returned_good', 'returned_damaged', 'returned_defective']:
                    vals['resolution_date'] = vals.get('resolution_date', fields.Datetime.now())
                    vals['last_status_change_date'] = vals.get('last_status_change_date', fields.Datetime.now())
                    vals['last_status_change_user_id'] = vals.get('last_status_change_user_id', self.env.user.id)
        
        result = super().write(vals)
        
        # Forzar flush y recarga
        if 'status' in vals:
            self.env.cr.flush()
            self.invalidate_cache()
        
        return result

    def action_mark_as_sold(self, sale_line, price=0.0):
        """
        Marca el registro de seguimiento como vendido
        :param sale_line: Línea de orden de venta relacionada
        :param price: Precio de venta
        """
        self.ensure_one()
        
        if self.status not in ['active', 'pending_resolution']:
            raise UserError(_(
                f"No se puede marcar como vendido el producto {self.product_id.name} "
                f"porque su estado actual es {self.status}"
            ))
        
        current_time = fields.Datetime.now()
        
        vals = {
            'status': 'sold',
            'resolution_date': current_time,
            'sale_order_line_id': sale_line.id,
            'sale_price': price,
            'last_status_change_date': current_time,
            'last_status_change_user_id': self.env.user.id,
        }
        
        # Realizar la actualización
        self.write(vals)
        
        # Recargar el registro para asegurar que tenemos los datos actualizados
        self = self.browse(self.id)
        
        # Verificar que el estado se actualizó correctamente
        if self.status != 'sold':
            raise UserError(_(
                f"Error al actualizar el estado del producto {self.product_id.name}. "
                f"Los cambios no se guardaron correctamente."
            ))
        
        # Registrar nota en el chatter
        self.message_post(
            body=_(
                f"Producto convertido a venta\n"
                f"- Precio de venta: {price}\n"
                f"- Orden de venta: {sale_line.order_id.name}\n"
                f"- Línea: {sale_line.name}\n"
                f"- Fecha de resolución: {current_time}"
            ),
            message_type='comment'
        )
        
        return True

    def action_mark_as_returned(self, return_picking, condition='good', notes=None):
        """Marcar el préstamo como devuelto"""
        self.ensure_one()
        
        if self.status not in ('active', 'pending_resolution'):
            raise UserError(_(
                "Solo los préstamos activos pueden marcarse como devueltos."
            ))
        
        status_mapping = {
            'good': 'returned_good',
            'damaged': 'returned_damaged',
            'defective': 'returned_defective'
        }
        
        self.write({
            'status': status_mapping.get(condition, 'returned_good'),
            'return_picking_id': return_picking.id,
            'resolution_date': fields.Datetime.now(),
            'return_condition_notes': notes or '',
            'last_status_change_date': fields.Datetime.now(),
            'last_status_change_user_id': self.env.user.id,
        })
        
        # Notificación automática
        self._post_status_change_message('returned', return_picking=return_picking, condition=condition)

    def action_view_related_documents(self):
        """Ver documentos relacionados (orden de venta o devolución)"""
        self.ensure_one()
        
        if self.sale_order_line_id:
            return {
                'name': 'Orden de Venta',
                'type': 'ir.actions.act_window',
                'res_model': 'sale.order',
                'res_id': self.sale_order_line_id.order_id.id,
                'view_mode': 'form',
                'target': 'current'
            }
        elif self.return_picking_id:
            return {
                'name': 'Devolución',
                'type': 'ir.actions.act_window',
                'res_model': 'stock.picking',
                'res_id': self.return_picking_id.id,
                'view_mode': 'form',
                'target': 'current'
            }
        else:
            return {
                'name': 'Préstamo Original',
                'type': 'ir.actions.act_window',
                'res_model': 'stock.picking',
                'res_id': self.picking_id.id,
                'view_mode': 'form',
                'target': 'current'
            }

    @api.model
    def get_loan_analytics(self, date_from=None, date_to=None, partner_ids=None):
        """Obtener analíticas de préstamos para dashboards"""
        domain = []
        
        if date_from:
            domain.append(('loan_date', '>=', date_from))
        if date_to:
            domain.append(('loan_date', '<=', date_to))
        if partner_ids:
            domain.append(('partner_id', 'in', partner_ids))
        
        records = self.search(domain)
        
        analytics = {
            'total_loans': len(records),
            'active_loans': len(records.filtered(lambda r: r.status == 'active')),
            'overdue_loans': len(records.filtered('is_overdue')),
            'sold_conversions': len(records.filtered(lambda r: r.status == 'sold')),
            'returns_good': len(records.filtered(lambda r: r.status == 'returned_good')),
            'returns_damaged': len(records.filtered(lambda r: r.status in ('returned_damaged', 'returned_defective'))),
            'avg_days_in_loan': sum(records.mapped('days_in_loan')) / len(records) if records else 0,
            'conversion_rate': len(records.filtered(lambda r: r.status == 'sold')) / len(records) * 100 if records else 0,
        }
        
        return analytics

    @api.model
    def _cron_cleanup_old_resolved_records(self):
        """Cron job para limpiar registros antiguos resueltos (opcional)"""
        # Buscar registros resueltos hace más de 2 años
        cutoff_date = fields.Datetime.now() - timedelta(days=730)
        
        old_records = self.search([
            ('status', 'in', ['sold', 'returned_good', 'returned_damaged', 'returned_defective']),
            ('resolution_date', '<', cutoff_date)
        ])
        
        _logger.info(f"Limpieza automática: encontrados {len(old_records)} registros antiguos")
        
        # En lugar de eliminar, podríamos archivar o mover a tabla histórica
        # old_records.unlink()  # Descomenta si quieres eliminar automáticamente
        
        return len(old_records)

    # ==========================================
    # MÉTODOS DE INTEGRACIÓN COMPLETA CON MAIL.THREAD
    # ==========================================
    
    def _post_status_change_message(self, new_status, **kwargs):
        """Enviar mensaje automático cuando cambia el estado"""
        self.ensure_one()
        
        status_messages = {
            'sold': self._get_sold_message,
            'returned': self._get_returned_message,
            'pending_resolution': self._get_pending_resolution_message,
        }
        
        message_method = status_messages.get(new_status)
        if message_method:
            message = message_method(**kwargs)
            self.message_post(
                body=message,
                subject=f"Cambio de Estado - {self.display_name}",
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
    
    def _get_sold_message(self, sale_order_line=None, **kwargs):
        """Mensaje para conversión a venta"""
        message = f"""
        <div class="o_mail_notification">
            <h4 style="color: #28a745;">&#10004; Préstamo Convertido a Venta</h4>
            <p><strong>Producto:</strong> {self.product_id.name}</p>
            <p><strong>Cliente:</strong> {self.partner_id.name}</p>
            <p><strong>Cantidad:</strong> {self.quantity:.2f} {self.product_id.uom_id.name}</p>
            <p><strong>Precio de Venta:</strong> ${self.sale_price:.2f}</p>
        """
        
        if sale_order_line:
            message += f"<p><strong>Orden de Venta:</strong> {sale_order_line.order_id.name}</p>"
        
        if self.lot_id:
            message += f"<p><strong>Número de Serie:</strong> {self.lot_id.name}</p>"
            
        message += "</div>"
        return message
    
    def _get_returned_message(self, return_picking=None, condition='good', **kwargs):
        """Mensaje para devolución"""
        condition_colors = {
            'good': '#28a745',
            'damaged': '#ffc107', 
            'defective': '#dc3545'
        }
        
        condition_labels = {
            'good': 'Buen Estado',
            'damaged': 'Dañado',
            'defective': 'Defectuoso'
        }
        
        color = condition_colors.get(condition, '#6c757d')
        condition_label = condition_labels.get(condition, condition.title())
        
        message = f"""
        <div class="o_mail_notification">
            <h4 style="color: {color};">&#8634; Préstamo Devuelto</h4>
            <p><strong>Producto:</strong> {self.product_id.name}</p>
            <p><strong>Cliente:</strong> {self.partner_id.name}</p>
            <p><strong>Cantidad:</strong> {self.quantity:.2f} {self.product_id.uom_id.name}</p>
            <p><strong>Condición:</strong> <span style="color: {color};">{condition_label}</span></p>
        """
        
        if return_picking:
            message += f"<p><strong>Devolución:</strong> {return_picking.name}</p>"
        
        if self.lot_id:
            message += f"<p><strong>Número de Serie:</strong> {self.lot_id.name}</p>"
            
        if self.return_condition_notes:
            message += f"<p><strong>Observaciones:</strong> {self.return_condition_notes}</p>"
            
        message += "</div>"
        return message
    
    def _get_pending_resolution_message(self, **kwargs):
        """Mensaje para estado pendiente de resolución"""
        return f"""
        <div class="o_mail_notification">
            <h4 style="color: #ffc107;">&#9888; Pendiente de Resolución</h4>
            <p><strong>Producto:</strong> {self.product_id.name}</p>
            <p><strong>Cliente:</strong> {self.partner_id.name}</p>
            <p>Este préstamo requiere acción para su resolución.</p>
        </div>
        """
    
    # ==========================================
    # OVERRIDES DE MAIL.THREAD
    # ==========================================
    
    def write(self, vals):
        """Override para tracking automático de cambios"""
        # Tracking automático de cambios de estado
        if 'status' in vals:
            for record in self:
                old_status = record.status
                record.last_status_change_date = fields.Datetime.now()
                record.last_status_change_user_id = self.env.user.id
        
        result = super().write(vals)
        
        # Post-procesamiento para notificaciones
        if 'status' in vals and vals['status'] != old_status:
            for record in self:
                record._handle_status_change_notifications(old_status, vals['status'])
        
        return result
    
    def _handle_status_change_notifications(self, old_status, new_status):
        """Manejar notificaciones automáticas por cambio de estado"""
        self.ensure_one()
        
        # Crear actividades automáticas según el nuevo estado
        if new_status == 'pending_resolution':
            self._create_resolution_activity()
        elif new_status in ('returned_damaged', 'returned_defective'):
            self._create_damage_assessment_activity()
        elif new_status == 'active' and self.is_overdue:
            self._create_overdue_activity()
    
    def _create_resolution_activity(self):
        """Crear actividad para resolución pendiente"""
        self.ensure_one()
        
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            activity_type = self.env['mail.activity.type'].search([('category', '=', 'default')], limit=1)
        
        if activity_type:
            self.activity_schedule(
                activity_type_id=activity_type.id,
                summary=f'Resolver préstamo - {self.product_id.name}',
                note=f"""
                <p>El préstamo requiere resolución:</p>
                <ul>
                    <li><strong>Producto:</strong> {self.product_id.name}</li>
                    <li><strong>Cliente:</strong> {self.partner_id.name}</li>
                    <li><strong>Días en préstamo:</strong> {self.days_in_loan}</li>
                </ul>
                <p>Acciones posibles: Convertir a venta, procesar devolución, o extender préstamo.</p>
                """,
                date_deadline=fields.Date.today() + timedelta(days=1),
                user_id=self.last_status_change_user_id.id or self.env.user.id
            )
    
    def _create_damage_assessment_activity(self):
        """Crear actividad para evaluación de daños"""
        self.ensure_one()
        
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if activity_type:
            self.activity_schedule(
                activity_type_id=activity_type.id,
                summary=f'Evaluar daños - {self.product_id.name}',
                note=f"""
                <p>Producto devuelto con daños requiere evaluación:</p>
                <ul>
                    <li><strong>Producto:</strong> {self.product_id.name}</li>
                    <li><strong>Estado:</strong> {dict(self._fields['status'].selection)[self.status]}</li>
                    <li><strong>Observaciones:</strong> {self.return_condition_notes or 'N/A'}</li>
                </ul>
                <p>Determinar costo de reparación o reemplazo.</p>
                """,
                date_deadline=fields.Date.today() + timedelta(days=2),
                user_id=self.env.user.id
            )
    
    def _create_overdue_activity(self):
        """Crear actividad para préstamo vencido"""
        self.ensure_one()
        
        # Verificar si ya tiene actividad de vencimiento reciente
        existing_activity = self.activity_ids.filtered(
            lambda a: 'vencido' in (a.summary or '').lower() and 
                     a.date_deadline >= fields.Date.today() - timedelta(days=7)
        )
        
        if existing_activity:
            return  # Ya tiene actividad reciente
        
        activity_type = self.env.ref('mail.mail_activity_data_call', raise_if_not_found=False)
        if not activity_type:
            activity_type = self.env['mail.activity.type'].search([('category', '=', 'default')], limit=1)
        
        if activity_type:
            self.activity_schedule(
                activity_type_id=activity_type.id,
                summary=f'Préstamo Vencido - {self.product_id.name}',
                note=f"""
                <p><strong style="color: #dc3545;">⚠️ Préstamo vencido hace {self.days_in_loan} días</strong></p>
                <ul>
                    <li><strong>Cliente:</strong> {self.partner_id.name}</li>
                    <li><strong>Producto:</strong> {self.product_id.name}</li>
                    <li><strong>Fecha esperada retorno:</strong> {self.expected_return_date}</li>
                </ul>
                <p><strong>Acciones recomendadas:</strong></p>
                <ul>
                    <li>Contactar al cliente</li>
                    <li>Resolver el período de prueba si aplica</li>
                    <li>Procesar devolución o venta</li>
                </ul>
                """,
                date_deadline=fields.Date.today(),
                user_id=self.env.user.id
            )
    
    # ==========================================
    # MÉTODOS DE ACCESO Y SEGURIDAD
    # ==========================================
    
    def _get_mail_thread_data(self, request_list):
        """Override para datos de thread de mail"""
        result = super()._get_mail_thread_data(request_list)
        
        # Agregar datos adicionales específicos del modelo
        if 'loan_data' in request_list:
            for record in self:
                result[record.id]['loan_data'] = {
                    'product_name': record.product_id.name,
                    'partner_name': record.partner_id.name,
                    'status_display': dict(record._fields['status'].selection)[record.status],
                    'days_in_loan': record.days_in_loan,
                    'is_overdue': record.is_overdue,
                }
        
        return result
    
    def _message_get_suggested_recipients(self):
        """Sugerir destinatarios para mensajes"""
        recipients = super()._message_get_suggested_recipients()
        
        for record in self:
            # Agregar cliente como destinatario sugerido
            if record.partner_id and record.partner_id.email:
                record._message_add_suggested_recipient(
                    recipients,
                    partner=record.partner_id,
                    reason=_('Cliente del préstamo')
                )
            
            # Agregar usuario responsable del último cambio
            if (record.last_status_change_user_id and 
                record.last_status_change_user_id != self.env.user and
                record.last_status_change_user_id.partner_id.email):
                
                record._message_add_suggested_recipient(
                    recipients,
                    partner=record.last_status_change_user_id.partner_id,
                    reason=_('Responsable del último cambio')
                )
        
        return recipients
    
    def _message_auto_subscribe_notify(self, partner_ids, template):
        """Notificación automática de suscripción"""
        # Personalizar plantilla para préstamos si es necesario
        return super()._message_auto_subscribe_notify(partner_ids, template)
    
    def _get_thread_with_access(self, thread_id, access_token=None, **kwargs):
        """Método requerido por mail.thread - SOLUCIÓN AL ERROR PRINCIPAL"""
        thread = self.browse(thread_id)
        thread.check_access_rights('read')
        thread.check_access_rule('read')
        return thread
    
    # ==========================================
    # MÉTODOS DE NOTIFICACIONES AUTOMÁTICAS
    # ==========================================
    
    def _send_loan_reminder(self):
        """Enviar recordatorio automático al cliente"""
        self.ensure_one()
        
        if not self.partner_id.email:
            _logger.warning(f"Cliente {self.partner_id.name} no tiene email para recordatorio")
            return False
        
        template = self._get_reminder_template()
        if template:
            template.send_mail(self.id, force_send=True)
            
            # Actualizar contadores
            self.write({
                'reminder_count': self.reminder_count + 1,
                'next_reminder_date': fields.Date.today() + timedelta(days=7),
                'notification_sent': True
            })
            
            # Registrar en el thread
            self.message_post(
                body=f"Recordatorio enviado al cliente ({self.partner_id.email})",
                subject="Recordatorio Enviado",
                message_type='notification'
            )
            
            return True
        
        return False
    
    def _get_reminder_template(self):
        """Obtener plantilla para recordatorios"""
        # Intentar encontrar plantilla específica de préstamos
        template = self.env.ref(
            'product_loans.loan_reminder_email_template', 
            raise_if_not_found=False
        )
        
        if not template:
            # Fallback a plantilla genérica
            template = self.env['mail.template'].search([
                ('model', '=', 'loan.tracking.detail'),
                ('name', 'ilike', 'recordatorio')
            ], limit=1)
        
        return template
    
    @api.model
    def _cron_send_reminders(self):
        """Cron job para enviar recordatorios automáticos"""
        # Buscar préstamos que requieren recordatorio
        records_to_remind = self.search([
            ('status', '=', 'active'),
            ('is_overdue', '=', True),
            '|',
            ('next_reminder_date', '<=', fields.Date.today()),
            ('next_reminder_date', '=', False)
        ])
        
        sent_count = 0
        for record in records_to_remind:
            try:
                if record._send_loan_reminder():
                    sent_count += 1
            except Exception as e:
                _logger.error(f"Error enviando recordatorio para {record.id}: {str(e)}")
        
        _logger.info(f"Enviados {sent_count} recordatorios de préstamos")
        return sent_count
    
    # ==========================================
    # MÉTODOS DE REPORTING Y ANÁLISIS
    # ==========================================
    
    def action_send_manual_reminder(self):
        """Acción manual para enviar recordatorio"""
        self.ensure_one()
        
        if self._send_loan_reminder():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Recordatorio Enviado',
                    'message': f'Se envió recordatorio a {self.partner_id.name}',
                    'type': 'success'
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'No se pudo enviar el recordatorio',
                    'type': 'danger'
                }
            }
    
    def action_view_thread_messages(self):
        """Ver mensajes del hilo de conversación"""
        self.ensure_one()
        
        return {
            'name': f'Mensajes - {self.display_name}',
            'type': 'ir.actions.act_window',
            'res_model': 'mail.message',
            'view_mode': 'list,form',
            'domain': [
                ('res_id', '=', self.id),
                ('model', '=', 'loan.tracking.detail')
            ],
            'context': {'create': False}
        }
    
    def action_archive(self):
        """Archivar registro con mensaje automático"""
        self.ensure_one()
        
        self.write({'active': False})
        
        self.message_post(
            body="Registro archivado manualmente",
            subject="Registro Archivado",
            message_type='notification'
        )
        
        return True


class LoanValuationTracker(models.Model):
    _name = 'loan.valuation.tracker'
    _description = 'Seguimiento de Valoración de Préstamos'
    _order = 'loan_date desc'

    # Referencias
    picking_id = fields.Many2one(
        'stock.picking',
        string='Préstamo',
        required=True,
        ondelete='cascade'
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True
    )
    
    lot_id = fields.Many2one(
        'stock.lot',
        string='Número de Serie/Lote'
    )
    
    # Información de valoración
    loan_date = fields.Datetime(
        string='Fecha de Préstamo',
        required=True
    )
    
    original_cost = fields.Float(
        string='Costo al Momento del Préstamo',
        digits='Product Price',
        required=True
    )
    
    current_cost = fields.Float(
        string='Costo Actual del Producto',
        digits='Product Price',
        compute='_compute_current_cost',
        store=True
    )
    
    valuation_difference = fields.Float(
        string='Diferencia de Valoración',
        digits='Product Price',
        compute='_compute_valuation_difference',
        store=True,
        help="Diferencia entre costo actual y costo original"
    )
    
    # Estado
    is_resolved = fields.Boolean(
        string='Resuelto',
        default=False,
        help="Indica si este préstamo ya fue resuelto (vendido o devuelto)"
    )
    
    resolution_type = fields.Selection([
        ('sold', 'Vendido'),
        ('returned', 'Devuelto')
    ], string='Tipo de Resolución')
    
    final_cost = fields.Float(
        string='Costo Final Utilizado',
        digits='Product Price',
        help="Costo utilizado para valoración en la transacción final"
    )

    @api.depends('product_id')
    def _compute_current_cost(self):
        """Obtener costo actual del producto"""
        for record in self:
            if record.product_id:
                record.current_cost = record.product_id.standard_price
            else:
                record.current_cost = 0.0

    @api.depends('original_cost', 'current_cost')
    def _compute_valuation_difference(self):
        """Calcular diferencia de valoración"""
        for record in self:
            record.valuation_difference = record.current_cost - record.original_cost

    def mark_as_resolved(self, resolution_type, final_cost=None):
        """Marcar como resuelto con tipo específico"""
        self.write({
            'is_resolved': True,
            'resolution_type': resolution_type,
            'final_cost': final_cost or self.original_cost
        })

    @api.model
    def create_for_loan(self, picking):
        """Crear registros de valoración para un préstamo nuevo"""
        valuation_records = []
        
        for move in picking.move_ids_without_package:
            if move.product_id.tracking == 'serial':
                # Un registro por cada número de serie
                for move_line in move.move_line_ids:
                    if move_line.lot_id:
                        valuation_records.append({
                            'picking_id': picking.id,
                            'product_id': move.product_id.id,
                            'lot_id': move_line.lot_id.id,
                            'loan_date': picking.date_done or fields.Datetime.now(),
                            'original_cost': move.product_id.standard_price,
                        })
            else:
                # Un registro por producto
                valuation_records.append({
                    'picking_id': picking.id,
                    'product_id': move.product_id.id,
                    'loan_date': picking.date_done or fields.Datetime.now(),
                    'original_cost': move.product_id.standard_price,
                })
        
        return self.create(valuation_records)

    @api.model
    def get_valuation_impact_report(self):
        """Generar reporte de impacto de valoración"""
        unresolved_records = self.search([('is_resolved', '=', False)])
        
        total_original = sum(unresolved_records.mapped('original_cost'))
        total_current = sum(unresolved_records.mapped('current_cost'))
        total_difference = total_current - total_original
        
        return {
            'unresolved_loans_count': len(unresolved_records),
            'total_original_value': total_original,
            'total_current_value': total_current,
            'total_valuation_impact': total_difference,
            'avg_valuation_difference': total_difference / len(unresolved_records) if unresolved_records else 0,
            'significant_differences': unresolved_records.filtered(
                lambda r: abs(r.valuation_difference) > r.original_cost * 0.1
            )
        }