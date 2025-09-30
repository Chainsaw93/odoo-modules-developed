# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SaleCommissionPlanAchievement(models.Model):
    _inherit = 'sale.commission.plan.achievement'
    
    # Extender las opciones de tipo para incluir "importe cobrado"
    type = fields.Selection(
        selection_add=[
            ('amount_collected', 'Importe Cobrado'),
        ],
        ondelete={'amount_collected': 'cascade'}
    )
    
    # NORMALIZACIÓN AUTOMÁTICA DESACTIVADA
    # El problema era que interfería con los valores normales como 5%
    # Ahora usamos solo la detección inteligente en el cálculo de comisiones
    
    # Métodos de corrección removidos - ahora se usa SQL directo en hooks.py


class SaleCommissionAchievement(models.Model):
    _inherit = 'sale.commission.achievement' 
    
    # Extender las opciones de tipo para incluir "importe cobrado"
    type = fields.Selection(
        selection_add=[
            ('amount_collected', 'Importe Cobrado'),
        ],
        ondelete={'amount_collected': 'cascade'}
    )
    
    # Campo directo para el vendedor externo (más confiable)
    external_salesperson_id = fields.Many2one(
        'gadint.external.salesperson',
        string='Vendedor Externo',
        help='Vendedor externo que generó esta comisión'
    )
    
    # Campo para mostrar el partner asociado al vendedor externo
    external_salesperson_partner_id = fields.Many2one(
        'res.partner',
        string='Contacto Vendedor Externo',
        related='external_salesperson_id.partner_id',
        store=True,
        help='Contacto asociado al vendedor externo que generó esta comisión'
    )
    
    # Campo para relacionar con factura (opcional)
    invoice_id = fields.Many2one(
        'account.move',
        string='Factura Relacionada',
        help='Factura que generó esta comisión'
    )
    
    @api.model
    def _get_achievement_amount_collected(self, invoice, partner=None):
        """Calcular comisión basada en importe cobrado de la factura"""
        if invoice.move_type == 'out_invoice' and invoice.state == 'posted':
            # Importe cobrado = Total - Residual (lo que ya está pagado)
            amount_collected = max(invoice.amount_total - invoice.amount_residual, 0.0)
            return amount_collected
        return 0.0


class AccountMoveCommissionExtension(models.Model):
    _inherit = 'account.move'
    
    def _calculate_amount_collected_commissions_from_extension(self, invoice):
        """Método de acceso para calcular comisiones desde account_move.py"""
        return self._calculate_amount_collected_commissions(invoice)
    
    def _reconcile_payments(self, debit_moves, credit_moves):
        """Sobrescribir para calcular comisiones por importe cobrado cuando se reconcilian pagos"""
        result = super()._reconcile_payments(debit_moves, credit_moves)
        
        # Solo procesar si sale_commission está disponible
        if 'sale.commission.plan' not in self.env:
            return result
        
        # Procesar facturas que tienen vendedores externos
        invoices_with_external = (debit_moves + credit_moves).filtered(
            lambda m: m.move_type == 'out_invoice' and m.external_salesperson_ids
        )
        
        for invoice in invoices_with_external:
            # LOG para debug
            invoice.message_post(
                body=f"COMMISSION_PLAN RECONCILE - Verificando si necesita recalcular comisiones para {invoice.name}",
                subject='COMMISSION_PLAN - Reconcile Trigger'
            )
            
            # Verificar si ya existen comisiones calculadas para esta factura
            existing_achievements = self.env['sale.commission.achievement'].search([
                ('invoice_id', '=', invoice.id),
                ('type', '=', 'amount_collected')
            ])
            
            if existing_achievements:
                invoice.message_post(
                    body=f"SKIP RECONCILE: Ya existen {len(existing_achievements)} comisiones calculadas. Solo actualizando estado 'commission_paid'",
                    subject='COMMISSION_PLAN - Skip Recálculo'
                )
                # Solo actualizar los campos computed y estado
                invoice._compute_total_commission_amount()
                invoice._compute_commission_detail()
                if hasattr(invoice, '_update_individual_commissions'):
                    invoice._update_individual_commissions()
            else:
                invoice.message_post(
                    body="RECONCILE: No hay comisiones previas, calculando por primera vez",
                    subject='COMMISSION_PLAN - Calculando Primera Vez'
                )
                
                self._calculate_amount_collected_commissions(invoice)
                # Forzar actualización de campos computed
                invoice._compute_total_commission_amount()
                invoice._compute_commission_detail()
                
                # AGREGAR LA ACTUALIZACIÓN DE COMISIONES INDIVIDUALES
                if hasattr(invoice, '_update_individual_commissions'):
                    invoice._update_individual_commissions()
                    
                    invoice.message_post(
                        body="COMMISSION_PLAN: Cálculo completo de comisiones automático finalizado",
                        subject='COMMISSION_PLAN - Cálculo Completo'
                    )
        
        return result
    
    def _calculate_amount_collected_commissions(self, invoice):
        """Calcular comisiones basadas en importe cobrado para una factura"""
        # LOG INICIAL
        invoice.message_post(
            body=f"INICIO CÁLCULO: invoice_id={invoice.id}, payment_state={invoice.payment_state}",
            subject='DEBUG - Inicio Cálculo Comisiones'
        )
        
        # Verificar disponibilidad de sale_commission
        if 'sale.commission.plan' not in self.env:
            invoice.message_post(
                body="ERROR: sale.commission.plan no está disponible en el entorno",
                subject='DEBUG - Error Sale Commission'
            )
            return
        
        # Solo si hay vendedores externos asignados
        if not invoice.external_salesperson_ids:
            invoice.message_post(
                body="SKIP: No hay vendedores externos asignados",
                subject='DEBUG - Sin Vendedores'
            )
            return
            
        # Verificar si ya existen comisiones para evitar duplicados
        existing_achievements = self.env['sale.commission.achievement'].search([
            ('invoice_id', '=', invoice.id),
            ('type', '=', 'amount_collected')
        ])
        
        if existing_achievements:
            invoice.message_post(
                body=f"SKIP: Ya existen {len(existing_achievements)} comisiones calculadas para esta factura",
                subject='DEBUG - Comisiones Existentes'
            )
            return
        
        # Calcular comisiones en dos casos:
        # 1. Cuando hay pagos: ['paid', 'in_payment', 'partial'] 
        # 2. Cuando se confirma la factura: 'not_paid' pero factura en estado 'posted'
        payment_valid_states = ['paid', 'in_payment', 'partial']
        invoice_confirmed = invoice.state == 'posted' and invoice.payment_state == 'not_paid'
        
        if invoice.payment_state not in payment_valid_states and not invoice_confirmed:
            invoice.message_post(
                body=f"SKIP: payment_state '{invoice.payment_state}' no válido y factura no confirmada (state: {invoice.state})",
                subject='DEBUG - Estado No Válido'
            )
            return
            
        # Log del escenario - CAMBIO: Usar subtotal sin impuestos como base
        if invoice_confirmed:
            scenario = "CONFIRMACIÓN DE FACTURA"
            base_amount = invoice.amount_untaxed  # CAMBIO: Usar subtotal sin impuestos
        else:
            scenario = "PAGO PROCESADO"
            # CAMBIO: Calcular proporción del subtotal según el pago cobrado
            if invoice.amount_total > 0:
                cobrado_ratio = max(invoice.amount_total - invoice.amount_residual, 0.0) / invoice.amount_total
                base_amount = invoice.amount_untaxed * cobrado_ratio
            else:
                base_amount = 0.0
            
        invoice.message_post(
            body=f"ESCENARIO: {scenario} - Base para cálculo: {base_amount}",
            subject='DEBUG - Escenario de Cálculo'
        )
        
        # Buscar planes de comisión con tipo 'amount_collected'
        # Debug paso a paso
        
        # 1. Verificar todos los planes
        all_plans = self.env['sale.commission.plan'].search([])
        invoice.message_post(
            body=f"PASO 1 - TODOS LOS PLANES: {len(all_plans)} total",
            subject='DEBUG - Paso 1'
        )
        
        # 2. Solo planes activos
        active_plans = self.env['sale.commission.plan'].search([('active', '=', True)])
        invoice.message_post(
            body=f"PASO 2 - PLANES ACTIVOS: {len(active_plans)} → {[(p.name, p.state) for p in active_plans]}",
            subject='DEBUG - Paso 2'
        )
        
        # 3. Verificar achievements de cada plan activo
        for plan in active_plans:
            achievements = plan.achievement_ids
            achievement_types = [a.type for a in achievements]
            invoice.message_post(
                body=f"PASO 3 - Plan '{plan.name}': {len(achievements)} achievements → tipos: {achievement_types}",
                subject='DEBUG - Paso 3'
            )
        
        # 4. Buscar con filtros
        plans = self.env['sale.commission.plan'].search([
            ('achievement_ids.type', '=', 'amount_collected'),
            ('state', 'in', ['approved', 'done']),
            ('active', '=', True)
        ])
        
        # Debug detallado de los planes encontrados
        plan_details = []
        for plan in plans:
            achievements_info = []
            for achievement in plan.achievement_ids.filtered(lambda a: a.type == 'amount_collected'):
                achievements_info.append(f"Rate: {achievement.rate}%")
            plan_details.append(f"Plan '{plan.name}': {', '.join(achievements_info)}")
        
        invoice.message_post(
            body=f"PLANES ENCONTRADOS: {len(plans)} planes de comisión activos\nDetalles: {'; '.join(plan_details)}",
            subject='DEBUG - Planes de Comisión DETALLE'
        )
        
        # amount_collected ya se calcula arriba como base_amount según el escenario
        
        invoice.message_post(
            body=f"IMPORTE BASE: {base_amount} (Subtotal: {invoice.amount_untaxed}, Total: {invoice.amount_total}, Residual: {invoice.amount_residual})",
            subject='DEBUG - Cálculo Importe'
        )
        
        if base_amount <= 0:
            invoice.message_post(
                body="SKIP: Importe cobrado es 0 o negativo",
                subject='DEBUG - Sin Importe'
            )
            return
        
        for plan in plans:
            for achievement in plan.achievement_ids.filtered(lambda a: a.type == 'amount_collected'):
                # Crear comisión por cada vendedor externo
                for salesperson in invoice.external_salesperson_ids:
                    # Verificar si ya existe una comisión para esta combinación
                    existing_commission = self.env['sale.commission.achievement'].search([
                        ('invoice_id', '=', invoice.id),
                        ('type', '=', 'amount_collected'),
                        ('note', 'ilike', salesperson.name)
                    ])
                    
                    if existing_commission:
                        continue  # Ya existe, no duplicar
                    
                    # Lógica CORREGIDA de cálculo de comisiones con detección automática de formato:
                    # - Detecta si el porcentaje ya está en formato decimal (0.05) o entero (5)
                    # - Aplica conversión solo cuando es necesario
                    
                    if salesperson.seller_type == 'leader':
                        # Para líderes: usar su porcentaje configurado directamente
                        leader_rate = salesperson.leader_percentage
                        
                        # DETECCIÓN AUTOMÁTICA: Si el rate > 1, está en formato entero (5%)
                        # Si el rate <= 1, está en formato decimal (0.05)
                        if leader_rate > 1.0:
                            # Formato entero: 5% → aplicar /100
                            commission_amount = base_amount * (leader_rate / 100.0)
                        else:
                            # Formato decimal: 0.05 → aplicar directamente
                            commission_amount = base_amount * leader_rate
                        
                        rate_used = leader_rate
                        calculation_type = f"Líder (formato: {'entero' if leader_rate > 1.0 else 'decimal'})"
                    else:
                        # Para vendedores: usar el % del plan de comisión
                        plan_rate = achievement.rate
                        
                        # MISMA DETECCIÓN para planes de comisión
                        if plan_rate > 1.0:
                            # Formato entero: 5% → aplicar /100
                            commission_amount = base_amount * (plan_rate / 100.0)
                        else:
                            # Formato decimal: 0.05 → aplicar directamente
                            commission_amount = base_amount * plan_rate
                        
                        rate_used = plan_rate
                        calculation_type = f"Plan (formato: {'entero' if plan_rate > 1.0 else 'decimal'})"
                    
                    # Debug: mostrar cálculo detallado
                    invoice.message_post(
                        body=f"""
                        CÁLCULO DETALLADO para {salesperson.name}:
                        - Tipo: {salesperson.seller_type}
                        - {calculation_type}: {rate_used}%
                        - Importe base ({scenario}): {base_amount:.2f}
                        - Comisión final: {commission_amount:.2f}
                        """,
                        subject='DEBUG - Cálculo Individual'
                    )
                    
                    if commission_amount > 0:
                        # Obtener usuario y equipo de ventas
                        user = salesperson.partner_id.user_id if salesperson.partner_id.user_id else invoice.user_id
                        team = user.sale_team_id if user and user.sale_team_id else self.env['crm.team'].search([('name', 'ilike', 'Sales')], limit=1)
                        
                        # Si no hay equipo, crear uno por defecto
                        if not team:
                            team = self.env['crm.team'].create({
                                'name': 'Equipo Vendedores Externos',
                                'user_id': user.id if user else self.env.user.id,
                                'member_ids': [(4, user.id)] if user else []
                            })
                        
                        # Debug: Verificar campos disponibles en el modelo
                        achievement_model = self.env['sale.commission.achievement']
                        available_fields = list(achievement_model._fields.keys())
                        invoice.message_post(
                            body=f"CAMPOS DISPONIBLES en sale.commission.achievement: {', '.join(sorted(available_fields))}",
                            subject='DEBUG - Campos del Modelo'
                        )
                        
                        # Crear el logro de comisión con campos validados
                        achievement_vals = {
                            'type': 'amount_collected',
                            'amount': commission_amount,
                            'date': fields.Date.today(),
                            'user_id': user.id if user else self.env.user.id,
                            'team_id': team.id,
                            'currency_id': invoice.currency_id.id,
                            'note': f'Comisión importe cobrado - {salesperson.name} - Factura {invoice.name}',
                            'external_salesperson_id': salesperson.id,  # Establecer directamente el vendedor
                        }
                        
                        # Agregar invoice_id solo si el campo existe
                        if 'invoice_id' in achievement_model._fields:
                            achievement_vals['invoice_id'] = invoice.id
                        
                        # Agregar plan_id solo si el campo existe
                        if 'plan_id' in achievement_model._fields and plan:
                            achievement_vals['plan_id'] = plan.id
                            
                        invoice.message_post(
                            body=f"VALORES PARA CREAR: {achievement_vals}",
                            subject='DEBUG - Valores Achievement'
                        )
                        
                        self.env['sale.commission.achievement'].create(achievement_vals)
                        
                        # Mensaje en chatter
                        invoice.message_post(
                            body=f'Comisión calculada para {salesperson.name}: {commission_amount:.2f} {invoice.currency_id.name} (Tipo: {calculation_type}, Rate: {rate_used}%)',
                            subject='Comisión por Importe Cobrado Calculada'
                        )
                
                # Forzar recálculo de campos computed
                invoice._compute_total_commission_amount()
                invoice._compute_commission_detail()


# Modelo de información sobre comisiones (siempre disponible)
class SaleCommissionReport(models.Model):
    """
    Extensión del reporte nativo de comisiones de Odoo 18
    para incluir comisiones por importe cobrado
    """
    _inherit = 'sale.commission.report'
    
    # Agregar campos específicos para nuestras comisiones
    is_amount_collected = fields.Boolean(
        string='Comisión Importe Cobrado',
        help='Indica si esta comisión es del tipo importe cobrado'
    )
    external_salesperson_id = fields.Many2one(
        'gadint.external.salesperson',
        string='Vendedor Externo',
        help='Vendedor externo asociado a esta comisión'
    )
    invoice_reference = fields.Char(
        string='Referencia Factura',
        help='Número de la factura que generó esta comisión'
    )
    
    def _select(self):
        """Extender el SELECT para incluir nuestros campos"""
        try:
            select_str = super()._select()
        except AttributeError:
            # Fallback si no existe el método padre
            select_str = """
                SELECT a.id,
                       a.date,
                       a.amount,
                       a.currency_id,
                       a.user_id,
                       a.team_id,
                       a.type"""
        
        select_str += """,
            CASE WHEN a.type = 'amount_collected' THEN true ELSE false END as is_amount_collected,
            CASE WHEN a.note ILIKE '%lider%' OR a.note ILIKE '%líder%' 
                 THEN (SELECT es.id FROM gadint_external_salesperson es 
                       WHERE es.seller_type = 'leader' 
                       AND (a.note ILIKE '%' || es.name || '%' OR a.note ILIKE '%' || es.display_name || '%')
                       LIMIT 1)
                 WHEN a.note ILIKE '%vendedor%'
                 THEN (SELECT es.id FROM gadint_external_salesperson es 
                       WHERE es.seller_type = 'salesperson' 
                       AND (a.note ILIKE '%' || es.name || '%' OR a.note ILIKE '%' || es.display_name || '%')
                       LIMIT 1)
                 ELSE NULL
            END as external_salesperson_id,
            CASE WHEN a.invoice_id IS NOT NULL 
                 THEN (SELECT am.name FROM account_move am WHERE am.id = a.invoice_id)
                 ELSE NULL
            END as invoice_reference"""
        return select_str
    
    def _group_by(self):
        """Extender el GROUP BY"""
        try:
            group_by_str = super()._group_by()
        except AttributeError:
            # Fallback si no existe el método padre
            group_by_str = """
                GROUP BY a.id, a.date, a.amount, a.currency_id, a.user_id, a.team_id, a.type"""
        
        group_by_str += """, a.note, a.invoice_id"""
        return group_by_str


class CommissionIntegrationInfo(models.TransientModel):
    """
    Modelo de información sobre estado de comisiones
    """
    _name = 'gadint.commission.integration'
    _description = 'Información de Integración con Comisiones'
    
    name = fields.Char(string='Estado', compute='_compute_commission_status')
    description = fields.Text(
        string='Información',
        compute='_compute_commission_info'
    )
    
    @api.depends()
    def _compute_commission_status(self):
        for record in self:
            if 'sale.commission.plan' in self.env:
                record.name = 'Comisiones Nativas Disponibles'
            else:
                record.name = 'Comisiones Nativas No Disponibles'
    
    @api.depends()
    def _compute_commission_info(self):
        for record in self:
            if 'sale.commission.plan' in self.env:
                try:
                    plans_count = self.env['sale.commission.plan'].search_count([])
                    record.description = f'''
SISTEMA DE COMISIONES ACTIVO

 Módulo sale_commission instalado
 Planes disponibles: {plans_count}
 Tipo "Importe Cobrado" agregado

Para usar:
1. Ventas → Comisiones → Planes de Comisión
2. Crear plan con tipo "Importe Cobrado"  
3. Asignar a vendedores externos

El cálculo automático funciona al cobrar facturas.
                    '''
                except Exception as e:
                    record.description = f'Error al consultar planes: {str(e)}'
            else:
                record.description = '''
SISTEMA DE COMISIONES NO DISPONIBLE

 Módulo sale_commission no instalado

Para activar comisiones por importe cobrado:
1. Apps → Buscar "Commission" → Instalar
2. Ventas → Configuración → Ajustes →  Comisiones  
3. Reiniciar Odoo
4. Configurar planes de comisión

Mientras tanto: gestión básica de vendedores externos funciona.
                '''