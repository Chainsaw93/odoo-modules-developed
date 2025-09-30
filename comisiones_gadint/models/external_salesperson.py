# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError


class ExternalSalesperson(models.Model):
    _name = 'gadint.external.salesperson'
    _description = 'Vendedores Externos Gadint'
    _inherit = ['mail.thread', 'mail.activity.mixin']  # Agregado para el chatter
    _rec_name = 'display_name'
    _order = 'name asc'

    # Campo principal de nombre mostrado
    name = fields.Char(
        string='Nombre Mostrado',
        required=True,
        tracking=True,  # Agregado tracking para el chatter
        help='Nombre que se mostrará al seleccionar este vendedor'
    )
    
    # Tipo de vendedor (Líder o Vendedor)
    seller_type = fields.Selection([
        ('leader', 'Líder'),
        ('salesperson', 'Vendedor')
    ], string='Tipo de vendedor', required=True, default='salesperson', tracking=True)
    
    # Relación con el contacto
    partner_id = fields.Many2one(
        'res.partner',
        string='Contacto',
        required=True,
        domain=[('external_sales_team', '=', True)],
        tracking=True,
        help='Seleccione el contacto que tiene marcado el campo vendedor externo'
    )
    
    # Porcentaje de comisión
    leader_percentage = fields.Float(
        string='Porcentaje de Comisión',
        default=1.0,
        tracking=True,
        help='Para líderes: porcentaje directo sobre el importe cobrado. Para vendedores: se usa el % del plan de comisión'
    )
    
    # Campo computed para mostrar nombre completo
    display_name = fields.Char(
        string='Nombre',
        compute='_compute_display_name',
        store=True
    )
    
    # Campos adicionales de información
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company
    )
    
    # Campos relacionados del partner para información adicional
    partner_email = fields.Char(
        related='partner_id.email',
        string='Email',
        readonly=True
    )
    
    partner_phone = fields.Char(
        related='partner_id.phone',
        string='Teléfono',
        readonly=True
    )
    
    # Campo computed para mostrar comisión en contexto de factura
    commission_amount_invoice = fields.Monetary(
        string='Comisión Calculada',
        compute='_compute_commission_amount_invoice',
        currency_field='currency_id',
        store=False,
        compute_sudo=True,  # Ejecutar con permisos elevados
        help='Comisión calculada para la factura en contexto'
    )
    
    # Campo para la moneda (necesario para el campo Monetary)
    currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_currency_id',
        string='Moneda'
    )
    
    # Campo computed para mostrar el porcentaje de comisión que se aplica
    commission_rate_display = fields.Char(
        string='% Comisión',
        compute='_compute_commission_rate_display',
        help='Muestra el porcentaje efectivo que se aplicará para la comisión'
    )
    
    @api.depends('name', 'seller_type', 'partner_id')
    def _compute_display_name(self):
        """Computa el nombre para mostrar en las selecciones"""
        for record in self:
            if record.name and record.seller_type:
                tipo_str = 'Líder' if record.seller_type == 'leader' else 'Vendedor'
                record.display_name = f"{record.name} ({tipo_str})"
            else:
                record.display_name = record.name or ''
    
    def _compute_currency_id(self):
        """Obtener moneda de la compañía o del contexto"""
        for record in self:
            # Intentar obtener moneda de la factura en contexto
            invoice_id = self._context.get('invoice_id')
            if invoice_id:
                invoice = self.env['account.move'].browse(invoice_id)
                record.currency_id = invoice.currency_id
            else:
                record.currency_id = self.env.company.currency_id
    
    @api.depends('seller_type', 'leader_percentage')
    def _compute_commission_rate_display(self):
        """Mostrar el porcentaje efectivo de comisión"""
        for record in self:
            if record.seller_type == 'leader':
                # Para líderes, mostrar su porcentaje directo con detección de formato
                percentage = record.leader_percentage if record.leader_percentage > 0 else 1.0
                
                # Detectar formato: si <= 1, probablemente es decimal (0.05 = 5%)
                if percentage <= 1.0 and percentage > 0:
                    display_percentage = percentage * 100  # 0.05 → 5
                    format_note = "(decimal→entero)"
                else:
                    display_percentage = percentage  # Ya está en formato entero
                    format_note = "(directo)"
                
                record.commission_rate_display = f"{display_percentage:.1f}% {format_note}"
            else:
                # Para vendedores, intentar obtener el % del plan de comisión
                if 'sale.commission.plan' in self.env:
                    try:
                        # Buscar planes activos con tipo 'amount_collected'
                        # Primero buscar todos los planes activos
                        all_plans = self.env['sale.commission.plan'].search([
                            ('active', '=', True)
                        ])
                        
                        rate_found = None
                        for plan in all_plans:
                            if plan.state in ['approved', 'done']:
                                achievements = plan.achievement_ids.filtered(lambda a: a.type == 'amount_collected')
                                if achievements:
                                    rate_found = achievements[0].rate
                                    break
                        
                        if rate_found is not None:
                            # APLICAR LA MISMA LÓGICA DE DETECCIÓN QUE EN EL CÁLCULO
                            if rate_found > 1.0:
                                # Formato entero: mostrar tal como está
                                display_rate = rate_found
                            else:
                                # Formato decimal: convertir para mostrar (0.05 → 5)
                                display_rate = rate_found * 100
                            
                            record.commission_rate_display = f"{display_rate:.1f}% (plan)"
                        else:
                            record.commission_rate_display = "0.0% (sin plan)"
                            
                    except Exception as e:
                        record.commission_rate_display = f"Error: {str(e)}"
                else:
                    record.commission_rate_display = "Sale commission no disponible"
    
    @api.depends('name', 'display_name', 'partner_id')
    def _compute_commission_amount_invoice(self):
        """Calcular comisión para la factura en contexto"""
        for record in self:
            # Primero verificar si hay un valor forzado en el contexto
            forced_amount = self._context.get('force_commission_amount')
            if forced_amount is not None:
                record.commission_amount_invoice = forced_amount
                continue
                
            amount = 0.0
            invoice_id = self._context.get('invoice_id')
            
            if invoice_id and 'sale.commission.achievement' in self.env:
                # Buscar achievements para esta factura
                achievements = self.env['sale.commission.achievement'].search([
                    ('invoice_id', '=', invoice_id),
                    ('type', '=', 'amount_collected')
                ])
                
                # Buscar por nombre del vendedor en la nota
                for achievement in achievements:
                    if (record.name in achievement.note or 
                        record.display_name in achievement.note or
                        (record.partner_id and record.partner_id.name in achievement.note)):
                        amount += achievement.amount
            
            record.commission_amount_invoice = amount
    
    @api.constrains('leader_percentage')
    def _check_leader_percentage(self):
        """Validar que el porcentaje esté entre 0 y 100"""
        for record in self:
            if record.seller_type == 'leader':
                if record.leader_percentage < 0 or record.leader_percentage > 100:
                    raise ValidationError(
                        'El porcentaje debe estar entre 0 y 100.'
                    )
    
    @api.constrains('partner_id')
    def _check_partner_external_sales_team(self):
        """Validar que el partner tenga marcado el campo external_sales_team"""
        for record in self:
            if record.partner_id and not record.partner_id.external_sales_team:
                raise ValidationError(
                    f'El contacto {record.partner_id.name} debe tener marcado '
                    'el campo "Equipo vendedores externos" para poder ser seleccionado.'
                )
    
    @api.constrains('partner_id')
    def _check_unique_partner(self):
        """Validar que un partner no esté duplicado como vendedor externo"""
        for record in self:
            if record.partner_id:
                existing = self.search([
                    ('partner_id', '=', record.partner_id.id),
                    ('id', '!=', record.id)
                ])
                if existing:
                    raise ValidationError(
                        f'El contacto {record.partner_id.name} ya está configurado '
                        'como vendedor externo.'
                    )
    
    @api.onchange('seller_type')
    def _onchange_seller_type(self):
        """Configurar porcentaje por defecto según tipo"""
        if self.seller_type == 'leader':
            # Para líderes: porcentaje directo sobre importe (por defecto 1%)
            self.leader_percentage = 1.0
        else:
            # Para vendedores: no se usa este campo, se usa el plan de comisión
            # Pero se deja en 0 para claridad
            self.leader_percentage = 0.0
    
    # NORMALIZACIÓN AUTOMÁTICA DESACTIVADA
    # El problema era que interfería con los valores normales
    # Ahora usamos solo la detección inteligente en el cálculo
    
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """Autocompletar nombre cuando se selecciona un partner"""
        if self.partner_id and not self.name:
            self.name = self.partner_id.name
    
    def refresh_commission_rate_display(self):
        """Forzar actualización del campo commission_rate_display"""
        for record in self:
            record._compute_commission_rate_display()
        return True
    
    def name_get(self):
        """Personalizar la representación del nombre"""
        result = []
        for record in self:
            name = record.display_name or record.name or ''
            result.append((record.id, name))
        return result
    
    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Mejorar la búsqueda por nombre"""
        args = args or []
        if name:
            records = self.search([
                '|', '|',
                ('name', operator, name),
                ('display_name', operator, name),
                ('partner_id.name', operator, name)
            ] + args, limit=limit)
        else:
            records = self.search(args, limit=limit)
        return records.name_get()
    
    @api.model
    def fix_existing_percentages(self):
        """Método para corregir porcentajes de vendedores existentes"""
        # Para vendedores regulares: dejar en 0% (usan el plan de comisión)
        regular_salespeople = self.search([
            ('seller_type', '=', 'salesperson')
        ])
        updated_count = 0
        for salesperson in regular_salespeople:
            old_percentage = salesperson.leader_percentage
            salesperson.leader_percentage = 0.0
            salesperson.message_post(
                body=f"Porcentaje actualizado de {old_percentage}% a 0% - Los vendedores regulares usan el % del plan de comisión",
                subject='Corrección de Porcentaje'
            )
            updated_count += 1
        
        # Corregir líderes que tienen porcentajes incorrectos o muy bajos
        leaders = self.search([
            ('seller_type', '=', 'leader')
        ])
        for leader in leaders:
            old_percentage = leader.leader_percentage
            # NUEVA LÓGICA: Normalización inteligente
            if leader.leader_percentage < 1 and leader.leader_percentage > 0:
                # Convertir de decimal a entero: 0.01 → 1
                leader.leader_percentage = leader.leader_percentage * 100
                updated_count += 1
            elif leader.leader_percentage == 0:
                # Si es 0, configurar a 1% por defecto
                leader.leader_percentage = 1.0
                updated_count += 1
            
            if old_percentage != leader.leader_percentage:
                leader.message_post(
                    body=f"AUTO-CORRECCIÓN: Porcentaje normalizado de {old_percentage}% a {leader.leader_percentage}% para líder",
                    subject='Normalización Automática'
                )
        
        # NUEVA: Corregir también los planes de comisión existentes
        if 'sale.commission.plan' in self.env:
            plans = self.env['sale.commission.plan'].search([
                ('achievement_ids.type', '=', 'amount_collected'),
                ('active', '=', True)
            ])
            
            for plan in plans:
                for achievement in plan.achievement_ids.filtered(lambda a: a.type == 'amount_collected'):
                    old_rate = achievement.rate
                    # Solo normalizar si está en formato decimal puro (< 1)
                    if 0 < achievement.rate < 1:
                        # Normalizar rate del plan: 0.05 → 5
                        achievement.rate = achievement.rate * 100
                        updated_count += 1
                        
                        # Log en el primer vendedor encontrado (para no spam)
                        if updated_count == 1:
                            first_leader = leaders[:1] if leaders else None
                            if first_leader:
                                first_leader.message_post(
                                    body=f"AUTO-CORRECCIÓN PLAN: '{plan.name}' rate normalizado de {old_rate}% a {achievement.rate}%",
                                    subject='Plan Normalizado'
                                )
        
        # Log general - no usar mail.thread directamente
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"Corrección automática completada: {updated_count} elementos normalizados")
        
        return True

    def unlink(self):
        """Verificar si se puede eliminar el vendedor externo"""
        for record in self:
            # Verificar si está asignado en órdenes de venta
            sale_orders = self.env['sale.order'].search([
                ('external_salesperson_ids', 'in', record.id)
            ])
            if sale_orders:
                raise UserError(
                    f'No se puede eliminar el vendedor externo {record.display_name} '
                    f'porque está asignado en {len(sale_orders)} orden(es) de venta.'
                )
            
            # Verificar si está asignado en facturas
            invoices = self.env['account.move'].search([
                ('external_salesperson_ids', 'in', record.id)
            ])
            if invoices:
                raise UserError(
                    f'No se puede eliminar el vendedor externo {record.display_name} '
                    f'porque está asignado en {len(invoices)} factura(s).'
                )
        
        return super().unlink()